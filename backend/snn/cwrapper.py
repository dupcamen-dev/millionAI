"""Python ctypes wrapper for snn_trader.dll — Million Compiler generated C SNN."""
import ctypes
import os
import numpy as np

_LIB = None
BUY_N = 8
SELL_N = 8
TOTAL_N = 16
NUCLEUS_SIZE = 64
SENSORY = 8


def _get_lib():
    global _LIB
    if _LIB is not None:
        return _LIB
    lib_dir = os.path.dirname(os.path.abspath(__file__))
    dll_path = os.path.join(lib_dir, "lib", "snn_trader.dll")
    if not os.path.exists(dll_path):
        dll_path = os.path.join(lib_dir, "lib", "libsnn_trader.so")
    if not os.path.exists(dll_path):
        raise FileNotFoundError(f"snn_trader library not found at {dll_path}")
    _LIB = ctypes.CDLL(dll_path)
    _setup()
    return _LIB


def _setup():
    lib = _LIB
    lib.snn_init_live.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float]
    lib.snn_init_live.restype = None
    lib.snn_forward_live.argtypes = [
        ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float),
    ]
    lib.snn_forward_live.restype = None
    lib.snn_accumulate_live.argtypes = [ctypes.POINTER(ctypes.c_float)]
    lib.snn_accumulate_live.restype = None
    lib.snn_decay_all.argtypes = []
    lib.snn_decay_all.restype = None
    lib.snn_micro_reward_all.argtypes = [ctypes.c_float, ctypes.c_float]
    lib.snn_micro_reward_all.restype = None
    lib.snn_commit_all.argtypes = [ctypes.c_float, ctypes.c_int]
    lib.snn_commit_all.restype = ctypes.c_float
    lib.snn_get_weights_live.argtypes = [ctypes.POINTER(ctypes.c_float)]
    lib.snn_get_weights_live.restype = None
    lib.snn_get_rstdp_state_live.argtypes = [
        ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
    ]
    lib.snn_get_rstdp_state_live.restype = None


class NativeSNN:
    """Live trading SNN backed by compiled C library from Million compiler."""

    def __init__(self, init_weights=None, lr=0.01, tau=24.0):
        self.lib = _get_lib()
        self._buy = (ctypes.c_float * BUY_N)()
        self._sell = (ctypes.c_float * SELL_N)()
        self._th = ctypes.c_float()
        if init_weights is not None:
            w = np.asarray(init_weights, dtype=np.float32).flatten()
            self.lib.snn_init_live(w.ctypes.data_as(ctypes.c_void_p),
                                   ctypes.c_float(lr), ctypes.c_float(tau))
        else:
            self.lib.snn_init_live(None, ctypes.c_float(lr), ctypes.c_float(tau))

    def forward(self, spikes):
        sp = np.asarray(spikes[:SENSORY], dtype=np.float32)
        self.lib.snn_forward_live(
            sp.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            self._buy, self._sell, ctypes.byref(self._th),
        )
        buy_max = float(max(self._buy))
        sell_max = float(max(self._sell))
        return buy_max, sell_max, self._th.value

    def accumulate(self, spikes):
        sp = np.asarray(spikes[:SENSORY], dtype=np.float32)
        self.lib.snn_accumulate_live(sp.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))

    def decay_traces(self):
        self.lib.snn_decay_all()

    def micro_reward(self, prev_pnl, curr_pnl):
        self.lib.snn_micro_reward_all(ctypes.c_float(prev_pnl), ctypes.c_float(curr_pnl))

    def commit(self, pnl_pct, side):
        reward = self.lib.snn_commit_all(ctypes.c_float(pnl_pct), ctypes.c_int(side))
        return reward, 0.0

    def get_weights(self):
        buf = (ctypes.c_float * (TOTAL_N * NUCLEUS_SIZE))()
        self.lib.snn_get_weights_live(buf)
        return np.array(buf, dtype=np.float32).reshape(TOTAL_N, NUCLEUS_SIZE)

    def get_state(self):
        lr = ctypes.c_float(); pnl = ctypes.c_float()
        t = ctypes.c_int(); w = ctypes.c_int()
        self.lib.snn_get_rstdp_state_live(ctypes.byref(lr), ctypes.byref(pnl),
                                          ctypes.byref(t), ctypes.byref(w))
        return {"lr": lr.value, "total_pnl": pnl.value,
                "trades": t.value, "wins": w.value}


def quick_backtest(data, lr=0.01, tau=24.0, sl=0.05, tp=0.12,
                   use_micro=True, init_weights=None, leverage=1):
    """Run backtest using compiled C SNN via live API functions."""
    snn = NativeSNN(init_weights=init_weights, lr=lr, tau=tau)
    vol_hist = []
    pnls_test = []
    split = int(len(data) * 0.8)

    for phase, start, end in [("train", 5, split), ("test", split, len(data))]:
        pos = 0; entry_price = 0.0
        prev_pnl = 0.0; has_prev = False
        trades = 0; wins = 0; pnl_sum = 0.0; phase_pnls = []

        for c in range(start, end):
            from snn.encoding import encode_ohlcv
            o, h, l, cl, v = data[c]
            spikes = encode_ohlcv(o, h, l, cl, v, vol_hist)

            buy, sell, th = snn.forward(spikes)
            action = 1 if buy > th and buy >= sell else (-1 if sell > th and sell > buy else 0)

            if pos == 0:
                if action:
                    pos = action; entry_price = cl; has_prev = False
                else:
                    snn.decay_traces()
            else:
                pnl_raw = (cl - entry_price) / entry_price
                curr = pnl_raw if pos == 1 else -pnl_raw
                curr_levered = curr * leverage
                snn.accumulate(spikes)
                if use_micro and has_prev:
                    snn.micro_reward(prev_pnl, curr_levered)
                prev_pnl = curr_levered; has_prev = True
                snn.decay_traces()
                close = 0
                if sl > 0 and curr_levered <= -sl: close = 1
                elif tp > 0 and curr_levered >= tp: close = 1
                elif (pos == 1 and action == -1) or (pos == -1 and action == 1): close = 1
                if close:
                    snn.commit(pnl_raw, pos)
                    pos = 0; has_prev = False
                    trades += 1; pnl_sum += curr_levered; phase_pnls.append(curr_levered)
                    if curr_levered > 0: wins += 1
        if phase == "test":
            pnls_test = phase_pnls
            tr = trades; tw = wins; tp = pnl_sum

    avg_pnl = tp / max(tr, 1)
    std_pnl = np.std(pnls_test) if len(pnls_test) > 1 else abs(avg_pnl) + 0.001
    wr = tw / max(tr, 1)
    risk_score = wr * avg_pnl * np.sqrt(max(tr, 1)) / max(std_pnl, 0.001)
    trained_weights = snn.get_weights()

    return {
        "trades": tr, "wins": tw, "total_pnl": tp,
        "avg_pnl": avg_pnl, "std_pnl": std_pnl,
        "winrate": wr, "risk_score": risk_score,
        "weights": [w.tolist() for w in trained_weights],
    }