"""Python ctypes wrapper for snn_trader.dll — Million Compiler generated C SNN."""
import ctypes
import os
import platform

import numpy as np

_LIB = None
BUY_N = 18
SELL_N = 18
TOTAL_N = BUY_N + SELL_N
NUCLEUS_SIZE = 64
SENSORY = 14


def _get_lib():
    global _LIB
    if _LIB is not None:
        return _LIB
    lib_dir = os.path.dirname(os.path.abspath(__file__))
    ext = ".dll" if platform.system() == "Windows" else ".so"
    lib_path = os.path.join(lib_dir, "lib", f"snn_trader{ext}")
    if not os.path.exists(lib_path):
        lib_path = os.path.join(lib_dir, "lib", f"libsnn_trader{ext}")
    if not os.path.exists(lib_path):
        raise FileNotFoundError(f"snn_trader library not found ({lib_path})")
    _LIB = ctypes.CDLL(lib_path)
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
    lib.snn_hebbian_idle.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_float]
    lib.snn_hebbian_idle.restype = None
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
    lib.snn_save_state.argtypes = [ctypes.POINTER(ctypes.c_float)]
    lib.snn_save_state.restype = ctypes.c_int
    lib.snn_load_state.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_int]
    lib.snn_load_state.restype = None
    lib.snn_activate_neuron.argtypes = [ctypes.c_int]
    lib.snn_activate_neuron.restype = None
    lib.snn_deactivate_neuron.argtypes = [ctypes.c_int]
    lib.snn_deactivate_neuron.restype = None
    lib.snn_mutate_neuron.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_float]
    lib.snn_mutate_neuron.restype = None
    lib.snn_get_active_mask.argtypes = [ctypes.POINTER(ctypes.c_float)]
    lib.snn_get_active_mask.restype = None
    lib.snn_set_learning_params.argtypes = [ctypes.c_float, ctypes.c_float]
    lib.snn_set_learning_params.restype = None
    lib.snn_set_global_bias.argtypes = [ctypes.c_float]
    lib.snn_set_global_bias.restype = None
    lib.snn_reinforce.argtypes = [ctypes.c_int]
    lib.snn_reinforce.restype = None


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
        return max(self._buy), max(self._sell), self._th.value

    def forward_raw(self, spikes):
        """Return raw per-neuron outputs: buy[16], sell[16], threshold."""
        sp = np.asarray(spikes[:SENSORY], dtype=np.float32)
        self.lib.snn_forward_live(
            sp.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            self._buy, self._sell, ctypes.byref(self._th),
        )
        return list(self._buy), list(self._sell), self._th.value

    def accumulate(self, spikes):
        sp = np.asarray(spikes[:SENSORY], dtype=np.float32)
        self.lib.snn_accumulate_live(sp.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))

    def decay_traces(self):
        self.lib.snn_decay_all()

    def hebbian_idle(self, spikes, lr_hebb=0.001):
        sp = np.asarray(spikes[:SENSORY], dtype=np.float32)
        self.lib.snn_hebbian_idle(sp.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), ctypes.c_float(lr_hebb))

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

    def save_state(self):
        """Export full neuron + RSTDP state as dict (for persistence to DB)."""
        buf = (ctypes.c_float * 7200)()
        n = self.lib.snn_save_state(buf)
        arr = np.array(buf[:n], dtype=np.float32)
        weights_2d = []
        eligibility_2d = []
        membrane = []
        pos = 0
        for i in range(TOTAL_N):
            weights_2d.append(arr[pos:pos + NUCLEUS_SIZE].tolist())
            pos += NUCLEUS_SIZE
            membrane.append({
                "bias": float(arr[pos]), "potential": float(arr[pos + 1]),
                "threshold": float(arr[pos + 2]), "refractory": float(arr[pos + 3]),
                "refr_counter": int(arr[pos + 4]), "output": float(arr[pos + 5]),
            })
            pos += 6
            eligibility_2d.append(arr[pos:pos + NUCLEUS_SIZE].tolist())
            pos += NUCLEUS_SIZE
        velocity_2d = []
        for i in range(TOTAL_N):
            velocity_2d.append(arr[pos:pos + NUCLEUS_SIZE].tolist())
            pos += NUCLEUS_SIZE
        rstpd = {
            "lr": float(arr[pos]),
            "total_pnl": float(arr[pos + 1]),
            "trades": int(arr[pos + 2]),
            "wins": int(arr[pos + 3]),
            "trades_total": int(arr[pos + 4]),
            "running_pnl_sum": float(arr[pos + 5]),
            "running_pnl_sq": float(arr[pos + 6]),
            "running_count": int(arr[pos + 7]),
        }
        pos += 8
        active_mask = [int(arr[pos + i]) for i in range(TOTAL_N)]
        return {"weights": weights_2d, "membrane": membrane,
                "eligibility": eligibility_2d, "velocity": velocity_2d,
                "rstpd": rstpd, "active_mask": active_mask}

    def load_state(self, saved, load_eligibility=True, load_membrane=True):
        """Restore full neuron + RSTDP state from dict (saved via save_state)."""
        buf = (ctypes.c_float * 7200)()
        pos = 0
        for i in range(TOTAL_N):
            w = saved["weights"][i][:NUCLEUS_SIZE]
            for v in w: buf[pos] = float(v); pos += 1
            if "membrane" in saved and i < len(saved["membrane"]):
                m = saved["membrane"][i]
                buf[pos] = m.get("bias", 1.0); pos += 1
                buf[pos] = m.get("potential", 0.0); pos += 1
                buf[pos] = m.get("threshold", 0.5); pos += 1
                buf[pos] = m.get("refractory", 0.0); pos += 1
                buf[pos] = m.get("refr_counter", 0); pos += 1
                buf[pos] = m.get("output", 0.0); pos += 1
            else:
                for _ in range(6): buf[pos] = 0.0; pos += 1
            if load_eligibility and "eligibility" in saved and i < len(saved["eligibility"]):
                for v in saved["eligibility"][i]: buf[pos] = float(v); pos += 1
            else:
                for _ in range(NUCLEUS_SIZE): buf[pos] = 0.0; pos += 1
            if load_eligibility and "velocity" in saved and i < len(saved["velocity"]):
                for v in saved["velocity"][i]: buf[pos] = float(v); pos += 1
            else:
                for _ in range(NUCLEUS_SIZE): buf[pos] = 0.0; pos += 1
        rstpd = saved.get("rstpd", {})
        buf[pos] = rstpd.get("lr", 0.01); pos += 1
        buf[pos] = rstpd.get("total_pnl", 0.0); pos += 1
        buf[pos] = rstpd.get("trades", 0); pos += 1
        buf[pos] = rstpd.get("wins", 0); pos += 1
        buf[pos] = rstpd.get("trades_total", 0); pos += 1
        buf[pos] = rstpd.get("running_pnl_sum", 0.0); pos += 1
        buf[pos] = rstpd.get("running_pnl_sq", 0.0); pos += 1
        buf[pos] = rstpd.get("running_count", 0); pos += 1
        # active mask
        am = saved.get("active_mask", [1] * TOTAL_N)
        for v in am[:TOTAL_N]: buf[pos] = float(v); pos += 1
        for _ in range(TOTAL_N - len(am)): buf[pos] = 1.0; pos += 1
        self.lib.snn_load_state(buf, ctypes.c_int(1 if load_eligibility else 0),
                                ctypes.c_int(1 if load_membrane else 0))

    # ── EvoBrain API ──
    def activate_neuron(self, idx):
        self.lib.snn_activate_neuron(ctypes.c_int(idx))

    def deactivate_neuron(self, idx):
        self.lib.snn_deactivate_neuron(ctypes.c_int(idx))

    def mutate_neuron(self, target, source, sigma=0.1):
        self.lib.snn_mutate_neuron(ctypes.c_int(target), ctypes.c_int(source), ctypes.c_float(sigma))

    def get_active_mask(self):
        buf = (ctypes.c_float * TOTAL_N)()
        self.lib.snn_get_active_mask(buf)
        return [int(buf[i]) for i in range(TOTAL_N)]

    def set_learning_params(self, lr, tau):
        self.lib.snn_set_learning_params(ctypes.c_float(lr), ctypes.c_float(tau))

    def set_global_bias(self, bias):
        self.lib.snn_set_global_bias(ctypes.c_float(bias))

    def reinforce(self, punish=False):
        """Predictive reward: reinforce (1.01x) or punish (0.99x) neurons that fired."""
        self.lib.snn_reinforce(ctypes.c_int(1 if punish else 0))


def quick_backtest(data, lr=0.01, tau=96.0, sl=0.05, tp=0.12,
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