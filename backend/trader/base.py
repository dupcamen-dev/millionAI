import json
import math
import os
import random
import sys
import time
from collections import deque

import numpy as np

from snn.encoding import encode_ohlcv, SENSORY, BUY_N, SELL_N, TOTAL_N
from snn.neuron import TradingNeuron, ARCHIVE_N
from snn.rstpd import RSTDPEngine

INITIAL_EQUITY = 10.0

class BaseTrader:
    def __init__(self, symbol="SOLUSDT", leverage=1, config_file=None, lr=0.01, tau=24.0, sl=0.05, tp=0.12):
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

        if config_file and os.path.exists(config_file):
            self.load_config(config_file)
        else:
            self.init_random()

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

    def on_candle(self, o, h, l, c, v, ts=None):
        self.last_close = c
        self.candle_count += 1
        self.last_candle_time = time.time()
        spikes = encode_ohlcv(o, h, l, c, v, self.vol_history)
        self.forward_all(spikes)
        action = self.compute_action()
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
                for n in self.neurons:
                    self.rstdp.decay_trace(n.eligibility)
        else:
            pnl_raw = (c - self.entry_price) / self.entry_price
            curr_unrealized = pnl_raw if self.pos == 1 else -pnl_raw
            curr_levered = curr_unrealized * self.leverage

            for i, n in enumerate(self.neurons):
                inp = spikes if i < BUY_N else -spikes
                self.rstdp.accumulate(n.eligibility, inp, n.output)

            if self._has_prev_pnl:
                for n in self.neurons:
                    self.rstdp.micro_reward(n.nucleus, n.eligibility, self.prev_unrealized, curr_levered)
            self.prev_unrealized = curr_levered
            self._has_prev_pnl = True

            for n in self.neurons:
                self.rstdp.decay_trace(n.eligibility)

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
                for n in self.neurons:
                    _, net = self.rstdp.commit(n.nucleus, n.eligibility, pnl_raw, self.pos)
                levered_pnl = curr_levered
                self.equity *= (1.0 + levered_pnl)
                self.rstdp.commit_stats(levered_pnl)
                self.trades += 1
                self.total_pnl += levered_pnl
                if levered_pnl > 0:
                    self.wins += 1
                side = "BUY" if self.pos == 1 else "SELL"
                self.on_exit(side, c, levered_pnl, close_reason, ts_str)
                self.pos = 0
                self._has_prev_pnl = False

            self.equity_curve.append(self.equity)

        if self.candle_count % 100 == 0 or self.candle_count <= 3:
            buy = max(n.output for n in self.neurons[:BUY_N]) if self.neurons else 0
            sell = max(n.output for n in self.neurons[BUY_N:]) if len(self.neurons) > BUY_N else 0
            th = self.neurons[0].threshold if self.neurons else 0.3
            print(f"{ts_str} Eq=${self.equity:.4f} buy={buy:.3f} sell={sell:.3f} th={th:.3f} eps={self.epsilon:.3f}")

        sys.stdout.flush()
        return action

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
