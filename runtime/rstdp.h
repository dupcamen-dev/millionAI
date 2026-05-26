/* Reward-modulated STDP with eligibility trace.

Usage:
  1. Maintain EligibilityState per neuron
  2. On each tick: rstdp_accumulate(nucleus, input, output, &state)
  3. On position close: rstdp_commit(nucleus, pnl_pct, &state)
     This computes reward, updates weights, resets traces.

  4. rstdp_decay(&state) — call each tick even without trade action
     to decay existing eligibility traces.
*/
#ifndef RSTDP_H
#define RSTDP_H

#include <math.h>
#include <string.h>

#define RSTDP_MAX_NUCLEUS 1024

typedef struct {
    float eligibility[RSTDP_MAX_NUCLEUS];   /* trace per weight */
    int size;                                /* actual nucleus size */
    float lr;                                /* learning rate */
    float decay;                             /* eligibility decay per tick (e.g. 0.92) */
    float reward_k;                          /* reward scaling (e.g. 10.0) */
    float fee_pct;                           /* round-trip fee (e.g. 0.002 = 0.2%) */
    float total_pnl;                         /* cumulative PnL */
    int trades;                              /* total trade count */
    int wins;                                /* winning trades */
    /* --- Online learning fields --- */
    float micro_lr_scale;                    /* LR scale for micro-reward (default 0.1) */
    float lr_0;                              /* initial LR for adaptive decay */
    int trades_total;                        /* total trades for adaptive LR */
    float prev_unrealized_pnl;               /* previous unrealized PnL for micro-reward delta */
} RSTDPState;

static void rstdp_init(RSTDPState* s, int nucleus_size, float lr, float tau_candles) {
    memset(s, 0, sizeof(RSTDPState));
    s->size = nucleus_size < RSTDP_MAX_NUCLEUS ? nucleus_size : RSTDP_MAX_NUCLEUS;
    s->lr = lr;
    s->lr_0 = lr;
    s->decay = expf(-1.0f / tau_candles);   /* exponential decay per tick */
    s->reward_k = 10.0f;
    s->fee_pct = 0.002f;                     /* 0.2% round-trip */
    s->micro_lr_scale = 0.1f;                /* default micro-reward scale */
}

/* Micro-reward: partial weight update on each tick without resetting eligibility.
   prev_unrealized / current_unrealized: fractional PnL (e.g. 0.01 = +1%).
   Returns the micro-reward value. */
static float rstdp_micro_reward(RSTDPState* s, float* nucleus,
                                 float prev_unrealized_pnl, float current_unrealized_pnl) {
    float pnl_change = current_unrealized_pnl - prev_unrealized_pnl;
    float micro_reward = tanhf(s->reward_k * 0.3f * pnl_change);
    float micro_lr = s->lr * s->micro_lr_scale;
    for (int i = 0; i < s->size; i++)
        nucleus[i] += micro_lr * s->eligibility[i] * micro_reward;
    return micro_reward;
}

/* Adaptive LR: lr = lr_0 / (1 + 0.01 * total_trades) */
static void rstdp_update_adaptive_lr(RSTDPState* s) {
    s->lr = s->lr_0 / (1.0f + 0.01f * (float)s->trades_total);
}

/* Set tau (eligibility decay constant) and recompute decay factor.
   tau: number of candles for eligibility half-life. */
static void rstdp_set_tau(RSTDPState* s, float tau_candles) {
    s->decay = expf(-1.0f / tau_candles);
}

/* STDP kernel: how much the pair (input[j], output) contributes to eligibility.
   input[j] = 0..1 (spike strength), output = -1..1 (action signal). */
static float stdp_kernel(float input_j, float output) {
    float dt = output - 0.5f;
    return input_j * dt * expf(-fabsf(dt));
}

/* Accumulate eligibility trace for one tick. Call AFTER forward pass. */
static void rstdp_accumulate(RSTDPState* s, float* nucleus, float* input, int input_size, float output) {
    int n = s->size < input_size ? s->size : input_size;
    for (int i = 0; i < n; i++) {
        s->eligibility[i] += stdp_kernel(input[i], output);
    }
    /* Normal STDP update (optional online component) */
    /*
    for (int i = 0; i < n; i++) {
        nucleus[i] += s->lr * input[i] * (output - 0.5f) * expf(-fabsf(output - 0.5f));
    }
    */
}

/* Decay eligibility traces (call every tick regardless of trade). */
static void rstdp_decay(RSTDPState* s) {
    for (int i = 0; i < s->size; i++)
        s->eligibility[i] *= s->decay;
}

/* Commit: apply reward to weights using eligibility traces.
   Call when position closes.
   pnl_pct = (exit_price - entry_price) / entry_price  (positive for long profit)
   side = 1 for long, -1 for short
   Returns the reward value. */
static float rstdp_commit(RSTDPState* s, float* nucleus, float pnl_pct, int side) {
    /* Adjust for fees */
    float net_pnl = pnl_pct * side - s->fee_pct;
    /* Reward: tanh(k * net_pnl), bounded [-1, 1] */
    float reward = tanhf(s->reward_k * net_pnl);

    /* Update weights: Δw_i = lr * eligibility_i * reward */
    for (int i = 0; i < s->size; i++) {
        nucleus[i] += s->lr * s->eligibility[i] * reward;
    }

    /* Track stats */
    s->total_pnl += net_pnl;
    s->trades++;
    s->trades_total++;
    if (net_pnl > 0) s->wins++;

    /* Reset eligibility to zero */
    memset(s->eligibility, 0, s->size * sizeof(float));

    return reward;
}

#endif /* RSTDP_H */
