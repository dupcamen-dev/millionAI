/* OHLCV → 8-channel spike encoding.

Input:  float o, h, l, c, v          (open, high, low, close, volume)
        float* vol_hist               (circular buffer of past volumes for SMA)
        int vol_idx, int vol_count    (current index + fill count)
Output: float spikes[8]

Channels:
  [0] UP        = 1.0 if close > open, else 0.0
  [1] DOWN      = 1.0 if close < open, else 0.0
  [2] BODY      = |close - open| / spread (0..1)
  [3] WICK_TOP  = (high - max(open,close)) / spread (0..1)
  [4] WICK_BOT  = (min(open,close) - low) / spread (0..1)
  [5] VOLUME    = volume / sma_volume_20 (clipped 0..3)
  [6] MOMENTUM  = sign * |close - open| / spread (-1..1)
  [7] BIAS      = (close - low) / spread (0..1)
*/
#ifndef CRYPTO_ENCODE_H
#define CRYPTO_ENCODE_H

#include <math.h>

#define SENSORY_CHANNELS 8
#define VOL_SMA_WINDOW 20

static float sma_volume_20(const float* hist, int idx, int count, float new_vol) {
    if (count < VOL_SMA_WINDOW) {
        float sum = new_vol;
        for (int i = 0; i < count; i++) sum += hist[i];
        return sum / (count + 1);
    }
    float sum = new_vol;
    for (int i = 0; i < VOL_SMA_WINDOW - 1; i++)
        sum += hist[(idx - 1 - i + VOL_SMA_WINDOW) % VOL_SMA_WINDOW];
    return sum / VOL_SMA_WINDOW;
}

static void encode_ohlcv(float o, float h, float l, float c, float v,
                          float* vol_hist, int vol_idx, int vol_count,
                          float spikes[SENSORY_CHANNELS]) {
    float spread = h - l;
    if (spread < 1e-8f) spread = 1e-8f;

    spikes[0] = (c > o) ? 1.0f : 0.0f;
    spikes[1] = (c < o) ? 1.0f : 0.0f;

    float body = fabsf(c - o);
    spikes[2] = fminf(body / spread, 1.0f);

    float top_wick = h - fmaxf(o, c);
    float bot_wick = fminf(o, c) - l;
    spikes[3] = fminf(top_wick / spread, 1.0f);
    spikes[4] = fminf(bot_wick / spread, 1.0f);

    float vol_sma = sma_volume_20(vol_hist, vol_idx, vol_count, v);
    spikes[5] = (vol_sma > 1e-8f) ? fminf(v / vol_sma, 3.0f) : 1.0f;

    float momentum = (c - o) / spread;
    spikes[6] = fmaxf(-1.0f, fminf(1.0f, momentum));

    spikes[7] = (c - l) / spread;
}

#endif /* CRYPTO_ENCODE_H */
