import json
import math
import os
import random
import sys
import time
from collections import deque

import numpy as np

from snn.encoding import encode_features, encode_ohlcv, SENSORY, BUY_N, SELL_N, TOTAL_N
from snn.neuron import TradingNeuron, ARCHIVE_N
from snn.rstpd import RSTDPEngine

# Try to load NativeSNN (compiled C from Million compiler)
try:
    from snn.cwrapper import NativeSNN
    _NATIVE_SNN = NativeSNN
except (ImportError, FileNotFoundError, OSError) as e:
    _NATIVE_SNN = None
    print(f"[Base] C SNN not available: {e}")

INITIAL_EQUITY = 10.0

class BaseTrader:
    def __init__(self, symbol="SOLUSDT", leverage=1, config_file=None, lr=0.01, tau=96.0, sl=0.05, tp=0.12):
        self.symbol = symbol.upper()
        self.leverage = leverage
        self.neurons = []
        self.vol_history = []
        self.pos = 0
        self.entry_price = 0.0
        self.last_close = 0.0
        self.equity = INITIAL_EQUITY
        self.trades = 0
        self.wins = 0
        self.total_pnl = 0.0
        self.prev_unrealized = 0.0
        self._has_prev_pnl = False
        self.rstdp = RSTDPEngine(lr=lr, tau=tau)
        self.sl = sl
        self.tp = tp
        self.running = True
        self.equity_curve = []
        self.candle_count = 0
        self.entry_candle = 0
        self.max_hold = 24
        self.epsilon = 0.15
        self.last_candle_time = time.time()
        self._c_snn = None  # NativeSNN instance (compiled C SNN)
        self._last_entry_signal = 0
        self._entry_consecutive = 0
        self._activity_history = []
        self._base_threshold = 0.40
        self._risk_scale = 1.0
        self._firing_count = [0] * 36  # per-neuron firing count
        self._firing_window = 20       # sliding window size
        self._last_evo_trade = 0
        self._last_evo_pnl = 0.0
        self._last_evo_candle_count = 0
        self._no_trade_streak = 0

        if config_file and os.path.exists(config_file):
            self.load_config(config_file)
        else:
            self.init_random()

    def _use_c_backend(self):
        return _NATIVE_SNN is not None and self._c_snn is not None

    def init_c_snn(self, weights=None, loaded_state=None, lr=None, tau=None):
        if _NATIVE_SNN is None:
            return False
        if lr is None: lr = self.rstdp.lr
        if tau is None: tau = -1.0 / math.log(max(self.rstdp.decay, 1e-10))
        if weights is None and self.neurons:
            weights = [n.nucleus.tolist() for n in self.neurons]
        self._c_snn = _NATIVE_SNN(init_weights=weights, lr=lr, tau=tau)
        if loaded_state and loaded_state.get("eligibility"):
            self._c_snn.load_state(loaded_state, load_eligibility=True, load_membrane=False)
        return True

    def _sync_weights_from_c(self):
        if not self._use_c_backend():
            return
        state = self._c_snn.save_state()
        w_np = np.array(state["weights"], dtype=np.float32)
        for i in range(TOTAL_N):
            self.neurons[i].nucleus = w_np[i].copy()
        self.rstdp.lr = state["rstpd"]["lr"]
        self.rstdp.total_pnl = state["rstpd"]["total_pnl"]
        self.rstdp.trades = state["rstpd"]["trades"]
        self.rstdp.wins = state["rstpd"]["wins"]
        self._last_full_state = state

    def _save_full_state_to_db(self):
        if not hasattr(self, 'db') or not self.db or not self.user_id:
            return
        if self._use_c_backend():
            state = self._c_snn.save_state()
            state["leverage"] = self.leverage
            state["risk_score"] = getattr(self, 'last_backtest_risk_score', 0.0)
            try:
                self.db.save_model_state(self.user_id, self.symbol, state)
            except Exception as e:
                print(f"[Base] Failed to save model state: {e}")

    def init_random(self):
        self.neurons = [TradingNeuron() for _ in range(TOTAL_N)]

    def load_config(self, path):
        with open(path) as f:
            data = json.load(f)
        self.neurons = [TradingNeuron(nucleus=np.array(n, dtype=np.float32)) for n in data.get("neurons", [])]
        self.leverage = data.get("leverage", self.leverage)
        self.symbol = data.get("symbol", self.symbol)

    def save_config(self, path):
        data = {
            "symbol": self.symbol,
            "leverage": self.leverage,
            "neurons": [n.nucleus.tolist() for n in self.neurons],
        }
        with open(path, "w") as f:
            json.dump(data, f)

    def forward_all(self, spikes):
        neg_spikes = -spikes
        for i in range(BUY_N):
            self.neurons[i].forward(spikes)
        for i in range(SELL_N):
            self.neurons[BUY_N + i].forward(neg_spikes)

    def compute_action(self):
        buy = max(n.output for n in self.neurons[:BUY_N]) if self.neurons else 0
        sell = max(n.output for n in self.neurons[BUY_N:]) if len(self.neurons) > BUY_N else 0
        th = self.neurons[0].threshold if self.neurons else 0.3
        if buy > th and buy >= sell:
            return 1
        if sell > th and sell > buy:
            return -1
        if random.random() < self.epsilon:
            return random.choice([1, -1])
        return 0

    def _hyperparam_cycle(self):
        """Run every 5 candles — adjusts params based on trading patterns."""
        log_fn = getattr(self, '_log', print)

        # No-trade streak: gradually become more aggressive
        if self._no_trade_streak > 20 and self._no_trade_streak % 20 == 0:
            self._base_threshold = max(0.25, self._base_threshold - 0.05)
            self.epsilon = min(0.3, self.epsilon + 0.05)
            log_fn("SYS", f"Evo: no-trade streak={self._no_trade_streak}, th→{self._base_threshold:.2f} eps→{self.epsilon:.2f}")

        # Only continue if we have enough trades for window PnL checks
        if self.trades <= self._last_evo_trade:
            return

        window_pnl = self.total_pnl - self._last_evo_pnl

        if window_pnl < -0.05:
            eff_tau = max(24, getattr(self, 'tau', 96) - 12)
            self.tau = eff_tau
            if self._use_c_backend():
                self._c_snn.set_learning_params(self.rstdp.lr * 1.1, eff_tau)
            self._risk_scale = max(0.4, self._risk_scale * 0.9)
            log_fn("SYS", f"Evo: loss PnL={window_pnl*100:.1f}%, tau→{eff_tau} lr↑ risk↓")

        if window_pnl > 0.10:
            eff_tau = min(192, getattr(self, 'tau', 96) + 12)
            self.tau = eff_tau
            if self._use_c_backend():
                self._c_snn.set_learning_params(self.rstdp.lr * 0.9, eff_tau)
            self.epsilon = max(0.05, self.epsilon * 0.8)
            self._base_threshold = min(1.0, self._base_threshold + 0.03)  # ← become less aggressive
            log_fn("SYS", f"Evo: win PnL={window_pnl*100:.1f}%, tau→{eff_tau} lr↓ eps↓ th→{self._base_threshold:.2f}")

        self._last_evo_pnl = self.total_pnl

    def _neurogenesis_cycle(self):
        """Run every 10 closed trades — replace weak neurons with mutated elite copies."""
        if self.trades - self._last_evo_trade < 10:
            return
        if not self._use_c_backend():
            return

        log_fn = getattr(self, '_log', print)
        mask = self._c_snn.get_active_mask()
        state = self._c_snn.save_state()
        weights = np.array(state['weights'])

        firing_rates = [self._firing_count[i] / max(self._firing_window, 1) for i in range(TOTAL_N)]
        weight_var = weights.var(axis=1)
        var_max = max(weight_var.max(), 0.01)
        utility = [0.8 * fr + 0.2 * (weight_var[i] / var_max) for i, fr in enumerate(firing_rates)]

        for side, start in [("BUY", 0), ("SELL", 18)]:
            active = [(i, utility[i]) for i in range(start, start + 18) if mask[i]]
            active.sort(key=lambda x: x[1])
            to_demote = active[:2]
            for idx, u in to_demote:
                self._c_snn.deactivate_neuron(idx)
                log_fn("SYS", f"Evo: demote {side} N{idx} (utility={u:.3f})")

        for side, start, el_start in [("BUY", 16, 0), ("SELL", 34, 18)]:
            active_in_side = [i for i in range(el_start, el_start + 18) if mask[i]]
            elite = active_in_side[:3] if len(active_in_side) >= 3 else active_in_side
            for ri in range(start, start + 2):
                if mask[ri]:
                    continue
                ei = elite[ri % len(elite)]
                self._c_snn.mutate_neuron(ri, ei, 0.1)
                self._c_snn.activate_neuron(ri)
                self._firing_count[ri] = 0
                log_fn("SYS", f"Evo: promote {side} reserve N{ri} (elite=N{ei})")

        self._last_evo_trade = self.trades
        self._last_evo_pnl = self.total_pnl
        self._last_evo_candle_count = self.candle_count

    def _compute_decision(self, buy_raw, sell_raw, th_val):
        # ── Track per-neuron firing ──
        for i, o in enumerate(buy_raw + sell_raw):
            if o > 0:
                self._firing_count[i] = min(self._firing_count[i] + 1, self._firing_window)
            else:
                self._firing_count[i] = max(self._firing_count[i] - 1, 0)

        # ── Tonic homeostasis: track raw activity ──
        active = sum(1 for o in buy_raw + sell_raw if o > 0)
        self._activity_history.append(active / 32.0)
        if len(self._activity_history) > 20:
            self._activity_history.pop(0)

        if self.candle_count % 5 == 0 and len(self._activity_history) > 0:
            avg = sum(self._activity_history) / len(self._activity_history)
            if avg > 0.50:
                self._base_threshold = min(1.0, self._base_threshold + 0.005)
            elif avg < 0.10:
                self._base_threshold = max(0.25, self._base_threshold - 0.005)

        # ── Score: top-3 weighted ──
        buy_sorted = sorted(buy_raw, reverse=True)
        sell_sorted = sorted(sell_raw, reverse=True)
        buy_score = 0.7 * buy_sorted[0] + 0.3 * (sum(buy_sorted[:3]) / 3.0)
        sell_score = 0.7 * sell_sorted[0] + 0.3 * (sum(sell_sorted[:3]) / 3.0)

        # ── Cross-inhibition ──
        if buy_score > sell_score:
            sell_score *= 0.5
        else:
            buy_score *= 0.5

        # ── Volatility threshold ──
        vol_pct = getattr(self, 'volatility_pct', 20.0)
        vol_mult = max(1.0, min(2.0, 1.0 + (vol_pct - 20.0) / 50.0))
        self._risk_scale = max(0.4, 1.0 / vol_mult)
        eff_th = self._base_threshold * vol_mult

        # ── Margin filter ──
        margin = abs(buy_score - sell_score) / max(buy_score, sell_score, 0.01)
        if margin < 0.15:
            return 0
        if max(buy_score, sell_score) < eff_th:
            return 0

        # ── Final decision ──
        if buy_score > sell_score:
            self._no_trade_streak = 0
            return 1
        elif sell_score > buy_score:
            self._no_trade_streak = 0
            return -1
        self._no_trade_streak += 1

        # Hyperparam cycle every 5 candles
        if self.candle_count % 5 == 0:
            self._hyperparam_cycle()

        return 0

    def on_candle(self, o, h, l, c, v, ts=None, order_book=None, trade_tape=None):
        self.last_close = c
        self.candle_count += 1
        self.last_candle_time = time.time()
        spikes = encode_features(o, h, l, c, v, self.vol_history,
                                  order_book=order_book, trade_tape=trade_tape)

        use_c = self._use_c_backend()
        if use_c:
            buy_raw, sell_raw, th_val = self._c_snn.forward_raw(spikes)
        else:
            self.forward_all(spikes)
            buy_raw = [n.output for n in self.neurons[:BUY_N]]
            sell_raw = [n.output for n in self.neurons[BUY_N:]]
            th_val = self.neurons[0].threshold if self.neurons else 0.3

        # ── v1 Decision Pipeline ─────────────────────────────
        raw_action = self._compute_decision(buy_raw, sell_raw, th_val)

        # ── Burst detector: entry needs 2+ consecutive, exit is instant ──
        if self.pos == 0:
            if raw_action == self._last_entry_signal and raw_action != 0:
                self._entry_consecutive += 1
            else:
                self._entry_consecutive = 1 if raw_action != 0 else 0
            self._last_entry_signal = raw_action
            action = raw_action if self._entry_consecutive >= 2 else 0
        else:
            action = raw_action  # no burst delay for exit signals

        # ── Log values ──
        buy_val = max(buy_raw) if buy_raw else 0
        sell_val = max(sell_raw) if sell_raw else 0

        ts_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else time.strftime("%Y-%m-%d %H:%M")

        if self.pos == 0:
            self.epsilon = max(0.02, self.epsilon * 0.995)
            if action != 0:
                self.pos = action
                self.entry_price = c
                self._has_prev_pnl = False
                self.entry_candle = self.candle_count
                side = "BUY" if action == 1 else "SELL"
                self.on_entry(side, c, ts_str)
            else:
                if use_c:
                    self._c_snn.decay_traces()
                    self._c_snn.hebbian_idle(spikes)
                    for n in self.neurons:
                        self.rstdp.decay_trace(n.eligibility)
        else:
            pnl_raw = (c - self.entry_price) / self.entry_price
            curr_unrealized = pnl_raw if self.pos == 1 else -pnl_raw
            curr_levered = curr_unrealized * self.leverage

            if use_c:
                self._c_snn.accumulate(spikes)
                if self._has_prev_pnl:
                    self._c_snn.micro_reward(self.prev_unrealized, curr_levered)
                self._c_snn.decay_traces()
            else:
                for i, n in enumerate(self.neurons):
                    inp = spikes if i < BUY_N else -spikes
                    self.rstdp.accumulate(n.eligibility, inp, n.output)
                if self._has_prev_pnl:
                    for n in self.neurons:
                        self.rstdp.micro_reward(n.nucleus, n.eligibility, self.prev_unrealized, curr_levered)
                for n in self.neurons:
                    self.rstdp.decay_trace(n.eligibility)

            self.prev_unrealized = curr_levered
            self._has_prev_pnl = True

            close_reason = None
            if self.sl > 0 and curr_levered <= -self.sl:
                close_reason = "SL"
            elif self.tp > 0 and curr_levered >= self.tp:
                close_reason = "TP"
            elif self.candle_count - self.entry_candle >= self.max_hold:
                close_reason = "TIME"
            elif (self.pos == 1 and action == -1) or (self.pos == -1 and action == 1):
                close_reason = "SIGNAL"

            if close_reason:
                if use_c:
                    self._c_snn.commit(pnl_raw, self.pos)
                else:
                    for n in self.neurons:
                        _, net = self.rstdp.commit(n.nucleus, n.eligibility, pnl_raw, self.pos)
                levered_pnl = curr_levered
                self.equity *= (1.0 + levered_pnl)
                self.rstdp.commit_stats(levered_pnl)
                self.trades += 1
                self.total_pnl += levered_pnl
                if levered_pnl > 0:
                    self.wins += 1
                if use_c:
                    self._sync_weights_from_c()
                    self._save_full_state_to_db()
                    self._neurogenesis_cycle()
                side = "BUY" if self.pos == 1 else "SELL"
                self.on_exit(side, c, levered_pnl, close_reason, ts_str)
                self.pos = 0
                self._has_prev_pnl = False

            self.equity_curve.append(self.equity)

        if self.candle_count % 100 == 0 or self.candle_count <= 10:
            log_fn = getattr(self, '_log', print)
            extra = ""
            if order_book is not None:
                extra = f" book_imb={spikes[8]:.2f}"
            if trade_tape is not None:
                extra += f" cvd={spikes[11]:.2f}"
            llog_fn("SYS", f"Candle#{self.candle_count}: {self.symbol} ${c:.4f} buy={buy_val:.3f} sell={sell_val:.3f} th={th_val:.3f} base_th={self._base_threshold:.2f} pos={self.pos} action={action}{extra}")
            if action != 0:
                log_fn("SYS", f"!!! SIGNAL: {'BUY' if action==1 else 'SELL'} @ ${c:.4f} (buy={buy_val:.3f} sell={sell_val:.3f} th={th_val:.3f} base_th={self._base_threshold:.2f})")
            self._log_state(ts_str, buy_val, sell_val, th_val, self.equity, self.epsilon)

        sys.stdout.flush()
        return action

    def _log_state(self, ts_str, buy, sell, th, equity, eps):
        print(f"{ts_str} Eq=${equity:.4f} buy={buy:.3f} sell={sell:.3f} th={th:.3f} eps={eps:.3f}")

    def on_entry(self, side, price, ts_str):
        print(f"{ts_str} {side} @ ${price:.6f} ({self.leverage}x)")

    def on_exit(self, side, price, pnl_pct, reason, ts_str):
        print(f"{ts_str} {reason} @ ${price:.6f} PnL={pnl_pct*100:.2f}% Eq=${self.equity:.4f}")

    def summary(self):
        wr = 100.0 * self.wins / self.trades if self.trades else 0
        print(f"\n=== TRADING SUMMARY ===")
        print(f"Symbol: {self.symbol} | Leverage: {self.leverage}x")
        print(f"Candles: {self.candle_count} | Trades: {self.trades} | WR: {wr:.1f}%")
        print(f"Total PnL: {self.total_pnl*100:.2f}%")
        print(f"Equity: ${self.equity:.6f} ({(self.equity/INITIAL_EQUITY-1)*100:.2f}%)")
