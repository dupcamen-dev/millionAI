import json
import sys
import time
import threading
import websocket


class BinanceWSListener:
    """Multi-stream WebSocket: kline (primary) + depth + trades.  Direct method callbacks."""

    def __init__(self, on_candle, on_error=None, reconnect_delay=5, log_fn=None):
        self.on_candle_cb = on_candle
        self.on_error_cb = on_error
        self.reconnect_delay = reconnect_delay
        self._last_close_time = 0
        self._last_open_log_ts = 0
        self._lock = threading.Lock()
        self._log = log_fn

        # Trade accumulator per 5-min window
        self._trade_buy_vol = 0.0
        self._trade_sell_vol = 0.0
        self._trade_count = 0
        self._trades_sizes = []

        # Order book cache
        self._order_book = None
        self._depth_received = False
        self._first_trade_logged = False

        # Debug: per-stream message counters
        self._kline_msg_n = 0
        self._depth_msg_n = 0
        self._trade_msg_n = 0

        self._running = True

    def _slog(self, txt):
        if self._log:
            self._log("SYS", txt)

    # ════════════════ Kline callback methods (DIRECT, not lambda) ════════════════
    def _on_kline_msg(self, ws, msg):
        self._kline_msg_n += 1
        try:
            data = json.loads(msg)
            if self._kline_msg_n <= 3:
                preview = str(data)[:250]
                self._slog(f"Kline#{self._kline_msg_n}: {preview}")
            k = data.get("k", {})
            if not k.get("x", False):
                now = time.time()
                if now - self._last_open_log_ts > 300:
                    self._last_open_log_ts = now
                    self._slog(f"Kline alive: ${k.get('c','?')}")
                return
            ct = k["T"]
            with self._lock:
                if ct <= self._last_close_time:
                    return
                self._last_close_time = ct
                o = float(k["o"]); h = float(k["h"]); l = float(k["l"])
                c = float(k["c"]); v = float(k["v"])
                ob = self._order_book[:] if self._order_book else None
                tt = self._build_trade_tape()
                self._trade_buy_vol = 0.0
                self._trade_sell_vol = 0.0
                self._trade_count = 0
                self._trades_sizes = []

            self.on_candle_cb(o, h, l, c, v, k["t"] / 1000,
                              order_book=ob, trade_tape=tt)
        except Exception as e:
            sys.stderr.write(f"[kline] parse: {e}\n")

    def _on_kline_err(self, ws, error):
        sys.stderr.write(f"[kline] WS error: {error}\n")

    def _on_kline_open(self, ws):
        self._slog(f"Kline WS connected: {self._symbol}")

    def _on_kline_close(self, ws, *args):
        sys.stdout.write(f"[kline] closed, reconnecting in {self.reconnect_delay}s...\n")
        time.sleep(self.reconnect_delay)
        if self._running and self._kline_ws:
            self._kline_ws.run_forever()

    def _run_kline(self):
        url = f"wss://fstream.binance.com/ws/{self._symbol.lower()}@kline_{self._interval}"
        self._kline_ws = websocket.WebSocketApp(
            url,
            on_open=self._on_kline_open,
            on_message=self._on_kline_msg,
            on_error=self._on_kline_err,
            on_close=self._on_kline_close,
        )
        self._slog(f"Kline WS starting: {self._symbol}@{self._interval}")
        self._kline_ws.run_forever()

    # ════════════════ Depth callback methods ════════════════
    def _on_depth_msg(self, ws, msg):
        self._depth_msg_n += 1
        try:
            data = json.loads(msg)
            if self._depth_msg_n == 1:
                self._slog(f"Depth#{self._depth_msg_n}: received")
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            if not bids or not asks:
                return
            if not self._depth_received:
                self._depth_received = True
                self._slog(f"Depth data: bid={bids[0][0]} ask={asks[0][0]}")
            bid_qty = sum(float(b[1]) for b in bids[:5])
            ask_qty = sum(float(a[1]) for a in asks[:5])
            best_bid = float(bids[0][0]) if bids else 0
            best_ask = float(asks[0][0]) if asks else 0
            max_bid_qty = max((float(b[1]) for b in bids[:5]), default=0)
            max_ask_qty = max((float(a[1]) for a in asks[:5]), default=0)
            with self._lock:
                self._order_book = [bid_qty, ask_qty, best_bid, best_ask, max_bid_qty, max_ask_qty]
        except Exception:
            pass

    def _on_depth_err(self, ws, error):
        sys.stderr.write(f"[depth] WS error: {error}\n")

    def _on_depth_open(self, ws):
        self._slog(f"Depth WS connected: {self._symbol}")

    def _on_depth_close(self, ws, *args):
        sys.stdout.write(f"[depth] closed, reconnecting...\n")
        time.sleep(self.reconnect_delay)
        if self._running and self._depth_ws:
            self._depth_ws.run_forever()

    def _run_depth(self):
        url = f"wss://fstream.binance.com/ws/{self._symbol.lower()}@depth5@500ms"
        self._depth_ws = websocket.WebSocketApp(
            url,
            on_open=self._on_depth_open,
            on_message=self._on_depth_msg,
            on_error=self._on_depth_err,
            on_close=self._on_depth_close,
        )
        self._slog(f"Depth WS starting: {self._symbol}@depth5")
        self._depth_ws.run_forever()

    # ════════════════ Trade callback methods ════════════════
    def _on_trade_msg(self, ws, msg):
        self._trade_msg_n += 1
        try:
            data = json.loads(msg)
            if self._trade_msg_n == 1:
                self._slog(f"Trade#{self._trade_msg_n}: received")
            if not self._first_trade_logged:
                self._first_trade_logged = True
                self._slog("Trade stream active")
            price = float(data.get("p", 0))
            qty = float(data.get("q", 0))
            is_buyer_maker = data.get("m", False)
            vol = price * qty
            with self._lock:
                if is_buyer_maker:
                    self._trade_sell_vol += vol
                else:
                    self._trade_buy_vol += vol
                self._trade_count += 1
                self._trades_sizes.append(qty)
        except Exception:
            pass

    def _on_trade_err(self, ws, error):
        sys.stderr.write(f"[trade] WS error: {error}\n")

    def _on_trade_open(self, ws):
        self._slog(f"Trade WS connected: {self._symbol}")

    def _on_trade_close(self, ws, *args):
        sys.stdout.write(f"[trade] closed, reconnecting...\n")
        time.sleep(self.reconnect_delay)
        if self._running and self._trade_ws:
            self._trade_ws.run_forever()

    def _run_trade(self):
        url = f"wss://fstream.binance.com/ws/{self._symbol.lower()}@aggTrade"
        self._trade_ws = websocket.WebSocketApp(
            url,
            on_open=self._on_trade_open,
            on_message=self._on_trade_msg,
            on_error=self._on_trade_err,
            on_close=self._on_trade_close,
        )
        self._slog(f"Trade WS starting: {self._symbol}@aggTrade")
        self._trade_ws.run_forever()

    # ── Helpers ─────────────────────────────────────
    def _build_trade_tape(self):
        if self._trade_count == 0:
            return None
        if len(self._trades_sizes) > 1:
            sorted_trades = sorted(self._trades_sizes)
            median = sorted_trades[len(sorted_trades) // 2]
            large_count = sum(1 for q in self._trades_sizes if q > 2 * median)
            large_ratio = large_count / len(self._trades_sizes)
        else:
            large_ratio = 0.0
        return [self._trade_buy_vol, self._trade_sell_vol,
                float(self._trade_count), large_ratio]

    # ── Public API ──────────────────────────────────
    def connect(self, symbol: str, interval: str = "5m"):
        self._symbol = symbol.upper()
        self._interval = interval

        t_k = threading.Thread(target=self._run_kline, daemon=True)
        t_k.start()
        t_d = threading.Thread(target=self._run_depth, daemon=True)
        t_d.start()
        t_t = threading.Thread(target=self._run_trade, daemon=True)
        t_t.start()

        t_k.join()  # block until stopped

    def stop(self):
        self._running = False
        for ws in [self._kline_ws, self._depth_ws, self._trade_ws]:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass