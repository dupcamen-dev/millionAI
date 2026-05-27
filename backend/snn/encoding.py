import math
import numpy as np

ARCHIVE_N = 64
SENSORY = 14
BUY_N = 18
SELL_N = 18
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

def encode_features(o, h, l, c, v, vol_history, order_book=None, trade_tape=None):
    """Encode OHLCV + order book + trade tape into 14-channel spike vector.
       order_book: [bid_qty, ask_qty, best_bid, best_ask, max_bid_qty, max_ask_qty]
       trade_tape: [buy_vol, sell_vol, trade_count, large_trade_ratio]
    """
    spread = max(h - l, 1e-8)
    spikes = np.zeros(SENSORY, dtype=np.float32)

    # Channels 0-7: OHLCV
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

    # Channels 8-10: Order Book
    if order_book is not None and len(order_book) >= 6:
        bid_qty, ask_qty, best_bid, best_ask, max_bid_qty, max_ask_qty = order_book[:6]
        total = bid_qty + ask_qty + 1e-8
        spikes[8] = (bid_qty - ask_qty) / total  # book imbalance
        bbid = best_bid if best_bid > 0 else c
        spikes[9] = min((best_ask - bbid) / bbid, 0.05) if bbid > 0 else 0  # spread
        spikes[10] = (max_bid_qty - max_ask_qty) / (max_bid_qty + max_ask_qty + 1e-8)  # wall pressure

    # Channels 11-13: Trade Tape
    if trade_tape is not None and len(trade_tape) >= 4:
        buy_vol, sell_vol, trade_count, large_ratio = trade_tape[:4]
        total_vol = buy_vol + sell_vol + 1e-8
        spikes[11] = (buy_vol - sell_vol) / total_vol  # CVD
        spikes[12] = min(trade_count / 100.0, 3.0)  # trade intensity
        spikes[13] = large_ratio  # large trade ratio

    return spikes

# Backward compatibility
def encode_ohlcv(o, h, l, c, v, vol_history, funding_rate=0.0):
    return encode_features(o, h, l, c, v, vol_history, None, None)