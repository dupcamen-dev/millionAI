/* Crypto SNN Backtest — Million v0.3
   Loads BTCUSDT 5m data, encodes OHLCV, runs TradingNeurons, R-STDP.
   Direct forward pass (no event-driven overhead for trading).

   ARCHIVE_PROJ_FN: integer hash (fast, no cancelation in groups of 4)
   Override sinf in generated code.

   Compile:
     gcc -O3 -ffast-math -lm -o backtest.exe backtest.c \
       -DARCHIVE_PROJ_FN\(i,j,l\)=\(\(\(float\)\(\(int\)\(\(i\)*13\^\(j\)*7\^\(l\)*5\)%31-15\)/15.0f\)\)

   Run:
     ./backtest [data_file] [lr] [tau] [threshold] [fee_pct]

   Data format: [int32 count][float O,H,L,C,V] x count
*/
#include "generated_crypto.c"
#include "../../runtime/crypto_encode.h"
#include "../../runtime/rstdp.h"
#include <time.h>
#include <string.h>

#define NUM_TRADING 16

/* ---------- Sliding Window SMA for volume normalization ---------- */
typedef struct {
    float buf[20];
    int idx;
    int count;
} VolHistory;

static void volhist_init(VolHistory* vh) {
    memset(vh, 0, sizeof(VolHistory));
}

static void volhist_push(VolHistory* vh, float vol) {
    vh->buf[vh->idx] = vol;
    vh->idx = (vh->idx + 1) % 20;
    if (vh->count < 20) vh->count++;
}

/* ---------- Forward pass: bypass event-driven, call process directly ----------
   Neurons 0-7: BUY specialists (respond to bullish patterns)
   Neurons 8-15: SELL specialists (negated input ⇒ respond to bearish patterns) */
static void forward_trading_cortex(float* spikes, int num_channels) {
    float neg_spikes[8];
    for (int i = 0; i < num_channels; i++) neg_spikes[i] = -spikes[i];
    for (int i = 0; i < 8; i++)
        process_TradingNeuron(&TradingCortex_neurons[i], spikes, num_channels);
    for (int i = 8; i < 16; i++)
        process_TradingNeuron(&TradingCortex_neurons[i], neg_spikes, num_channels);
}

/* ---------- Trading State ---------- */
typedef enum { POS_NONE = 0, POS_LONG = 1, POS_SHORT = -1 } Position;

typedef struct {
    Position pos;
    float entry_price;
    int entry_candle;
    float pnl_total;            /* cumulative PnL */
    float trades;
    int wins;
    float equity;
    float initial_equity;
    float equity_curve[200000];
    int equity_len;
} TradeState;

static void trade_init(TradeState* ts, float initial_equity) {
    memset(ts, 0, sizeof(TradeState));
    ts->initial_equity = initial_equity;
    ts->equity = initial_equity;
}

/* ---------- Data Loading ---------- */
typedef struct {
    int count;
    float* data; /* [count][5]: O, H, L, C, V */
} OHLCVData;

static OHLCVData load_ohlcv(const char* path) {
    OHLCVData d = {0, NULL};
    FILE* fp = fopen(path, "rb");
    if (!fp) { printf("FAIL: %s\n", path); exit(1); }
    fread(&d.count, sizeof(int), 1, fp);
    d.data = (float*)malloc(d.count * 5 * sizeof(float));
    fread(d.data, sizeof(float), d.count * 5, fp);
    fclose(fp);
    return d;
}

/* ---------- Action Decision ---------- */
static int decide_action(float threshold) {
    float buy_max = 0.0f, sell_max = 0.0f;
    for (int i = 0; i < 8; i++) {
        if (TradingCortex_neurons[i].output > buy_max)
            buy_max = TradingCortex_neurons[i].output;
        if (TradingCortex_neurons[8 + i].output > sell_max)
            sell_max = TradingCortex_neurons[8 + i].output;
    }
    if (buy_max > threshold && buy_max >= sell_max) return 1;
    if (sell_max > threshold && sell_max >  buy_max) return -1;
    return 0;
}

/* ---------- Metrics ---------- */
static double sharpe_ratio(float* curve, int len) {
    if (len < 2) return 0.0;
    double mean = 0.0;
    for (int i = 0; i < len; i++) mean += curve[i];
    mean /= len;
    double var = 0.0;
    for (int i = 0; i < len; i++) var += (curve[i] - mean) * (curve[i] - mean);
    var /= (len - 1);
    if (var < 1e-10) return 0.0;
    return (mean / sqrt(var)) * sqrt(288.0 * 365.0);
}

static double max_drawdown(float* curve, int len) {
    double peak = -1e9, dd = 0;
    for (int i = 0; i < len; i++) {
        if (curve[i] > peak) peak = curve[i];
        double cur_dd = (peak - curve[i]) / peak;
        if (cur_dd > dd) dd = cur_dd;
    }
    return dd;
}

/* ---------- Single loop (used for both train and test) ----------
   stop_loss_pct: e.g. 0.05 = close at -5% loss
   take_profit_pct: e.g. 0.15 = close at +15% profit  */
static void run_loop(OHLCVData* ohlcv, int start, int end,
                     TradeState* ts, RSTDPState* rstdp,
                     int* trade_count_out, int* win_count_out,
                     float* pnl_total_out,
                     float tau, float thresh, int print_trades,
                     float stop_loss_pct, float take_profit_pct) {
    VolHistory vh;
    volhist_init(&vh);

    float spikes[SENSORY_CHANNELS];
    int trades = 0, wins = 0;
    float pnl_sum = 0.0f;

    for (int c = start; c < end; c++) {
        float* ohlc = &ohlcv->data[c * 5];
        float o = ohlc[0], h = ohlc[1], l = ohlc[2], cl = ohlc[3], v = ohlc[4];

        encode_ohlcv(o, h, l, cl, v, vh.buf, vh.idx, vh.count, spikes);
        volhist_push(&vh, v);

        /* Forward pass */
        forward_trading_cortex(spikes, SENSORY_CHANNELS);
        int action = decide_action(thresh);

        /* Trade logic */
        if (ts->pos == POS_NONE) {
            if (action == 1) {
                ts->pos = POS_LONG;
                ts->entry_price = cl;
                ts->entry_candle = c;
                if (print_trades) printf("Candle %d: BUY at %.2f\n", c, cl);
            } else if (action == -1) {
                ts->pos = POS_SHORT;
                ts->entry_price = cl;
                ts->entry_candle = c;
                if (print_trades) printf("Candle %d: SELL at %.2f\n", c, cl);
            }
            /* Decay all eligibility traces (no position = no accumulation) */
            for (int i = 0; i < NUM_TRADING; i++) rstdp_decay(&rstdp[i]);
        } else {
            /* In position: accumulate eligibility from all neurons */
            for (int i = 0; i < NUM_TRADING; i++) {
                rstdp_accumulate(&rstdp[i],
                                 TradingCortex_neurons[i].nucleus,
                                 spikes, SENSORY_CHANNELS,
                                 TradingCortex_neurons[i].output);
                rstdp_decay(&rstdp[i]);
            }

            /* Check for close: SL/TP takes priority over signal */
            float pnl_raw = (cl - ts->entry_price) / ts->entry_price;
            float pnl_with_sign = (ts->pos == POS_LONG) ? pnl_raw : -pnl_raw;

            int close_signal = 0;
            const char* close_reason = "SIGNAL";
            if (stop_loss_pct > 0 && pnl_with_sign <= -stop_loss_pct) {
                close_signal = 1; close_reason = "SL";
            } else if (take_profit_pct > 0 && pnl_with_sign >= take_profit_pct) {
                close_signal = 1; close_reason = "TP";
            } else if (ts->pos == POS_LONG && action == -1) {
                close_signal = 1;
            } else if (ts->pos == POS_SHORT && action == 1) {
                close_signal = 1;
            }

            if (close_signal) {
                /* Apply R-STDP to all neurons */
                float total_reward = 0.0f;
                for (int i = 0; i < NUM_TRADING; i++) {
                    total_reward += rstdp_commit(&rstdp[i],
                                  TradingCortex_neurons[i].nucleus,
                                  pnl_raw, (int)ts->pos);
                }
                total_reward /= (float)NUM_TRADING;

                /* Update equity */
                ts->equity *= (1.0f + pnl_with_sign);
                trades++;
                if (pnl_with_sign > 0) wins++;
                pnl_sum += pnl_with_sign;

                if (print_trades)
                    printf("Candle %d: %s at %.2f, PnL=%.4f%%, reward=%.4f, equity=%.2f\n",
                           c, close_reason, cl, pnl_with_sign * 100, total_reward, ts->equity);

                ts->pos = POS_NONE;
            }
        }

        /* Track equity curve (sample every 100 candles) */
        if (c % 100 == 0 && ts->equity_len < 200000) {
            if (ts->pos != POS_NONE) {
                float pnl = (cl - ts->entry_price) / ts->entry_price;
                float unrealized = (ts->pos == POS_LONG) ? pnl : -pnl;
                ts->equity_curve[ts->equity_len++] = ts->equity * (1.0f + unrealized);
            } else {
                ts->equity_curve[ts->equity_len++] = ts->equity;
            }
        }
    }

    /* Force close any open position at end of loop */
    if (ts->pos != POS_NONE) {
        float* last = &ohlcv->data[(end - 1) * 5];
        float pnl_raw = (last[3] - ts->entry_price) / ts->entry_price;
        for (int i = 0; i < NUM_TRADING; i++)
            rstdp_commit(&rstdp[i], TradingCortex_neurons[i].nucleus,
                         pnl_raw, (int)ts->pos);
        float pnl = (ts->pos == POS_LONG) ? pnl_raw : -pnl_raw;
        trades++; pnl_sum += pnl;
        if (pnl > 0) wins++;
        if (print_trades)
            printf("Candle %d: Force close at %.2f, PnL=%.4f%%\n", end - 1, last[3], pnl * 100);
        ts->pos = POS_NONE;
    }

    *trade_count_out = trades;
    *win_count_out = wins;
    *pnl_total_out = pnl_sum;
}

/* ---------- Main ---------- */
int main(int argc, char** argv) {
    const char* data_path = argc > 1 ? argv[1] : "../../data/btcusdt_5m.bin";
    float lr       = argc > 2 ? atof(argv[2]) : 0.01f;
    float tau      = argc > 3 ? atof(argv[3]) : 12.0f;
    float thresh   = argc > 4 ? atof(argv[4]) : 0.3f;
    float fee_pct  = argc > 5 ? atof(argv[5]) : 0.002f;
    float stop_loss = argc > 6 ? atof(argv[6]) : 0.0f;   /* 0 = disabled */
    float take_prof = argc > 7 ? atof(argv[7]) : 0.0f;
    int   quiet     = argc > 8 ? atoi(argv[8]) : 0;      /* 1 = suppress trade logs */
    unsigned int rseed = argc > 9 ? (unsigned int)atoi(argv[9]) : (unsigned int)time(NULL);
    srand(rseed);

    /* Load data */
    OHLCVData ohlcv = load_ohlcv(data_path);
    printf("Loaded %d candles\n", ohlcv.count);
    if (ohlcv.count < 100) { printf("Too few candles\n"); return 1; }

    /* Split: 80% train, 20% test */
    int split = (int)(ohlcv.count * 0.8);
    printf("Train: 0-%d, Test: %d-%d\n", split, split, ohlcv.count);
    printf("Params: lr=%.4f  tau=%.1f  threshold=%.2f  fee=%.4f  sl=%.2f  tp=%.2f\n\n",
           lr, tau, thresh, fee_pct, stop_loss, take_prof);

    /* Init network (Xavier init + bias=1.0 now in generated code) */
    init_region_TradingCortex();

    /* Init R-STDP per neuron */
    RSTDPState rstdp[NUM_TRADING];
    for (int i = 0; i < NUM_TRADING; i++)
        rstdp_init(&rstdp[i], 64, lr, tau);

    /* ============ TRAINING ============ */
    printf("=== TRAINING ===\n");
    TradeState ts;
    trade_init(&ts, 10000.0f);

    int tr_trades, tr_wins;
    float tr_pnl;
    run_loop(&ohlcv, 5, split, &ts, rstdp,
             &tr_trades, &tr_wins, &tr_pnl,
             tau, thresh, 1 - quiet, stop_loss, take_prof);

    printf("\nTraining: %d trades, winrate=%.1f%%, total PnL=%.4f%%, final equity=%.2f\n\n",
           tr_trades, tr_trades > 0 ? 100.0f * tr_wins / tr_trades : 0,
           tr_pnl * 100, ts.equity);

    /* ============ TEST ============ */
    printf("=== TEST ===\n");
    trade_init(&ts, 10000.0f);

    /* Reset R-STDP stats (keep weights from training) */
    for (int i = 0; i < NUM_TRADING; i++) {
        rstdp[i].total_pnl = 0;
        rstdp[i].trades = 0;
        rstdp[i].wins = 0;
    }

    int te_trades, te_wins;
    float te_pnl;
    run_loop(&ohlcv, split, ohlcv.count, &ts, rstdp,
             &te_trades, &te_wins, &te_pnl,
             tau, thresh, 1 - quiet, stop_loss, take_prof);

    /* ============ RESULTS ============ */
    printf("\n=== RESULTS ===\n");
    printf("Test trades: %d\n", te_trades);
    printf("Winrate:       %.1f%%\n", te_trades > 0 ? 100.0f * te_wins / te_trades : 0);
    printf("Net PnL:       %.4f%%\n", te_pnl * 100);
    printf("Final equity:  %.2f (%.2f%%)\n", ts.equity, (ts.equity / ts.initial_equity - 1) * 100);
    printf("Sharpe (ann.): %.2f\n", sharpe_ratio(ts.equity_curve, ts.equity_len));
    printf("Max Drawdown:  %.2f%%\n", max_drawdown(ts.equity_curve, ts.equity_len) * 100);

    /* Buy & Hold benchmark */
    float bh_entry = ohlcv.data[split * 5 + 3];
    float bh_exit  = ohlcv.data[(ohlcv.count - 1) * 5 + 3];
    float bh_return = (bh_exit - bh_entry) / bh_entry;
    printf("Buy & Hold:    %.2f%%\n", bh_return * 100);

    free(ohlcv.data);
    return 0;
}
