"""SNN Crypto Paper Trader v0.5 — Futures + Auto-Asset + Telegram
Binance Futures WebSocket 5m -> R-STDP + micro-rewards + leverage.

Usage:
    python paper_trader.py --mode futures --auto-asset --telegram TOKEN
    python paper_trader.py --symbol PEPEUSDT --mode futures --leverage 3
"""
import argparse, json, os, sys, time, math, threading, queue, subprocess, urllib.request, urllib.error, random
from datetime import datetime, timezone
import numpy as np
from collections import deque

SENSORY = 8; ARCHIVE_N = 64; BUY_N = 8; SELL_N = 8; TOTAL_N = BUY_N + SELL_N
INITIAL_EQUITY = 10.0
FAPI_BASE = "https://fapi.binance.com"
DATA_DIR = os.path.dirname(__file__)

# ─────────── Arch projection ───────────
def arch_proj(i, j, l):
    return float(((i * 13) ^ (j * 7) ^ (l * 5)) % 31 - 15) / 15.0

def archive_unfold(nucleus, level=1):
    N = len(nucleus); unfolded = np.zeros(N * 4, dtype=np.float32)
    for i in range(N * 4):
        s = sum(nucleus[j] * arch_proj(i, j, level) for j in range(N))
        unfolded[i] = math.tanh(s / N)
    return unfolded

def archive_compress(unfolded, out_size=64):
    in_size = len(unfolded); group = in_size // out_size
    compressed = np.zeros(out_size, dtype=np.float32)
    for i in range(out_size):
        start = i * group; end = min(start + group, in_size)
        compressed[i] = sum(unfolded[start:end]) / (end - start)
    return compressed

# ─────────── OHLCV encoding ───────────
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
    if len(vol_history) > 20: vol_history.pop(0)
    vol_sma = np.mean(vol_history) if vol_history else v
    spikes[5] = min(v / vol_sma, 3.0) if vol_sma > 1e-8 else 1.0
    spikes[6] = max(-1.0, min(1.0, (c - o) / spread))
    spikes[7] = (c - l) / spread
    return spikes

# ─────────── Binance Futures API helpers ───────────
def fapi_get(path, params=None):
    url = f"{FAPI_BASE}{path}"
    if params: url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        sys.stderr.write(f"FAPI error {path}: {e}\n")
        return None

def download_futures_klines(symbol, interval="5m", limit=1500):
    limit = min(limit, 1500)
    raw = fapi_get("/fapi/v1/klines", {"symbol": symbol.upper(), "interval": interval, "limit": limit})
    if not raw: return None
    data = np.zeros((len(raw), 5), dtype=np.float32)
    for i, k in enumerate(raw):
        data[i] = [float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])]
    return data

def get_funding_rate(symbol):
    try:
        r = fapi_get("/fapi/v1/premiumIndex", {"symbol": symbol.upper()})
        return float(r["lastFundingRate"]) if r and "lastFundingRate" in r else 0.0
    except: return 0.0

# ─────────── Asset Screener ───────────
class AssetScreener:
    def __init__(self, data_dir):
        self.data_dir = os.path.join(data_dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.rank_file = os.path.join(self.data_dir, "asset_rank.json")

    def scan(self, top_n=5):
        print("[Screener] Scanning Binance Futures...")
        info = fapi_get("/fapi/v1/exchangeInfo")
        if not info: return []
        tickers = fapi_get("/fapi/v1/ticker/24hr")
        if not tickers: return []
        ticker_map = {t["symbol"]: t for t in tickers}

        candidates = []
        for s in info.get("symbols", []):
            if not s["symbol"].endswith("USDT"): continue
            if s["status"] != "TRADING": continue
            if s["contractType"] != "PERPETUAL": continue
            t = ticker_map.get(s["symbol"])
            if not t: continue
            price = float(t.get("lastPrice", 0) or 0)
            vol_usdt = float(t.get("quoteVolume", 0) or 0)
            if price <= 0 or price >= 1000: continue
            if vol_usdt < 100_000_000: continue
            klines = download_futures_klines(s["symbol"], "5m", 100)
            if klines is None or len(klines) < 20: continue
            atr = np.mean([max(klines[i,2]-klines[i,3],
                               abs(klines[i,2]-klines[i-1,3]),
                               abs(klines[i,3]-klines[i-1,3]))
                          for i in range(1, len(klines), 5)])
            vol_ratio = atr / price
            score = vol_ratio * math.log(max(vol_usdt, 1e6)) / price
            try:
                fund_rate = get_funding_rate(s["symbol"])
            except:
                fund_rate = 0.0
            candidates.append({
                "symbol": s["symbol"],
                "price": float(price),
                "volume": float(vol_usdt),
                "volatility": float(vol_ratio * 100),
                "score": float(score),
                "funding": float(fund_rate)
            })
        candidates.sort(key=lambda x: -x["score"])
        top = candidates[:top_n]
        with open(self.rank_file, "w") as f:
            json.dump({"timestamp": time.time(), "assets": top}, f, indent=2)
        print(f"[Screener] Top-{len(top)} assets (price<$1000, vol>$100M):")
        for i, a in enumerate(top):
            print(f"  {i+1}. {a['symbol']} — score:{a['score']:.1f} vol:{a['volatility']:.2f}% liq:${a['volume']/1e6:.0f}M price:${a['price']:.4f} fund:{a['funding']*100:.4f}%")
        return top

# ─────────── Trading Neuron ───────────
class TradingNeuron:
    def __init__(self, nucleus=None, nucleus_size=ARCHIVE_N):
        if nucleus is not None:
            self.nucleus = np.array(nucleus, dtype=np.float32)
        else:
            fan = nucleus_size + nucleus_size
            scale = math.sqrt(6.0 / fan)
            self.nucleus = np.random.uniform(-scale, scale, nucleus_size).astype(np.float32)
        self.bias = 1.0; self.potential = 0.0
        self.threshold = 0.5; self.output = 0.0
        self.refr = 0; self.decay = 0.99
        self.eligibility = np.zeros(nucleus_size, dtype=np.float32)

    def forward(self, input_vec):
        if self.refr > 0:
            self.refr -= 1; self.output = 0.0; return
        unfolded = archive_unfold(self.nucleus, 1)
        state = archive_compress(unfolded, ARCHIVE_N)
        delta = np.dot(input_vec[:SENSORY], state[:SENSORY]) / float(SENSORY) + self.bias
        self.potential += delta
        if self.potential >= self.threshold:
            self.output = self.potential; self.potential = 0.0; self.refr = 0
            self.threshold = 0.5 + (self.threshold - 0.5) * 0.9 + 0.1 * abs(self.output)
        else:
            self.output = 0.0; self.potential *= self.decay

# ─────────── R-STDP Engine ───────────
class RSTDPEngine:
    def __init__(self, lr=0.01, tau=24.0):
        self.lr = lr; self.lr_0 = lr
        self.decay = math.exp(-1.0 / tau)
        self.reward_k = 10.0; self.fee_pct = 0.002
        self.micro_lr_scale = 0.1
        self.total_pnl = 0.0; self.trades = 0; self.wins = 0; self.trades_total = 0

    def accumulate(self, eligibility, input_vec, output):
        n = min(len(eligibility), len(input_vec))
        for i in range(n):
            dt = output - 0.5
            eligibility[i] += input_vec[i] * dt * math.exp(-abs(dt))

    def decay_trace(self, eligibility):
        eligibility *= self.decay

    def micro_reward(self, nucleus, eligibility, prev_pnl, curr_pnl):
        change = curr_pnl - prev_pnl
        reward = math.tanh(self.reward_k * 0.3 * change)
        nucleus[:len(eligibility)] += self.lr * self.micro_lr_scale * eligibility * reward
        return reward

    def commit(self, nucleus, eligibility, pnl_pct, side):
        net = pnl_pct * side - self.fee_pct
        reward = math.tanh(self.reward_k * net)
        nucleus[:len(eligibility)] += self.lr * eligibility * reward
        eligibility.fill(0)
        return reward, net

    def commit_stats(self, net_pnl):
        self.total_pnl += net_pnl; self.trades += 1; self.trades_total += 1
        if net_pnl > 0: self.wins += 1
        self.lr = self.lr_0 / (1.0 + 0.01 * self.trades_total)

    def set_tau(self, tau_candles):
        self.decay = math.exp(-1.0 / tau_candles)

    def adaptive_tau(self, atr, atr_median):
        if atr_median > 1e-8:
            vol = atr / atr_median; tau = 24.0 * (1.0 + vol)
            self.set_tau(max(tau, 4.0))

# ─────────── Experience Replay ───────────
class ExperienceReplay:
    def __init__(self, maxlen=1000):
        self.buffer = deque(maxlen=maxlen)

    def add(self, spikes, action, entry_price, unrealized_pnl):
        self.buffer.append((spikes.copy(), action, entry_price, unrealized_pnl))

    def sample(self, batch_size=32):
        if len(self.buffer) < batch_size: return None
        idx = np.random.choice(len(self.buffer), batch_size, replace=False)
        return [self.buffer[i] for i in idx]

# ─────────── Telegram Bot ───────────
class TelegramBot:
    def __init__(self, token, trader_ref, msg_queue, data_dir="."):
        self.token = token; self.base = f"https://api.telegram.org/bot{token}"
        self.trader = trader_ref; self.msg_queue = msg_queue
        self.chat_ids = set(); self.offset = 0; self.running = True
        self.chat_file = os.path.join(data_dir, "telegram_chats.json")
        self.load_chats()

    def load_chats(self):
        try:
            with open(self.chat_file) as f: self.chat_ids = set(json.load(f))
        except: self.chat_ids = set()

    def save_chats(self):
        try:
            with open(self.chat_file, "w") as f: json.dump(list(self.chat_ids), f)
        except: pass

    def _req(self, method, data):
        url = f"{self.base}/{method}"
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except: return None

    def send(self, chat_id, text):
        self._req("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

    def broadcast(self, text):
        for cid in list(self.chat_ids): self.send(cid, text)

    def handle(self, chat_id, text):
        text = text.strip().lower(); t = self.trader
        if text == "/start":
            self.send(chat_id, "SNN Paper Trader v0.5 Futures\n"
                      f"Asset: {t.symbol} | Mode: {t.mode} | Leverage: {t.leverage}x\n"
                      "/status\n/summary\n/save\n/chart\n/assets")
        elif text == "/status":
            pos_str = {0: "None", 1: "LONG", -1: "SHORT"}.get(t.pos, "?")
            msg = f"${t.equity:.2f} | {pos_str} | Lev:{t.leverage}x"
            if t.pos and t.entry_price:
                pnl = (t.last_close - t.entry_price) / t.entry_price
                if t.pos == -1: pnl = -pnl
                msg += f"\nEntry: ${t.entry_price:.6f} UPnL:{pnl*100:.2f}%"
            self.send(chat_id, msg)
        elif text == "/summary":
            wr = 100.0 * t.wins / t.trades if t.trades else 0
            self.send(chat_id, f"Trades:{t.trades} WR:{wr:.1f}% PnL:{t.total_pnl*100:.2f}% Eq:${t.equity:.2f}")
        elif text == "/save":
            p = os.path.join(os.path.dirname(__file__), "best_config.json")
            t.save_config(p)
            self.send(chat_id, f"Saved to {p}")
        elif text == "/assets":
            p = os.path.join(t.data_dir, "data", "asset_rank.json")
            try:
                with open(p) as f: d = json.load(f)
                msg = "Top assets:\n" + "\n".join(f"{a['symbol']} score:{a['score']:.1f}" for a in d["assets"])
            except: msg = "No ranking"
            self.send(chat_id, msg)
        elif text == "/chart":
            if len(t.equity_curve) > 1:
                p = os.path.join(os.path.dirname(__file__), "eq.csv")
                with open(p, "w") as f:
                    f.write("candle,eq\n")
                    for i, eq in enumerate(t.equity_curve): f.write(f"{i},{eq:.4f}\n")
                self.send(chat_id, f"Saved {p}")
            else: self.send(chat_id, "Not enough data")

    def run(self):
        self.load_chats()
        while self.running:
            try:
                url = f"{self.base}/getUpdates?offset={self.offset}&timeout=30"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=35) as r:
                    updates = json.loads(r.read()).get("result", [])
                for u in updates:
                    self.offset = u["update_id"] + 1
                    chat_id = u.get("message", {}).get("chat", {}).get("id")
                    if chat_id:
                        self.chat_ids.add(chat_id); self.save_chats()
                        self.handle(chat_id, u["message"].get("text", ""))
            except: pass
            while not self.msg_queue.empty():
                try: self.broadcast(self.msg_queue.get_nowait())
                except queue.Empty: break

# ─────────── ATR Tracker ───────────
class ATRTracker:
    def __init__(self, period=14):
        self.period = period; self.tr_buffer = []; self.prev_close = None

    def update(self, o, h, l, c):
        if self.prev_close is None:
            self.prev_close = c; tr = h - l
        else:
            tr = max(h - l, abs(h - self.prev_close), abs(l - self.prev_close))
            self.prev_close = c
        self.tr_buffer.append(tr)
        if len(self.tr_buffer) > self.period: self.tr_buffer.pop(0)
        atr = np.mean(self.tr_buffer) if self.tr_buffer else tr
        median = np.median(self.tr_buffer) if len(self.tr_buffer) > 3 else atr
        return atr, max(median, 1e-8)

# ─────────── Quick Python Backtest (for auto-leverage) ───────────
def quick_backtest(data, lr=0.01, tau=24.0, thresh=0.3, sl=0.05, tp=0.12, fee=0.002, use_micro=1):
    neurons = [TradingNeuron() for _ in range(TOTAL_N)]
    rstdp = RSTDPEngine(lr=lr, tau=tau)
    split = int(len(data) * 0.8)
    vol_hist = []
    pnls = []
    for phase, start, end in [("train", 5, split), ("test", split, len(data))]:
        pos = 0; entry_price = 0.0; prev_pnl = 0.0; has_prev = False
        trades = 0; wins = 0; pnl_sum = 0.0
        phase_pnls = []
        for c in range(start, end):
            o, h, l, cl, v = data[c]
            spikes = encode_ohlcv(o, h, l, cl, v, vol_hist)
            neg = -spikes
            for i in range(BUY_N): neurons[i].forward(spikes)
            for i in range(SELL_N): neurons[BUY_N+i].forward(neg)
            buy = max(n.output for n in neurons[:BUY_N]) if neurons else 0
            sell = max(n.output for n in neurons[BUY_N:]) if len(neurons) > BUY_N else 0
            th = neurons[0].threshold if neurons else 0.3
            action = 1 if buy > th and buy >= sell else (-1 if sell > th and sell > buy else 0)
            if pos == 0:
                if action:
                    pos = action; entry_price = cl; has_prev = False
                else:
                    for n in neurons: rstdp.decay_trace(n.eligibility)
            else:
                pnl_raw = (cl - entry_price) / entry_price
                curr = pnl_raw if pos == 1 else -pnl_raw
                for i, n in enumerate(neurons):
                    inp = spikes if i < BUY_N else neg
                    rstdp.accumulate(n.eligibility, inp, n.output)
                if use_micro and has_prev:
                    for n in neurons:
                        rstdp.micro_reward(n.nucleus, n.eligibility, prev_pnl, curr)
                prev_pnl = curr; has_prev = True
                for n in neurons: rstdp.decay_trace(n.eligibility)
                close = 0
                if sl > 0 and curr <= -sl: close = 1
                elif tp > 0 and curr >= tp: close = 1
                elif (pos == 1 and action == -1) or (pos == -1 and action == 1): close = 1
                if close:
                    for i, n in enumerate(neurons):
                        _, net = rstdp.commit(n.nucleus, n.eligibility, pnl_raw, pos)
                    rstdp.commit_stats(net)
                    pos = 0; has_prev = False
                    trades += 1; pnl_sum += curr
                    phase_pnls.append(curr)
                    if curr > 0: wins += 1
        if phase == "test":
            pnls = phase_pnls
            tr = trades; tw = wins; tp = pnl_sum
    avg_pnl = tp / max(tr, 1)
    std_pnl = np.std(pnls) if len(pnls) > 1 else abs(avg_pnl) + 0.001
    wr = tw / max(tr, 1)
    risk_score = wr * avg_pnl * math.sqrt(max(tr, 1)) / max(std_pnl, 0.001)
    trained_weights = [n.nucleus.copy() for n in neurons]
    return {"trades": tr, "wins": tw, "total_pnl": tp, "avg_pnl": avg_pnl,
            "std_pnl": std_pnl, "winrate": wr, "risk_score": risk_score,
            "weights": trained_weights}

# ─────────── Paper Trader ───────────
class PaperTrader:
    def __init__(self,                  symbol="SOLUSDT", mode="futures", leverage=1,
                 config_file=None, lr=0.01, tau=24.0, sl=0.05, tp=0.12,
                 auto_asset=False, telegram_token=None, data_dir=DATA_DIR):
        self.symbol = symbol.upper()
        self.mode = mode
        self.leverage = leverage
        self.neurons = []
        self.vol_history = []
        self.pos = 0; self.entry_price = 0.0; self.last_close = 0.0
        self.equity = INITIAL_EQUITY
        self.trades = 0; self.wins = 0; self.total_pnl = 0.0; self.trades_daily = 0
        self.prev_unrealized = 0.0; self._has_prev_pnl = False
        self.rstdp = RSTDPEngine(lr=lr, tau=tau)
        self.sl = sl; self.tp = tp; self.running = True
        self.msg_queue = queue.Queue()
        self.equity_curve = []; self.candle_count = 0
        self.data_dir = data_dir
        self.atr = ATRTracker(14)
        self.replay = ExperienceReplay(1000)
        self.last_funding_rate = 0.0
        self.last_scan_time = 0
        self.epsilon = 0.15
        self.entry_candle = 0
        self.max_hold = 24
        self.last_candle_time = time.time()
        self.telegram = None

        if telegram_token:
            self.telegram = TelegramBot(telegram_token, self, self.msg_queue, data_dir)
            threading.Thread(target=self.telegram.run, daemon=True).start()

        if auto_asset:
            self.select_best_asset()
        elif config_file and os.path.exists(config_file):
            self.load_config(config_file)
        else:
            self.init_random()

        print(f"Paper Trader v0.5 | {self.symbol} | {self.mode} | {self.leverage}x | Eq=${self.equity:.2f}")

    def select_best_asset(self):
        screener = AssetScreener(self.data_dir)
        assets = screener.scan(5)
        if not assets:
            print("[Auto] No assets found, using SOLUSDT")
            self.symbol = "SOLUSDT"
            self.init_random(); return

        best_asset = None; best_score = -999; best_r = None
        for a in assets[:3]:
            print(f"[Auto] Quick backtesting {a['symbol']}...")
            data = download_futures_klines(a["symbol"], "5m", 500)
            if data is None or len(data) < 200: continue
            t0 = time.time()
            r = quick_backtest(data, lr=self.rstdp.lr_0)
            t1 = time.time()
            if r["trades"] < 3: continue
            print(f"  -> {r['trades']}t, WR:{r['winrate']*100:.1f}%, avg:{r['avg_pnl']*100:.2f}%, risk:{r['risk_score']:.2f} ({t1-t0:.0f}s)")
            if r["risk_score"] > best_score:
                best_score = r["risk_score"]; best_asset = a; best_r = r

        if best_asset is None:
            print("[Auto] Using top ranked asset (fallback)")
            best_asset = assets[0]

        self.symbol = best_asset["symbol"]
        self.last_funding_rate = best_asset.get("funding", 0.0)
        self.leverage = max(1, min(5, round(1 + best_r.get("risk_score", 0) * 2))) if best_r else 1
        print(f"[Auto] Selected {self.symbol} at {self.leverage}x leverage (risk_score={best_score:.2f})")
        score_path = os.path.join(self.data_dir, "data", "current_score.txt")
        os.makedirs(os.path.dirname(score_path), exist_ok=True)
        with open(score_path, "w") as f: f.write(str(best_asset.get("score", 0)))
        if best_r and best_r.get("weights"):
            self.neurons = [TradingNeuron(nucleus=w) for w in best_r["weights"]]
            print(f"[Auto] Loaded trained weights ({len(self.neurons)} neurons)")
        else:
            self.init_random()
        self.tg_notify(f"Auto-selected {self.symbol} {self.leverage}x")

    def init_random(self):
        self.neurons = [TradingNeuron() for _ in range(TOTAL_N)]

    def load_config(self, path):
        with open(path) as f: data = json.load(f)
        self.neurons = [TradingNeuron(nucleus=np.array(n, dtype=np.float32)) for n in data.get("neurons", [])]
        self.leverage = data.get("leverage", self.leverage)
        self.symbol = data.get("symbol", self.symbol)

    def save_config(self, path):
        data = {"symbol": self.symbol, "leverage": self.leverage,
                "neurons": [n.nucleus.tolist() for n in self.neurons]}
        with open(path, "w") as f: json.dump(data, f)

    def tg_notify(self, text):
        if self.telegram: self.msg_queue.put(f"[{self.symbol}] {text}")

    def forward_all(self, spikes):
        neg_spikes = -spikes
        for i in range(BUY_N): self.neurons[i].forward(spikes)
        for i in range(SELL_N): self.neurons[BUY_N + i].forward(neg_spikes)

    def compute_action(self):
        buy = max(n.output for n in self.neurons[:BUY_N]) if self.neurons else 0
        sell = max(n.output for n in self.neurons[BUY_N:]) if len(self.neurons) > BUY_N else 0
        th = self.neurons[0].threshold if self.neurons else 0.3
        if buy > th and buy >= sell: return 1
        if sell > th and sell > buy: return -1
        # epsilon-greedy: if no signal and we have been idle, force explore
        if random.random() < self.epsilon:
            return random.choice([1, -1])
        return 0

    def on_candle(self, o, h, l, c, v, ts=None):
        self.last_close = c; self.candle_count += 1; self.last_candle_time = time.time()
        spikes = encode_ohlcv(o, h, l, c, v, self.vol_history, self.last_funding_rate)
        atr_val, atr_med = self.atr.update(o, h, l, c)
        self.rstdp.adaptive_tau(atr_val, atr_med)
        ts_str = ts.strftime("%Y-%m-%d %H:%M") if hasattr(ts, 'strftime') else time.strftime("%Y-%m-%d %H:%M")

        self.forward_all(spikes)
        action = self.compute_action()

        if self.pos == 0:
            if action == 1:
                self.pos = 1; self.entry_price = c; self._has_prev_pnl = False; self.entry_candle = self.candle_count
                msg = f"{ts_str} BUY  @ ${c:.6f} ({self.leverage}x)"
                print(msg); self.tg_notify(msg)
            elif action == -1:
                self.pos = -1; self.entry_price = c; self._has_prev_pnl = False; self.entry_candle = self.candle_count
                msg = f"{ts_str} SELL @ ${c:.6f} ({self.leverage}x)"
                print(msg); self.tg_notify(msg)
            else:
                self.epsilon = max(0.02, self.epsilon * 0.999)
                for n in self.neurons: self.rstdp.decay_trace(n.eligibility)
        else:
            pnl_raw = (c - self.entry_price) / self.entry_price
            curr_unrealized = pnl_raw if self.pos == 1 else -pnl_raw
            curr_levered = curr_unrealized * self.leverage

            for i, n in enumerate(self.neurons):
                inp = spikes if i < BUY_N else -spikes
                self.rstdp.accumulate(n.eligibility, inp, n.output)

            if self._has_prev_pnl:
                for n in self.neurons:
                    self.rstdp.micro_reward(n.nucleus, n.eligibility,
                                           self.prev_unrealized, curr_levered)
            self.prev_unrealized = curr_levered; self._has_prev_pnl = True

            for n in self.neurons: self.rstdp.decay_trace(n.eligibility)
            self.replay.add(spikes, action, self.entry_price, curr_levered)

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
                total_net = 0.0
                for i, n in enumerate(self.neurons):
                    _, net = self.rstdp.commit(n.nucleus, n.eligibility, pnl_raw, self.pos)
                    total_net = net
                levered_pnl = curr_levered
                self.equity *= (1.0 + levered_pnl)
                self.rstdp.commit_stats(total_net)
                self.trades += 1; self.trades_daily += 1
                self.total_pnl += levered_pnl
                if levered_pnl > 0: self.wins += 1
                self.pos = 0; self._has_prev_pnl = False
                msg = f"{ts_str} {close_reason} @ ${c:.6f} PnL={levered_pnl*100:.2f}% Eq=${self.equity:.4f}"
                print(msg); self.tg_notify(msg)

            self.equity_curve.append(self.equity)

        if self.candle_count % 100 == 0 or self.candle_count <= 3:
            buy = max(n.output for n in self.neurons[:BUY_N]) if self.neurons else 0
            sell = max(n.output for n in self.neurons[BUY_N:]) if len(self.neurons) > BUY_N else 0
            th = self.neurons[0].threshold if self.neurons else 0.3
            print(f"{ts_str} Eq=${self.equity:.4f} buy={buy:.3f} sell={sell:.3f} th={th:.3f} eps={self.epsilon:.3f}")

        # Auto-rotation every 288 candles (~24h at 5m)
        if self.candle_count - self.last_scan_time > 288:
            self.check_asset_rotation()
            self.last_scan_time = self.candle_count

        sys.stdout.flush()
        return action

    def check_asset_rotation(self):
        p = os.path.join(self.data_dir, "data", "asset_rank.json")
        if not os.path.exists(p): return
        try:
            with open(p) as f: d = json.load(f)
            if time.time() - d.get("timestamp", 0) > 3600:
                # Re-scan
                screener = AssetScreener(self.data_dir)
                assets = screener.scan(5)
                if not assets: return
            else:
                assets = d.get("assets", [])
            if not assets or assets[0]["symbol"] == self.symbol: return
            new_score = assets[0]["score"]
            try:
                with open(os.path.join(self.data_dir, "data", "current_score.txt")) as f:
                    cur_score = float(f.read().strip())
            except:
                cur_score = 0
            if new_score > cur_score * 1.3:
                print(f"[Rotation] {assets[0]['symbol']} ({new_score:.1f}) > {self.symbol} ({cur_score:.1f}) x1.3")
                data = download_futures_klines(assets[0]["symbol"], "5m", 500)
                if data is not None and len(data) > 200:
                    r = quick_backtest(data)
                    if r["risk_score"] > 0.5:
                        self.symbol = assets[0]["symbol"]
                        self.leverage = max(1, min(5, round(1 + r["risk_score"] * 2)))
                        if r.get("weights"):
                            self.neurons = [TradingNeuron(nucleus=w) for w in r["weights"]]
                        else:
                            self.init_random()
                        self.last_funding_rate = assets[0].get("funding", 0.0)
                        self.tg_notify(f"Rotated to {self.symbol} {self.leverage}x")
                        with open(os.path.join(self.data_dir, "data", "current_score.txt"), "w") as f:
                            f.write(str(new_score))
        except Exception as e:
            print(f"[Rotation] Error: {e}")

    def summary(self):
        wr = 100.0 * self.wins / self.trades if self.trades else 0
        print(f"\n=== PAPER TRADING SUMMARY ===")
        print(f"Symbol: {self.symbol} | Mode: {self.mode} | Leverage: {self.leverage}x")
        print(f"Candles: {self.candle_count} | Trades: {self.trades} | WR: {wr:.1f}%")
        print(f"Total PnL: {self.total_pnl*100:.2f}%")
        print(f"Equity: ${self.equity:.6f} ({(self.equity/INITIAL_EQUITY-1)*100:.2f}%)")



# ─────────── WebSocket listener (Futures) ───────────
def binance_ws_listener(trader, symbol="SOLUSDT", interval="5m"):
    import websocket
    url = f"wss://fstream.binance.com/market/ws/{symbol.lower()}@kline_{interval}"
    last_close_time = 0

    def on_message(ws, msg):
        nonlocal last_close_time
        trader.last_candle_time = time.time()  # WS heartbeat
        try:
            data = json.loads(msg)
            k = data.get("k", {})
            if k.get("x", False):
                ct = k["T"]
                if ct <= last_close_time: return
                last_close_time = ct
                o, h, l, c, v = float(k["o"]), float(k["h"]), float(k["l"]), float(k["c"]), float(k["v"])
                t = time.localtime(k["t"] / 1000)
                # Update funding rate every hour
                if trader.candle_count % 12 == 0:
                    try: trader.last_funding_rate = get_funding_rate(trader.symbol)
                    except: pass
                trader.on_candle(o, h, l, c, v, t)
        except Exception as e:
            sys.stderr.write(f"WS: {e}\n")

    def on_error(ws, error):
        sys.stderr.write(f"WS error: {error}\n")

    def on_close(ws, close_status, close_msg):
        sys.stdout.write("WS closed, reconnecting...\n"); time.sleep(5); ws.run_forever()

    def on_open(ws):
        sys.stdout.write(f"Futures WS connected: {symbol} {interval}\n")

    ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_message,
                                 on_error=on_error, on_close=on_close)
    ws.run_forever()

# ─────────── Main ───────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SNN Paper Trader v0.5 Futures")
    parser.add_argument("--symbol", default="SOLUSDT")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--mode", choices=["spot", "futures"], default="futures")
    parser.add_argument("--leverage", type=int, default=1)
    parser.add_argument("--auto-asset", action="store_true", help="Auto-select best futures asset")
    parser.add_argument("--config", default=None)
    parser.add_argument("--telegram", default=None)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--tau", type=float, default=24.0)
    parser.add_argument("--sl", type=float, default=0.05)
    parser.add_argument("--tp", type=float, default=0.12)
    parser.add_argument("--data-dir", default=DATA_DIR)
    args = parser.parse_args()

    if not args.telegram:
        args.telegram = os.environ.get("TELEGRAM_TOKEN")

    trader = PaperTrader(symbol=args.symbol, mode=args.mode, leverage=args.leverage,
                         config_file=args.config, lr=args.lr, tau=args.tau,
                         sl=args.sl, tp=args.tp, auto_asset=args.auto_asset,
                         telegram_token=args.telegram, data_dir=args.data_dir)

    try:
        binance_ws_listener(trader, trader.symbol, args.interval)
    except KeyboardInterrupt:
        trader.running = False
        trader.summary()
        trader.save_config(os.path.join(args.data_dir, "best_config.json"))
