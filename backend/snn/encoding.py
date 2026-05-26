import math
import numpy as np

def arch_proj(i, j, l):
    return float(((i * 13) ^ (j * 7) ^ (l * 5)) % 31 - 15) / 15.0

def archive_unfold(nucleus, level=1):
    N = len(nucleus)
    unfolded = np.zeros(N * 4, dtype=np.float32)
    for i in range(N * 4):
        s = sum(nucleus[j] * arch_proj(i, j, level) for j in range(N))
        unfolded[i] = math.tanh(s / N)
    return unfolded

def archive_compress(unfolded, out_size=64):
    in_size = len(unfolded)
    group = in_size // out_size
    compressed = np.zeros(out_size, dtype=np.float32)
    for i in range(out_size):
        start = i * group
        end = min(start + group, in_size)
        compressed[i] = sum(unfolded[start:end]) / (end - start)
    return compressed

SENSORY = 8
ARCHIVE_N = 64
BUY_N = 8
SELL_N = 8
TOTAL_N = BUY_N + SELL_N

def encode_ohlcv(o, h, l, c, v, vol_history, funding_rate=0.0):
    spread = max(h - l, 1e-8)
    spikes = np.zeros(SENSORY, dtype=np.float32)
    spikes[0] = 1.0 if c > o else 0.0
    spikes[1] = 1.0 if c < o else 0.0
    body = abs(c - o)
    spikes[2] = min(body / spread, 1.0)
    spikes[3] = min((h - max(o, c)) / spread, 1.0)
    spikes[4] = min((min(o, c) - l) / spread, 1.0)
    vol_history.append(v)
    if len(vol_history) > 20:
        vol_history.pop(0)
    vol_sma = np.mean(vol_history) if vol_history else v
    spikes[5] = min(v / vol_sma, 3.0) if vol_sma > 1e-8 else 1.0
    spikes[6] = max(-1.0, min(1.0, (c - o) / spread))
    spikes[7] = (c - l) / spread
    return spikes
