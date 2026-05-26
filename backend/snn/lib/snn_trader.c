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
#define BUY_N          16
#define SELL_N         16
#define TOTAL_N        (BUY_N + SELL_N)
#define UNFOLD_SIZE    (NUCLEUS_SIZE * 4)
#define SENSORY        8
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
} RSTDPState;

/* ==================== Global State ==================== */
static Neuron g_neurons[TOTAL_N];
static RSTDPState g_rstdp;

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

/* ==================== OHLCV Encoding ==================== */

static void encode_ohlcv(float o, float h, float l, float c, float v,
                         float* vol_hist, int* vol_len, float* out) {
    float spread = h - l;
    if (spread < 1e-8f) spread = 1e-8f;

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

    /* Volume moving average */
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
}

/* ==================== Neuron Forward ==================== */

static int neuron_forward(Neuron* n, const float* input_vec, int input_size) {
    if (n->refr_counter > 0) {
        n->refr_counter--;
        n->output = 0.0f;
        return 0;
    }

    float unfolded1[UNFOLD_SIZE];
    float compressed1[NUCLEUS_SIZE];
    float unfolded2[UNFOLD_SIZE];
    float state[NUCLEUS_SIZE];

    /* Level 1: nucleus[64] -> unfolded[256] -> compress -> features[64] */
    archive_unfold(n->nucleus, NUCLEUS_SIZE, unfolded1, UNFOLD_SIZE, 1);
    archive_compress(unfolded1, UNFOLD_SIZE, compressed1, NUCLEUS_SIZE);

    /* Level 2: features[64] -> unfolded[256] -> compress -> state[64] */
    archive_unfold(compressed1, NUCLEUS_SIZE, unfolded2, UNFOLD_SIZE, 2);
    archive_compress(unfolded2, UNFOLD_SIZE, state, NUCLEUS_SIZE);

    float delta = 0.0f;
    int limit = (input_size < SENSORY) ? input_size : SENSORY;
    for (int i = 0; i < limit; i++) {
        delta += input_vec[i] * state[i];
    }
    delta = delta / (float)input_size + n->bias;
    n->potential += delta;

    if (n->potential >= n->threshold) {
        n->output = n->potential;
        n->potential = 0.0f;
        n->refr_counter = (int)n->refractory;
        n->threshold = 0.5f + (n->threshold - 0.5f) * 0.9f + 0.1f * fabsf(n->output);
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
        n->nucleus[i] += lr_eff * n->eligibility[i] * reward;
    }
}

static void rstpd_commit_one(Neuron* n, float pnl_pct, int side) {
    float net = pnl_pct * (float)side - g_rstdp.fee_pct;
    float reward = tanhf(g_rstdp.reward_k * net);
    for (int i = 0; i < NUCLEUS_SIZE; i++) {
        n->nucleus[i] += g_rstdp.lr * n->eligibility[i] * reward;
        n->eligibility[i] = 0.0f;
    }
    g_rstdp.total_pnl += net;
    g_rstdp.trades++;
    g_rstdp.trades_total++;
    if (net > 0) g_rstdp.wins++;
    g_rstdp.lr = g_rstdp.lr_0 / (1.0f + 0.005f * (float)g_rstdp.trades_total);
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
                g_neurons[i].nucleus[j] = ((float)rand() / (float)RAND_MAX - 0.5f) * 2.0f * xavier_scale;
            }
        }
    }

    for (int i = 0; i < TOTAL_N; i++) {
        g_neurons[i].bias = 1.0f;
        g_neurons[i].potential = 0.0f;
        g_neurons[i].threshold = 0.5f;
        g_neurons[i].refractory = 0.0f;
        g_neurons[i].refr_counter = 0;
        g_neurons[i].output = 0.0f;
        memset(g_neurons[i].eligibility, 0, NUCLEUS_SIZE * sizeof(float));
    }

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
            encode_ohlcv(o, h, l, cl, v, vol_hist, &vol_len, spikes);

            /* Forward pass */
            float buy_out[BUY_N];
            float sell_out[SELL_N];
            float neg_spikes[SENSORY];
            for (int i = 0; i < SENSORY; i++) neg_spikes[i] = -spikes[i];

            for (int i = 0; i < BUY_N; i++) {
                neuron_forward(&g_neurons[i], spikes, SENSORY);
                buy_out[i] = g_neurons[i].output;
            }
            for (int i = 0; i < SELL_N; i++) {
                neuron_forward(&g_neurons[BUY_N + i], neg_spikes, SENSORY);
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
                            g_neurons[i].nucleus[j] *= 0.99999f;
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
                g_neurons[i].nucleus[j] = ((float)rand() / (float)RAND_MAX - 0.5f) * 2.0f * xavier_scale;
            }
        }
    }

    for (int i = 0; i < TOTAL_N; i++) {
        g_neurons[i].bias = 1.0f;
        g_neurons[i].potential = 0.0f;
        g_neurons[i].threshold = 0.5f;
        g_neurons[i].refractory = 0.0f;
        g_neurons[i].refr_counter = 0;
        g_neurons[i].output = 0.0f;
        memset(g_neurons[i].eligibility, 0, NUCLEUS_SIZE * sizeof(float));
    }
    rstpd_init(&g_rstdp, lr, tau);
}

EXPORT void snn_forward_live(const float* spikes, float* buy_out, float* sell_out, float* threshold) {
    float neg_spikes[SENSORY];
    for (int i = 0; i < SENSORY; i++) neg_spikes[i] = -spikes[i];

    for (int i = 0; i < BUY_N; i++) {
        neuron_forward(&g_neurons[i], spikes, SENSORY);
        buy_out[i] = g_neurons[i].output;
    }
    for (int i = 0; i < SELL_N; i++) {
        neuron_forward(&g_neurons[BUY_N + i], neg_spikes, SENSORY);
        sell_out[i] = g_neurons[BUY_N + i].output;
    }
    *threshold = g_neurons[0].threshold;
}

EXPORT void snn_accumulate_live(const float* spikes) {
    float neg_spikes[SENSORY];
    for (int i = 0; i < SENSORY; i++) neg_spikes[i] = -spikes[i];

    for (int i = 0; i < BUY_N; i++) {
        rstpd_accumulate_one(&g_neurons[i], spikes, SENSORY);
    }
    for (int i = 0; i < SELL_N; i++) {
        rstpd_accumulate_one(&g_neurons[BUY_N + i], neg_spikes, SENSORY);
    }
}

EXPORT void snn_decay_all(void) {
    for (int i = 0; i < TOTAL_N; i++) rstpd_decay_one(&g_neurons[i]);
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
            g_neurons[i].nucleus[j] *= 0.99999f;
    }
}

EXPORT void snn_micro_reward_all(float prev_pnl, float curr_pnl) {
    for (int i = 0; i < TOTAL_N; i++) {
        rstpd_micro_reward_one(&g_neurons[i], prev_pnl, curr_pnl);
    }
}

EXPORT float snn_commit_all(float pnl_pct, int side) {
    for (int i = 0; i < TOTAL_N; i++) {
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
 *   refr_counter(1), output(1), eligibility[NUCLEUS_SIZE]
 * Then RSTDP state:
 *   lr(1), total_pnl(1), trades(1), wins(1), trades_total(1)
 * Total floats = TOTAL_N * (NUCLEUS_SIZE + 6 + NUCLEUS_SIZE) + 5
 *              = 16 * (64 + 6 + 64) + 5 = 16 * 134 + 5 = 2149
 */

#define STATE_PER_NEURON (NUCLEUS_SIZE + 6 + NUCLEUS_SIZE)  /* 134 */
#define STATE_TOTAL (TOTAL_N * STATE_PER_NEURON + 5)        /* 2149 */

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
    }
    /* RSTDP state */
    buf[pos++] = g_rstdp.lr;
    buf[pos++] = g_rstdp.total_pnl;
    buf[pos++] = (float)g_rstdp.trades;
    buf[pos++] = (float)g_rstdp.wins;
    buf[pos++] = (float)g_rstdp.trades_total;
    return pos;
}

EXPORT void snn_load_state(const float* buf, int load_eligibility, int load_membrane) {
    int pos = 0;
    for (int i = 0; i < TOTAL_N; i++) {
        /* nucleus */
        for (int j = 0; j < NUCLEUS_SIZE; j++) g_neurons[i].nucleus[j] = buf[pos + j];
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
    }
    /* RSTDP state */
    if (load_eligibility) {
        g_rstdp.lr = buf[pos++];
        g_rstdp.total_pnl = buf[pos++];
        g_rstdp.trades = (int)buf[pos++];
        g_rstdp.wins = (int)buf[pos++];
        g_rstdp.trades_total = (int)buf[pos++];
    }
}