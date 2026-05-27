/*
 * Million SNN Crypto Trader — Native C Backtest Engine
 *
 * Full backtest loop in C: OHLCV encoding -> SNN forward -> R-STDP
 * Called once from Python via ctypes for the entire backtest.
 *
 * Build:
 *   clang -shared -O3 -o snn_trader.dll snn_trader.c -lm
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

/* ==================== Architecture constants ==================== */
#define NUCLEUS_SIZE   64
#define BUY_N          18
#define SELL_N         18
#define TOTAL_N        (BUY_N + SELL_N)
#define UNFOLD_SIZE    (NUCLEUS_SIZE * 4)
#define SENSORY        14
#define COMPRESS_OUT   64

/* ==================== ARCHIVE_PROJ_FN — must match Python encoding.py ==================== */
#define ARCHIVE_PROJ_FN(i, j, level) \
    ((float)((((i) * 13) ^ ((j) * 7) ^ ((level) * 5)) % 31 - 15) / 15.0f)

/* ==================== API export macro ==================== */
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

/* ==================== Neuron ==================== */
typedef struct {
    float nucleus[NUCLEUS_SIZE];
    float bias;
    float potential;
    float threshold;
    float refractory;
    int   refr_counter;
    float output;
    float eligibility[NUCLEUS_SIZE];
    float velocity[NUCLEUS_SIZE];
} Neuron;

/* ==================== R-STDP Engine ==================== */
typedef struct {
    float lr;
    float lr_0;
    float decay;
    float reward_k;
    float fee_pct;
    float micro_lr_scale;
    float total_pnl;
    int   trades;
    int   wins;
    int   trades_total;
    float running_pnl_sum;
    float running_pnl_sq;
    int   running_count;
} RSTDPState;

/* ==================== Global State ==================== */
static Neuron g_neurons[TOTAL_N];
static RSTDPState g_rstdp;
static float g_active_mask[TOTAL_N]; /* 1.0 = active, 0.0 = reserve */

/* ==================== Archive Operations ==================== */

static void archive_unfold(const float* in, int in_size,
                           float* out, int out_size, int level) {
    for (int i = 0; i < out_size; i++) {
        float sum = 0.0f;
        for (int j = 0; j < in_size; j++) {
            sum += in[j] * ARCHIVE_PROJ_FN(i, j, level);
        }
        out[i] = tanhf(sum / (float)in_size);
    }
}

static void archive_compress(const float* in, int in_size,
                             float* out, int out_size) {
    int group = in_size / out_size;
    if (group < 1) group = 1;
    for (int i = 0; i < out_size; i++) {
        float sum = 0.0f;
        int start = i * group;
        for (int j = 0; j < group && (start + j) < in_size; j++) {
            sum += in[start + j];
        }
        out[i] = sum / (float)group;
    }
}

/* ==================== Feature Encoding (14 channels) ==================== */

static void encode_features(float o, float h, float l, float c, float v,
                            float* vol_hist, int* vol_len, float* out,
                            const float* order_book, const float* trade_tape) {
    float spread = h - l;
    if (spread < 1e-8f) spread = 1e-8f;

    /* --- Channels 0-7: OHLCV (same as before) --- */
    out[0] = (c > o) ? 1.0f : 0.0f;
    out[1] = (c < o) ? 1.0f : 0.0f;

    float body = fabsf(c - o);
    out[2] = (body / spread < 1.0f) ? (body / spread) : 1.0f;
    out[3] = ((h - (o > c ? o : c)) / spread);
    if (out[3] > 1.0f) out[3] = 1.0f;
    if (out[3] < 0.0f) out[3] = 0.0f;

    out[4] = (((o < c ? o : c) - l) / spread);
    if (out[4] > 1.0f) out[4] = 1.0f;
    if (out[4] < 0.0f) out[4] = 0.0f;

    vol_hist[*vol_len % 20] = v;
    (*vol_len)++;
    int n = (*vol_len < 20) ? *vol_len : 20;
    float vol_sum = 0.0f;
    for (int i = 0; i < n; i++) vol_sum += vol_hist[i];
    float vol_sma = vol_sum / (float)n;
    if (vol_sma < 1e-8f) vol_sma = v;
    out[5] = (v / vol_sma < 3.0f) ? (v / vol_sma) : 3.0f;

    out[6] = (c - o) / spread;
    if (out[6] > 1.0f) out[6] = 1.0f;
    if (out[6] < -1.0f) out[6] = -1.0f;

    out[7] = (c - l) / spread;

    /* --- Channels 8-10: Order Book (default to 0 when NULL) --- */
    if (order_book) {
        /* Channel 8: Book imbalance (-1 to +1) */
        float total = order_book[0] + order_book[1] + 1e-8f;
        out[8] = (order_book[0] - order_book[1]) / total;

        /* Channel 9: Spread normalized (0 to 1) */
        float book_bid = order_book[2] > 0 ? order_book[2] : c;
        float book_ask = order_book[3] > 0 ? order_book[3] : c;
        out[9] = (book_ask - book_bid) / book_bid;
        if (out[9] > 0.05f) out[9] = 0.05f;  /* cap extreme spreads */

        /* Channel 10: Wall pressure (bid dominance vs ask dominance) */
        out[10] = (order_book[4] - order_book[5]) / (order_book[4] + order_book[5] + 1e-8f);
    } else {
        out[8] = 0.0f;
        out[9] = 0.0f;
        out[10] = 0.0f;
    }

    /* --- Channels 11-13: Trade Tape (default to 0 when NULL) --- */
    if (trade_tape) {
        /* Channel 11: CVD (Cumulative Volume Delta) [-1 to 1] */
        float total_vol = trade_tape[0] + trade_tape[1] + 1e-8f;
        out[11] = (trade_tape[0] - trade_tape[1]) / total_vol;

        /* Channel 12: Trade intensity (0 to 3) */
        out[12] = trade_tape[2] / 100.0f;  /* normalize: ~100 trades/5min = normal */
        if (out[12] > 3.0f) out[12] = 3.0f;

        /* Channel 13: Large trade ratio (0 to 1) */
        out[13] = trade_tape[3];
    } else {
        out[11] = 0.0f;
        out[12] = 0.0f;
        out[13] = 0.0f;
    }
}

/* ==================== Neuron Forward ==================== */

static int neuron_forward(Neuron* n, const float* input_vec, int input_size, int n_active) {
    if (n->refr_counter > 0) {
        n->refr_counter--;
        n->output = 0.0f;
        return 0;
    }

    float unfolded1[UNFOLD_SIZE];
    float compressed1[NUCLEUS_SIZE];
    float unfolded2[UNFOLD_SIZE];
    float state[NUCLEUS_SIZE];

    /* Level 1 (or 3): nucleus[64] -> unfolded[256] -> compress -> features[64] */
archive_unfold(n->nucleus, NUCLEUS_SIZE, unfolded1, UNFOLD_SIZE, 1);
    archive_compress(unfolded1, UNFOLD_SIZE, compressed1, NUCLEUS_SIZE);

    archive_unfold(compressed1, NUCLEUS_SIZE, unfolded2, UNFOLD_SIZE, 2);
    archive_compress(unfolded2, UNFOLD_SIZE, state, NUCLEUS_SIZE);

    float delta = 0.0f;
    int limit = (input_size < SENSORY) ? input_size : SENSORY;
    for (int i = 0; i < limit; i++) {
        delta += input_vec[i] * state[i];
    }
    int divisor = (n_active > 0) ? n_active : input_size;
    delta = delta / (float)divisor + n->bias;
    n->potential += delta;

    if (n->potential >= n->threshold) {
        n->output = n->potential;
        n->potential = 0.0f;
        n->refr_counter = (int)n->refractory;
        n->threshold = 0.5f;
        return 1;
    } else {
        n->output = 0.0f;
        n->potential *= 0.99f;
        return 0;
    }
}

/* ==================== R-STDP Operations ==================== */

static void rstpd_init(RSTDPState* s, float lr, float tau) {
    s->lr = lr;
    s->lr_0 = lr;
    s->decay = expf(-1.0f / tau);
    s->reward_k = 10.0f;
    s->fee_pct = 0.002f;
    s->micro_lr_scale = 0.1f;
    s->total_pnl = 0.0f;
    s->trades = 0;
    s->wins = 0;
    s->trades_total = 0;
    s->running_pnl_sum = 0.0f;
    s->running_pnl_sq = 0.0f;
    s->running_count = 0;
}

static void rstpd_accumulate_one(Neuron* n, const float* input_vec, int input_size) {
    float dt = n->output - 0.5f;
    float scale = dt * expf(-fabsf(dt));
    int n_elems = (input_size < NUCLEUS_SIZE) ? input_size : NUCLEUS_SIZE;
    for (int i = 0; i < n_elems; i++) {
        n->eligibility[i] += input_vec[i] * scale;
    }
}

static void rstpd_decay_one(Neuron* n) {
    for (int i = 0; i < NUCLEUS_SIZE; i++) {
        n->eligibility[i] *= g_rstdp.decay;
    }
}

static void rstpd_micro_reward_one(Neuron* n, float prev_pnl, float curr_pnl) {
    float change = curr_pnl - prev_pnl;
    float reward = tanhf(g_rstdp.reward_k * 0.3f * change);
    float lr_eff = g_rstdp.lr * g_rstdp.micro_lr_scale;
    for (int i = 0; i < NUCLEUS_SIZE; i++) {
n->velocity[i] = 0.9f * n->velocity[i] + lr_eff * n->eligibility[i] * reward;
            n->nucleus[i] += n->velocity[i];
            if (n->nucleus[i] > 10.0f) n->nucleus[i] = 10.0f;
            if (n->nucleus[i] < -10.0f) n->nucleus[i] = -10.0f;
        }
    }

static void rstpd_commit_one(Neuron* n, float pnl_pct, int side) {
    float net = pnl_pct * (float)side - g_rstdp.fee_pct;

    /* Sharpe-driven reward: first 5 trades use simple reward, then normalized */
    g_rstdp.running_pnl_sum += net;
    g_rstdp.running_pnl_sq += net * net;
    g_rstdp.running_count++;
    float reward;
    if (g_rstdp.running_count < 5) {
        reward = tanhf(g_rstdp.reward_k * net);  /* simple reward for early trades */
    } else {
    float avg = g_rstdp.running_pnl_sum / (float)g_rstdp.running_count;
    float variance = (g_rstdp.running_pnl_sq / (float)g_rstdp.running_count) - avg * avg;
    float std = sqrtf(variance < 0.0f ? 0.0f : variance);
    float denominator = std < 0.01f ? 0.01f : std;
    float normalized = (net - avg) / denominator;
    float reward = tanhf(g_rstdp.reward_k * normalized);
    }

    for (int i = 0; i < NUCLEUS_SIZE; i++) {
        n->velocity[i] = 0.9f * n->velocity[i] + g_rstdp.lr * n->eligibility[i] * reward;
        n->nucleus[i] += n->velocity[i];
        /* Clamp to [-10, +10] */
        if (n->nucleus[i] > 10.0f) n->nucleus[i] = 10.0f;
        if (n->nucleus[i] < -10.0f) n->nucleus[i] = -10.0f;
        n->eligibility[i] = 0.0f;
    }
    g_rstdp.total_pnl += net;
    g_rstdp.trades++;
    g_rstdp.trades_total++;
    if (net > 0) g_rstdp.wins++;
    g_rstdp.lr = g_rstdp.lr_0 / (1.0f + 0.005f * (float)g_rstdp.trades_total);
    if (g_rstdp.lr < 0.002f) g_rstdp.lr = 0.002f;  /* minimum lr */
}

/* ==================== Full Backtest in C ==================== */

/*
 * snn_backtest — run full backtest on OHLCV data.
 *
 * Input:
 *   data[N][5]: OHLCV array (float, row-major: O,H,L,C,V)
 *   n_candles: number of rows
 *   warm_weights: optional initial nucleus data (TOTAL_N * NUCLEUS_SIZE floats) or NULL
 *   lr, tau, sl, tp: hyperparameters
 *   leverage: position leverage multiplier
 *   use_micro: 1 to enable micro-rewards, 0 to disable
 *
 * Output (via pointers):
 *   trades, wins, total_pnl (sum of leveraged returns)
 *   weights_out: pre-allocated float[TOTAL_N * NUCLEUS_SIZE] or NULL
 *   winrate_out, risk_score_out
 */
EXPORT void snn_backtest(
    const float* data, int n_candles,
    const float* warm_weights,
    float lr, float tau, float sl, float tp, int leverage, int use_micro,
    int* trades_out, int* wins_out, float* total_pnl_out,
    float* weights_out, float* winrate_out, float* risk_score_out)
{
    /* Init neurons */
    static int seeded = 0;
    if (!seeded) { srand((unsigned int)time(NULL) ^ 42); seeded = 1; }

    if (warm_weights) {
        for (int i = 0; i < TOTAL_N; i++) {
            memcpy(g_neurons[i].nucleus, &warm_weights[i * NUCLEUS_SIZE],
                   NUCLEUS_SIZE * sizeof(float));
        }
    } else {
        float xavier_scale = sqrtf(6.0f / (float)(NUCLEUS_SIZE + NUCLEUS_SIZE));
        for (int i = 0; i < TOTAL_N; i++) {
            for (int j = 0; j < NUCLEUS_SIZE; j++) {
                g_neurons[i].nucleus[j] = ((float)rand() / (float)RAND_MAX - 0.5f) * 2.0f * 4.0f;
            }
        }
    }

    for (int i = 0; i < TOTAL_N; i++) {
        g_neurons[i].bias = (i < BUY_N) ? 0.3f : 0.0f;  /* BUY=0.3, SELL=0.0 */
        g_neurons[i].potential = 0.0f;
        g_neurons[i].threshold = 0.5f;
        g_neurons[i].refractory = 0.0f;
        g_neurons[i].refr_counter = 0;
        g_neurons[i].output = 0.0f;
        memset(g_neurons[i].eligibility, 0, NUCLEUS_SIZE * sizeof(float));
        memset(g_neurons[i].velocity, 0, NUCLEUS_SIZE * sizeof(float));
    }

    for (int i = 0; i < TOTAL_N; i++) g_active_mask[i] = 1.0f;
    rstpd_init(&g_rstdp, lr, tau);

    /* State */
    int pos = 0;
    float entry_price = 0.0f;
    float prev_pnl = 0.0f;
    int has_prev = 0;
    int trades = 0, wins = 0;
    float pnl_sum = 0.0f;
    float vol_hist[20] = {0};
    int vol_len = 0;
    int split = (int)(n_candles * 0.8f);

    

    /* Process candles */
    for (int phase = 0; phase < 2; phase++) {
        int start = (phase == 0) ? 5 : split;
        int end = (phase == 0) ? split : n_candles;
        float phase_pnl_sum = 0.0f;
        int phase_trades = 0;
        int phase_wins = 0;

        for (int c = start; c < end; c++) {
            float o = data[c * 5 + 0];
            float h = data[c * 5 + 1];
            float l = data[c * 5 + 2];
            float cl = data[c * 5 + 3];
            float v = data[c * 5 + 4];

            float spikes[SENSORY];
            encode_features(o, h, l, cl, v, vol_hist, &vol_len, spikes, NULL, NULL);

            /* Forward pass */
            float buy_out[BUY_N];
            float sell_out[SELL_N];
            float neg_spikes[SENSORY];
            for (int i = 0; i < SENSORY; i++) neg_spikes[i] = -spikes[i];

            for (int i = 0; i < BUY_N; i++) {
                neuron_forward(&g_neurons[i], spikes, SENSORY, 8);
                buy_out[i] = g_neurons[i].output;
            }
            for (int i = 0; i < SELL_N; i++) {
                neuron_forward(&g_neurons[BUY_N + i], neg_spikes, SENSORY, 8);
                sell_out[i] = g_neurons[BUY_N + i].output;
            }

            /* Compute buy/sell max */
            float buy_max = buy_out[0];
            for (int i = 1; i < BUY_N; i++) {
                if (buy_out[i] > buy_max) buy_max = buy_out[i];
            }
            float sell_max = sell_out[0];
            for (int i = 1; i < SELL_N; i++) {
                if (sell_out[i] > sell_max) sell_max = sell_out[i];
            }
            float th = g_neurons[0].threshold;

            int action = 0;
            if (buy_max > th && buy_max >= sell_max) action = 1;
            else if (sell_max > th && sell_max > buy_max) action = -1;

            /* Trading logic */
            if (pos == 0) {
                if (action != 0) {
                    pos = action;
                    entry_price = cl;
                    has_prev = 0;
                } else {
                    for (int i = 0; i < TOTAL_N; i++) {
                        rstpd_decay_one(&g_neurons[i]);
                    }
                    /* Hebbian idle: reinforce firing patterns even without position */
                    for (int i = 0; i < BUY_N; i++) {
                        if (g_neurons[i].output > 0.0f) {
                            for (int j = 0; j < SENSORY; j++)
                                g_neurons[i].nucleus[j] += 0.0005f * spikes[j] * g_neurons[i].output;
                        }
                    }
                    for (int i = 0; i < SELL_N; i++) {
                        int idx = BUY_N + i;
                        if (g_neurons[idx].output > 0.0f) {
                            for (int j = 0; j < SENSORY; j++)
                                g_neurons[idx].nucleus[j] += 0.0005f * neg_spikes[j] * g_neurons[idx].output;
                        }
                    }
                    /* L2 weight decay */
                    for (int i = 0; i < TOTAL_N; i++) {
                        for (int j = 0; j < NUCLEUS_SIZE; j++)
                            g_neurons[i].nucleus[j] *= 0.999f;
                    }
                }
            } else {
                float pnl_raw = (cl - entry_price) / entry_price;
                float curr = (pos == 1) ? pnl_raw : -pnl_raw;
                float curr_levered = curr * (float)leverage;

                for (int i = 0; i < BUY_N; i++) {
                    rstpd_accumulate_one(&g_neurons[i], spikes, SENSORY);
                }
                for (int i = 0; i < SELL_N; i++) {
                    rstpd_accumulate_one(&g_neurons[BUY_N + i], neg_spikes, SENSORY);
                }

                if (use_micro && has_prev) {
                    for (int i = 0; i < TOTAL_N; i++) {
                        rstpd_micro_reward_one(&g_neurons[i], prev_pnl, curr_levered);
                    }
                }
                prev_pnl = curr_levered;
                has_prev = 1;

                for (int i = 0; i < TOTAL_N; i++) {
                    rstpd_decay_one(&g_neurons[i]);
                }

                int close = 0;
                if (sl > 0.0f && curr_levered <= -sl) close = 1;
                else if (tp > 0.0f && curr_levered >= tp) close = 1;
                else if ((pos == 1 && action == -1) || (pos == -1 && action == 1)) close = 1;

                if (close) {
                    for (int i = 0; i < TOTAL_N; i++) {
                        rstpd_commit_one(&g_neurons[i], pnl_raw, pos);
                    }
                    pos = 0;
                    has_prev = 0;
                    phase_trades++;
                    phase_pnl_sum += curr_levered;
                    if (curr_levered > 0.0f) phase_wins++;
                }
            }
        }

        if (phase == 1) {
            trades = phase_trades;
            wins = phase_wins;
            pnl_sum = phase_pnl_sum;
        }
    }

    /* Compute risk score from test phase PnLs */
    float avg_pnl = (trades > 0) ? (pnl_sum / (float)trades) : 0.0f;
    float std_pnl = (trades > 1) ? fabsf(avg_pnl) + 0.001f : fabsf(avg_pnl) + 0.001f;
    float wr = (trades > 0) ? ((float)wins / (float)trades) : 0.0f;
    float risk_score = wr * avg_pnl * sqrtf((float)(trades > 0 ? trades : 1)) / (std_pnl + 0.001f);

    *trades_out = trades;
    *wins_out = wins;
    *total_pnl_out = pnl_sum;
    *winrate_out = wr;
    *risk_score_out = risk_score;

    /* Export weights */
    if (weights_out) {
        for (int i = 0; i < TOTAL_N; i++) {
            memcpy(&weights_out[i * NUCLEUS_SIZE],
                   g_neurons[i].nucleus,
                   NUCLEUS_SIZE * sizeof(float));
        }
    }
}


/* ==================== Live Trading API ==================== */
/* These are called from Python on each candle (for live trading, not backtest) */

EXPORT void snn_init_live(const float* nucleus_data, float lr, float tau) {
    static int seeded = 0;
    if (!seeded) { srand((unsigned int)time(NULL)); seeded = 1; }

    if (nucleus_data) {
        for (int i = 0; i < TOTAL_N; i++) {
            memcpy(g_neurons[i].nucleus, &nucleus_data[i * NUCLEUS_SIZE],
                   NUCLEUS_SIZE * sizeof(float));
        }
    } else {
        float xavier_scale = sqrtf(6.0f / (float)(NUCLEUS_SIZE + NUCLEUS_SIZE));
        for (int i = 0; i < TOTAL_N; i++) {
            for (int j = 0; j < NUCLEUS_SIZE; j++) {
                g_neurons[i].nucleus[j] = ((float)rand() / (float)RAND_MAX - 0.5f) * 2.0f * 4.0f;
            }
        }
    }

    for (int i = 0; i < TOTAL_N; i++) {
        g_neurons[i].bias = (i < BUY_N) ? 0.3f : 0.0f;  /* BUY=0.3, SELL=0.0 */
        g_neurons[i].potential = 0.0f;
        g_neurons[i].threshold = 0.5f;
        g_neurons[i].refractory = 0.0f;
        g_neurons[i].refr_counter = 0;
        g_neurons[i].output = 0.0f;
        memset(g_neurons[i].eligibility, 0, NUCLEUS_SIZE * sizeof(float));
        memset(g_neurons[i].velocity, 0, NUCLEUS_SIZE * sizeof(float));
    }
    /* Init active mask: 16 BUY + 16 SELL active, 4 reserve */
    for (int i = 0; i < 16; i++) g_active_mask[i] = 1.0f;
    for (int i = 16; i < 18; i++) g_active_mask[i] = 0.0f;
    for (int i = 18; i < 34; i++) g_active_mask[i] = 1.0f;
    for (int i = 34; i < 36; i++) g_active_mask[i] = 0.0f;
    rstpd_init(&g_rstdp, lr, tau);
}

EXPORT void snn_forward_live(const float* spikes, float* buy_out, float* sell_out, float* threshold) {
    float neg_spikes[SENSORY];
    for (int i = 0; i < SENSORY; i++) neg_spikes[i] = -spikes[i];

    for (int i = 0; i < BUY_N; i++) {
        neuron_forward(&g_neurons[i], spikes, SENSORY, SENSORY);
        buy_out[i] = (g_active_mask[i] > 0.5f) ? g_neurons[i].output : 0.0f;
    }
    for (int i = 0; i < SELL_N; i++) {
        neuron_forward(&g_neurons[BUY_N + i], neg_spikes, SENSORY, SENSORY);
        sell_out[i] = (g_active_mask[BUY_N + i] > 0.5f) ? g_neurons[BUY_N + i].output : 0.0f;
    }
    *threshold = g_neurons[0].threshold;
}

EXPORT void snn_accumulate_live(const float* spikes) {
    float neg_spikes[SENSORY];
    for (int i = 0; i < SENSORY; i++) neg_spikes[i] = -spikes[i];

    for (int i = 0; i < BUY_N; i++) {
        if (g_active_mask[i] > 0.5f)
            rstpd_accumulate_one(&g_neurons[i], spikes, SENSORY);
    }
    for (int i = 0; i < SELL_N; i++) {
        int idx = BUY_N + i;
        if (g_active_mask[idx] > 0.5f)
            rstpd_accumulate_one(&g_neurons[idx], neg_spikes, SENSORY);
    }
}

EXPORT void snn_decay_all(void) {
    for (int i = 0; i < TOTAL_N; i++)
        if (g_active_mask[i] > 0.5f)
            rstpd_decay_one(&g_neurons[i]);
}

EXPORT void snn_hebbian_idle(const float* spikes, float lr_hebb) {
    /* Hebbian reinforcement when pos=0: strengthen patterns that activate neurons */
    float neg_spikes[SENSORY];
    for (int i = 0; i < SENSORY; i++) neg_spikes[i] = -spikes[i];
    for (int i = 0; i < BUY_N; i++) {
        if (g_neurons[i].output > 0.0f) {
            for (int j = 0; j < SENSORY; j++)
                g_neurons[i].nucleus[j] += lr_hebb * spikes[j] * g_neurons[i].output;
        }
    }
    for (int i = 0; i < SELL_N; i++) {
        int idx = BUY_N + i;
        if (g_neurons[idx].output > 0.0f) {
            for (int j = 0; j < SENSORY; j++)
                g_neurons[idx].nucleus[j] += lr_hebb * neg_spikes[j] * g_neurons[idx].output;
        }
    }
    /* L2 weight decay to prevent divergence */
    for (int i = 0; i < TOTAL_N; i++) {
        for (int j = 0; j < NUCLEUS_SIZE; j++)
            g_neurons[i].nucleus[j] *= 0.999f;
    }
}

EXPORT void snn_micro_reward_all(float prev_pnl, float curr_pnl) {
    for (int i = 0; i < TOTAL_N; i++) {
        if (g_active_mask[i] > 0.5f)
            rstpd_micro_reward_one(&g_neurons[i], prev_pnl, curr_pnl);
    }
}

EXPORT float snn_commit_all(float pnl_pct, int side) {
    for (int i = 0; i < TOTAL_N; i++) {
        if (g_active_mask[i] > 0.5f)
            rstpd_commit_one(&g_neurons[i], pnl_pct, side);
    }
    /* return reward */
    float avg_net = g_rstdp.total_pnl / (float)(g_rstdp.trades > 0 ? g_rstdp.trades : 1);
    return tanhf(g_rstdp.reward_k * avg_net);
}

EXPORT void snn_get_weights_live(float* buf) {
    for (int i = 0; i < TOTAL_N; i++) {
        memcpy(&buf[i * NUCLEUS_SIZE], g_neurons[i].nucleus, NUCLEUS_SIZE * sizeof(float));
    }
}

EXPORT void snn_get_rstdp_state_live(float* lr, float* total_pnl, int* trades, int* wins) {
    *lr = g_rstdp.lr;
    *total_pnl = g_rstdp.total_pnl;
    *trades = g_rstdp.trades;
    *wins = g_rstdp.wins;
}

/*
 * Full state save/load — preserves neuron membrane + eligibility + RSTDP
 * Layout per neuron (TOTAL_N times):
 *   nucleus[NUCLEUS_SIZE], bias(1), potential(1), threshold(1), refractory(1),
 *   refr_counter(1), output(1), eligibility[NUCLEUS_SIZE], velocity[NUCLEUS_SIZE]
 * Then RSTDP state:
 *   lr(1), total_pnl(1), trades(1), wins(1), trades_total(1),
 *   running_pnl_sum(1), running_pnl_sq(1), running_count(1),
 *   active_mask[36]
 * Total floats = TOTAL_N * (NUCLEUS_SIZE + 6 + NUCLEUS_SIZE + NUCLEUS_SIZE) + 8 + 36
 *              = 36 * (64 + 6 + 64 + 64) + 44 = 36 * 198 + 44 = 7172
 */

#define STATE_PER_NEURON (NUCLEUS_SIZE + 6 + NUCLEUS_SIZE + NUCLEUS_SIZE)  /* 198 */
#define STATE_TOTAL (TOTAL_N * STATE_PER_NEURON + 44)                        /* 7172 */

EXPORT int snn_save_state(float* buf) {
    int pos = 0;
    for (int i = 0; i < TOTAL_N; i++) {
        /* nucleus */
        for (int j = 0; j < NUCLEUS_SIZE; j++) buf[pos + j] = g_neurons[i].nucleus[j];
        pos += NUCLEUS_SIZE;
        /* scalar state */
        buf[pos++] = g_neurons[i].bias;
        buf[pos++] = g_neurons[i].potential;
        buf[pos++] = g_neurons[i].threshold;
        buf[pos++] = g_neurons[i].refractory;
        buf[pos++] = (float)g_neurons[i].refr_counter;
        buf[pos++] = g_neurons[i].output;
        /* eligibility */
        for (int j = 0; j < NUCLEUS_SIZE; j++) buf[pos + j] = g_neurons[i].eligibility[j];
        pos += NUCLEUS_SIZE;
        /* velocity */
        for (int j = 0; j < NUCLEUS_SIZE; j++) buf[pos + j] = g_neurons[i].velocity[j];
        pos += NUCLEUS_SIZE;
    }
    /* RSTDP state */
    buf[pos++] = g_rstdp.lr;
    buf[pos++] = g_rstdp.total_pnl;
    buf[pos++] = (float)g_rstdp.trades;
    buf[pos++] = (float)g_rstdp.wins;
    buf[pos++] = (float)g_rstdp.trades_total;
    buf[pos++] = g_rstdp.running_pnl_sum;
    buf[pos++] = g_rstdp.running_pnl_sq;
    buf[pos++] = (float)g_rstdp.running_count;
    /* active mask */
    for (int i = 0; i < TOTAL_N; i++) buf[pos++] = g_active_mask[i];
    return pos;
}

EXPORT void snn_load_state(const float* buf, int load_eligibility, int load_membrane) {
    int pos = 0;
    for (int i = 0; i < TOTAL_N; i++) {
        /* nucleus */
        for (int j = 0; j < NUCLEUS_SIZE; j++) {
            g_neurons[i].nucleus[j] = buf[pos + j];
            if (g_neurons[i].nucleus[j] > 10.0f) g_neurons[i].nucleus[j] = 10.0f;
            if (g_neurons[i].nucleus[j] < -10.0f) g_neurons[i].nucleus[j] = -10.0f;
        }
        pos += NUCLEUS_SIZE;
        if (load_membrane) {
            g_neurons[i].bias = buf[pos++];
            g_neurons[i].potential = buf[pos++];
            g_neurons[i].threshold = buf[pos++];
            g_neurons[i].refractory = buf[pos++];
            g_neurons[i].refr_counter = (int)buf[pos++];
            g_neurons[i].output = buf[pos++];
        } else {
            pos += 6;
        }
        /* eligibility */
        if (load_eligibility) {
            for (int j = 0; j < NUCLEUS_SIZE; j++) g_neurons[i].eligibility[j] = buf[pos + j];
        }
        pos += NUCLEUS_SIZE;
        /* velocity */
        if (load_eligibility) {
            for (int j = 0; j < NUCLEUS_SIZE; j++) g_neurons[i].velocity[j] = buf[pos + j];
        }
        pos += NUCLEUS_SIZE;
    }
    /* RSTDP state */
    if (load_eligibility) {
        g_rstdp.lr = buf[pos++];
        g_rstdp.total_pnl = buf[pos++];
        g_rstdp.trades = (int)buf[pos++];
        g_rstdp.wins = (int)buf[pos++];
        g_rstdp.trades_total = (int)buf[pos++];
        g_rstdp.running_pnl_sum = buf[pos++];
        g_rstdp.running_pnl_sq = buf[pos++];
        g_rstdp.running_count = (int)buf[pos++];
    }
    /* active mask */
    if (load_eligibility) {
        for (int i = 0; i < TOTAL_N; i++) g_active_mask[i] = buf[pos + i];
    }
    pos += TOTAL_N;
}

/* ==================== EvoBrain API ==================== */

EXPORT void snn_activate_neuron(int idx) {
    if (idx >= 0 && idx < TOTAL_N) {
        g_active_mask[idx] = 1.0f;
        memset(g_neurons[idx].eligibility, 0, NUCLEUS_SIZE * sizeof(float));
        memset(g_neurons[idx].velocity, 0, NUCLEUS_SIZE * sizeof(float));
        g_neurons[idx].potential = 0.0f;
        g_neurons[idx].threshold = 0.5f;
        g_neurons[idx].refr_counter = 0;
    }
}

EXPORT void snn_deactivate_neuron(int idx) {
    if (idx >= 0 && idx < TOTAL_N) {
        g_active_mask[idx] = 0.0f;
    }
}

EXPORT void snn_mutate_neuron(int target, int source, float sigma) {
    if (target < 0 || target >= TOTAL_N || source < 0 || source >= TOTAL_N) return;
    if (target == source) return;
    static int seeded = 0;
    if (!seeded) { srand((unsigned int)time(NULL) ^ 42); seeded = 1; }
    for (int j = 0; j < NUCLEUS_SIZE; j++) {
        float r = ((float)rand() / (float)RAND_MAX - 0.5f) * 2.0f;  /* [-1, 1] */
        float v = g_neurons[source].nucleus[j] + r * sigma * 4.0f;
        if (v > 4.0f) v = 4.0f;
        if (v < -4.0f) v = -4.0f;
        g_neurons[target].nucleus[j] = v;
    }
    memset(g_neurons[target].eligibility, 0, NUCLEUS_SIZE * sizeof(float));
    memset(g_neurons[target].velocity, 0, NUCLEUS_SIZE * sizeof(float));
    g_neurons[target].potential = 0.0f;
    g_neurons[target].threshold = 0.5f;
}

EXPORT void snn_get_active_mask(float* buf) {
    for (int i = 0; i < TOTAL_N; i++) buf[i] = g_active_mask[i];
}

EXPORT void snn_set_learning_params(float lr, float tau) {
    g_rstdp.lr = lr;
    g_rstdp.lr_0 = lr;
    g_rstdp.decay = expf(-1.0f / tau);
}

EXPORT void snn_set_global_bias(float bias) {
    for (int i = 0; i < TOTAL_N; i++) {
        g_neurons[i].bias = bias;
    }
}

EXPORT void snn_reinforce(int punish) {
    /* Predictive reward: reinforce or punish neurons that fired on previous candle.
       reinforce (punish=0): multiply nucleus by 1.01
       punish (punish=1):    multiply nucleus by 0.99
       Clamp to [-10, +10]. */
    float factor = punish ? 0.99f : 1.01f;
    for (int i = 0; i < TOTAL_N; i++) {
        if (g_neurons[i].output > 0.0f) {  /* only adjust neurons that fired */
            for (int j = 0; j < NUCLEUS_SIZE; j++) {
                g_neurons[i].nucleus[j] *= factor;
                if (g_neurons[i].nucleus[j] > 10.0f) g_neurons[i].nucleus[j] = 10.0f;
                if (g_neurons[i].nucleus[j] < -10.0f) g_neurons[i].nucleus[j] = -10.0f;
            }
        }
    }
}