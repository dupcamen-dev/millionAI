import math
import numpy as np

ARCHIVE_N = 64
SENSORY = 8
BUY_N = 8
SELL_N = 8
TOTAL_N = BUY_N + SELL_N

_UNFOLD_CACHE = {}

def _get_unfold_matrix(nucleus_size, level):
    key = (nucleus_size, level)
    if key not in _UNFOLD_CACHE:
        N = nucleus_size
        out_size = N * 4
        i_idx = np.arange(out_size, dtype=np.int32).reshape(-1, 1)
        j_idx = np.arange(N, dtype=np.int32).reshape(1, -1)
        W = ((i_idx * 13) ^ (j_idx * 7) ^ (level * 5)) % 31 - 15
        W = W.astype(np.float32) / 15.0
        _UNFOLD_CACHE[key] = W
    return _UNFOLD_CACHE[key]

def archive_unfold(nucleus, level=1):
    N = len(nucleus)
    W = _get_unfold_matrix(N, level)
    s = W @ nucleus
    return np.tanh(s / float(N)).astype(np.float32)

def archive_compress(unfolded, out_size=64):
    in_size = len(unfolded)
    group = max(in_size // out_size, 1)
    reshaped = unfolded[:group * out_size].reshape(out_size, group)
    return reshaped.mean(axis=1).astype(np.float32)

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