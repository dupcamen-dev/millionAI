import json
import sys
import time
import threading
import websocket


class BinanceWSListener:
    """Multi-stream WebSocket listener: kline (primary) + depth + trades."""

    def __init__(self, on_candle, on_error=None, reconnect_delay=5, log_fn=None):
        self.on_candle_cb = on_candle
        self.on_error_cb = on_error
        self.reconnect_delay = reconnect_delay
        self._last_close_time = 0
        self._last_open_log_ts = 0
        self._lock = threading.Lock()
        self._log = log_fn

        self._trade_buy_vol = 0.0
        self._trade_sell_vol = 0.0
        self._trade_count = 0
        self._trades_sizes = []

        self._depth_received = False
        self._first_trade_logged = False
        self._order_book = None
        self._msg_count = 0  # debug: count received messages

        self._kline_ws = None
        self._depth_ws = None
        self._trade_ws = None
        self._running = True

    def _slog(self, msg):
        self._log and self._log("SYS", msg)

    # ── Generic message handler (single arg) ────────────────
    def _on_msg(self, raw):
        """Handle any WebSocket message — dispatch by type."""
        self._msg_count += 1
        try:
            data = json.loads(raw)
        except Exception:
            return

        e_type = data.get("e", "")
        if e_type == "kline":
            self._handle_kline(data)
        elif e_type == "depthUpdate":
            self._handle_depth(data)
        elif e_type == "aggTrade":
            self._handle_trade(data)

        # Debug: log first 3 raw messages
        if self._msg_count <= 3:
            preview = str(data)[:300]
            self._slog(f"WS msg#{self._msg_count}: {preview}")

    def _on_err(self, error):
        if isinstance(error, Exception):
            err_str = str(error)[:200]
        else:
            err_str = str(error)[:200]
        sys.stderr.write(f"WS error: {err_str}\n")
        self._slog(f"WS ERROR: {err_str}")

    def _on_close(self, *args):
        self._slog("WS connection closed")

    def _on_open(self):
        self._slog(f"WS connected: {self._symbol}")

    # ── Kline handler ──────────────────────────────
    def _handle_kline(self, data):
        k = data.get("k", {})
        if not k.get("x", False):
            now = time.time()
            if now - self._last_open_log_ts > 300:
                self._last_open_log_ts = now
                self._slog(f"Kline alive: ${k.get('c','?')} (waiting)")
            return
        ct = k["T"]
        with self._lock:
            if ct <= self._last_close_time:
                return
            self._last_close_time = ct
            o = float(k["o"]); h = float(k["h"]); l = float(k["l"])
            c = float(k["c"]); v = float(k["v"])
            order_book = self._build_order_book()
            trade_tape = self._build_trade_tape()
            self._trade_buy_vol = 0.0
            self._trade_sell_vol = 0.0
            self._trade_count = 0
            self._trades_sizes = []

        self.on_candle_cb(o, h, l, c, v, k["t"] / 1000,
                          order_book=order_book, trade_tape=trade_tape)

    # ── Depth handler ──────────────────────────────
    def _handle_depth(self, data):
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        if not bids or not asks:
            return
        if not self._depth_received:
            self._depth_received = True
            self._slog(f"Depth: bid={bids[0][0]} ask={asks[0][0]}")
        bid_qty = sum(float(b[1]) for b in bids[:5])
        ask_qty = sum(float(a[1]) for a in asks[:5])
        best_bid = float(bids[0][0]) if bids else 0
        best_ask = float(asks[0][0]) if asks else 0
        max_bid_qty = max((float(b[1]) for b in bids[:5]), default=0)
        max_ask_qty = max((float(a[1]) for a in asks[:5]), default=0)
        with self._lock:
            self._order_book = [bid_qty, ask_qty, best_bid, best_ask, max_bid_qty, max_ask_qty]

    # ── Trade handler ──────────────────────────────
    def _handle_trade(self, data):
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

    # ── Helpers ─────────────────────────────────────
    def _build_order_book(self):
        return self._order_book[:] if self._order_book else None

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

    # ── Connection (single WebSocket, combined stream) ──
    def _run_ws(self):
        # One connection, all 3 streams
        sym = self._symbol.lower()
        self._url = (
            f"wss://fstream.binance.com/stream?"
            f"streams={sym}@kline_{self._interval}/{sym}@depth5@500ms/{sym}@aggTrade"
        )
        self._slog(f"WS connecting: {self._url[:80]}...")
        self._ws = websocket.WebSocketApp(
            self._url,
            on_open=lambda *_: self._on_open(),
            on_message=lambda _, msg: self._on_msg(msg),
            on_error=lambda _, err: self._on_err(err),
            on_close=lambda _, *args: self._on_close(),
        )
        self._ws.run_forever()

    def connect(self, symbol: str, interval: str = "5m"):
        self._symbol = symbol.upper()
        self._interval = interval
        self._ws = None
        self._url = f"wss://fstream.binance.com/ws/{symbol.lower()}@kline_{interval}"
        self._slog(f"WS connecting: {self._url[:80]}...")
        self._ws = websocket.WebSocketApp(
            self._url,
            on_open=lambda *_: self._on_open(),
            on_message=lambda _, msg: self._on_msg(msg),
            on_error=lambda _, err: self._on_err(err),
            on_close=lambda _, *args: self._on_close(),
        )
        self._ws.run_forever()

    def stop(self):
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass