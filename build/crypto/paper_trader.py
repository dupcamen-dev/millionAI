"""SNN Crypto Paper Trader — Million v0.3
Binance WebSocket 5m klines → R-STDP inference → paper trading log.

Usage:
    python paper_trader.py                         # default: BTCUSDT
    python paper_trader.py --symbol ETHUSDT --config best_config.json

Requires: pip install websocket-client numpy
"""
import argparse, json, os, sys, time, math
import numpy as np

# ─────────────── OHLCV → 8-channel encoding ───────────────
def encode_ohlcv(o, h, l, c, v, vol_history):
    spread = max(h - l, 1e-8)
    spikes = np.zeros(8, dtype=np.float32)
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

# ─────────────── Archive projection (integer hash, matches C) ───────────────
ARCHIVE_PROJ = lambda i, j, l: (float(((i * 13) ^ (j * 7) ^ (l * 5)) % 31 - 15) / 15.0)

def archive_unfold(nucleus, level=1):
    """nucleus[64] → unfolded[256]"""
    N = len(nucleus)
    unfolded = np.zeros(N * 4, dtype=np.float32)
    for i in range(N * 4):
        s = sum(nucleus[j] * ARCHIVE_PROJ(i, j, level) for j in range(N))
        unfolded[i] = math.tanh(s / N)
    return unfolded

def archive_compress(unfolded, out_size=64):
    """unfolded[256] → compressed[out_size]"""
    in_size = len(unfolded)
    group = in_size // out_size
    compressed = np.zeros(out_size, dtype=np.float32)
    for i in range(out_size):
        start = i * group
        s = sum(unfolded[start + j] for j in range(group) if start + j < in_size)
        compressed[i] = math.tanh(s / group)
    return compressed

# ─────────────── Trading Neuron ───────────────
class TradingNeuron:
    def __init__(self, nucleus):
        self.nucleus = np.array(nucleus, dtype=np.float32)
        self.potential = 0.0
        self.threshold = 0.3
        self.output = 0.0
        self.refr = 0
        self.eligibility = np.zeros(64, dtype=np.float32)

    def forward(self, input_vec):
        if self.refr > 0:
            self.refr -= 1
            self.output = 0.0
            return
        unfolded = archive_unfold(self.nucleus, 1)
        state = archive_compress(unfolded, 64)
        delta = np.dot(input_vec[:8], state[:8]) / 8.0
        self.potential += delta
        if self.potential >= self.threshold:
            self.output = self.potential
            self.potential = 0.0
            self.refr = 0
            self.threshold = 0.5 + (self.threshold - 0.5) * 0.9 + 0.1 * abs(self.output)
        else:
            self.output = 0.0
            self.potential *= 0.95

# ─────────────── Paper Trader ───────────────
class PaperTrader:
    def __init__(self, config_file=None):
        self.neurons = []
        self.vol_history = []
        self.pos = 0        # 0=none, 1=long, -1=short
        self.entry_price = 0.0
        self.equity = 10000.0
        self.trades = 0
        self.wins = 0
        self.total_pnl = 0.0
        self.trade_log = []

        if config_file and os.path.exists(config_file):
            self.load_config(config_file)
        else:
            self.init_random()

    def init_random(self):
        for _ in range(8):   # BUY neurons
            nuc = np.random.uniform(-5, 5, 64).astype(np.float32)
            self.neurons.append(TradingNeuron(nuc))
        for _ in range(8):   # SELL neurons (same structure, negated input)
            nuc = np.random.uniform(-5, 5, 64).astype(np.float32)
            self.neurons.append(TradingNeuron(nuc))

    def load_config(self, path):
        data = json.load(open(path))
        for nuc_data in data["neurons"]:
            self.neurons.append(TradingNeuron(np.array(nuc_data, dtype=np.float32)))

    def save_config(self, path):
        data = {"neurons": [n.nucleus.tolist() for n in self.neurons]}
        json.dump(data, open(path, "w"))

    def act(self, o, h, l, c, v):
        spikes = encode_ohlcv(o, h, l, c, v, self.vol_history)

        # Forward BUY neurons (0-7) with normal input
        for i in range(8):
            self.neurons[i].forward(spikes)
        # Forward SELL neurons (8-15) with negated input
        neg_spikes = -spikes
        for i in range(8):
            self.neurons[8 + i].forward(neg_spikes)

        # Decision
        buy_max = max(n.output for n in self.neurons[:8]) if self.neurons else 0
        sell_max = max(n.output for n in self.neurons[8:]) if len(self.neurons) > 8 else 0
        thresh = self.neurons[0].threshold if self.neurons else 0.3
        action = 0
        if buy_max > thresh and buy_max >= sell_max:
            action = 1
        elif sell_max > thresh and sell_max > buy_max:
            action = -1

        # R-STDP
        tau = 24.0
        decay = math.exp(-1.0 / tau)
        for i, n in enumerate(self.neurons):
            s = n.eligibility
            inp = spikes if i < 8 else neg_spikes
            dt = n.output - 0.5
            stdp_kernel = inp[:8] * dt * math.exp(-abs(dt))
            # Accumulate eligibility (using first 8 elements matching input size)
            s[:8] += stdp_kernel
            s *= decay

        return action, spikes

    def on_candle(self, o, h, l, c, v, ts=None):
        action, spikes = self.act(o, h, l, c, v)
        pnl_raw = (c - self.entry_price) / self.entry_price if self.entry_price else 0

        ts_str = ts.strftime("%Y-%m-%d %H:%M") if hasattr(ts, 'strftime') else time.strftime("%Y-%m-%d %H:%M")

        if self.pos == 0:
            if action == 1:
                self.pos = 1
                self.entry_price = c
                sys.stdout.write(f"{ts_str} BUY  @ {c:.2f}\n")
            elif action == -1:
                self.pos = -1
                self.entry_price = c
                sys.stdout.write(f"{ts_str} SELL @ {c:.2f}\n")
        else:
            pnl_with_sign = pnl_raw if self.pos == 1 else -pnl_raw
            # SL/TP check
            sl, tp = 0.05, 0.12
            close_reason = None
            if pnl_with_sign <= -sl:
                close_reason = "SL"
            elif pnl_with_sign >= tp:
                close_reason = "TP"
            elif (self.pos == 1 and action == -1) or (self.pos == -1 and action == 1):
                close_reason = "SIGNAL"

            if close_reason:
                # R-STDP commit (simplified: update weights)
                fee = 0.002
                reward = math.tanh(10.0 * (pnl_with_sign - fee))
                for n in self.neurons:
                    n.nucleus[:8] += 0.01 * n.eligibility[:8] * reward
                    n.eligibility.fill(0)

                self.equity *= (1.0 + pnl_with_sign)
                self.trades += 1
                self.total_pnl += pnl_with_sign
                if pnl_with_sign > 0:
                    self.wins += 1
                self.trade_log.append(f"{ts_str} {close_reason} @ {c:.2f} PnL={pnl_with_sign*100:.2f}% Eq={self.equity:.2f}")
                sys.stdout.write(f"{ts_str} {close_reason} @ {c:.2f} PnL={pnl_with_sign*100:.2f}% Eq={self.equity:.2f}\n")
                self.pos = 0
                self.entry_price = 0.0

        sys.stdout.flush()
        return action

    def summary(self):
        wr = 100.0 * self.wins / self.trades if self.trades > 0 else 0
        print(f"\n=== PAPER TRADING SUMMARY ===")
        print(f"Trades: {self.trades}")
        print(f"Winrate: {wr:.1f}%")
        print(f"Total PnL: {self.total_pnl*100:.2f}%")
        print(f"Equity: ${self.equity:.2f} ({((self.equity/10000)-1)*100:.2f}%)")

# ─────────────── WebSocket listener ───────────────
def binance_ws_listener(trader, symbol="BTCUSDT", interval="5m"):
    import threading
    import websocket

    url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@kline_{interval}"
    last_close_time = 0

    def on_message(ws, msg):
        nonlocal last_close_time
        try:
            data = json.loads(msg)
            k = data.get("k", {})
            if k.get("x", False):  # kline closed
                ct = k["T"]
                if ct <= last_close_time:
                    return
                last_close_time = ct
                o, h, l, c, v = float(k["o"]), float(k["h"]), float(k["l"]), float(k["c"]), float(k["v"])
                t = time.localtime(k["t"] / 1000)
                trader.on_candle(o, h, l, c, v, t)
        except Exception as e:
            sys.stderr.write(f"WS error: {e}\n")

    def on_error(ws, error):
        sys.stderr.write(f"WS error: {error}\n")

    def on_close(ws, close_status, close_msg):
        sys.stdout.write("WS closed\n")

    def on_open(ws):
        sys.stdout.write(f"Connected to {symbol} {interval}\n")

    ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_message,
                                 on_error=on_error, on_close=on_close)
    ws.run_forever()

# ─────────────── Main ───────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SNN Crypto Paper Trader")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--config", default=None, help="JSON with pretrained weights")
    parser.add_argument("--interval", default="5m")
    args = parser.parse_args()

    trader = PaperTrader(config_file=args.config)
    sys.stdout.write(f"Paper Trader starting: {args.symbol} {args.interval}\n")
    sys.stdout.write(f"Initial equity: ${trader.equity:.2f}\n")
    sys.stdout.flush()

    try:
        binance_ws_listener(trader, args.symbol, args.interval)
    except KeyboardInterrupt:
        trader.summary()
