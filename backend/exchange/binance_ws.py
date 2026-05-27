import json
import sys
import time
import threading
import websocket


class BinanceWSListener:
    """Multi-stream WebSocket listener: kline (primary) + depth + trades (optional)."""

    def __init__(self, on_candle, on_error=None, reconnect_delay=5, log_fn=None):
        self.on_candle_cb = on_candle
        self.on_error_cb = on_error
        self.reconnect_delay = reconnect_delay
        self._last_close_time = 0
        self._lock = threading.Lock()
        self._log = log_fn  # optional log callback

        # Accumulated trade tape stats for current 5-minute window
        self._trade_buy_vol = 0.0
        self._trade_sell_vol = 0.0
        self._trade_count = 0
        self._trades_sizes = []  # last N trade sizes for large trade detection

        # Latest order book snapshot
        self._order_book = None

        # Threads
        self._kline_ws = None
        self._depth_ws = None
        self._trade_ws = None
        self._threads = []
        self._running = True

    # ==================== Kline stream (PRIMARY) ====================

    def _on_kline_msg(self, ws, msg):
        try:
            data = json.loads(msg)
            k = data.get("k", {})
            if not k.get("x", False):
                return  # candle not closed
            ct = k["T"]
            with self._lock:
                if ct <= self._last_close_time:
                    return
                self._last_close_time = ct
                o = float(k["o"]); h = float(k["h"]); l = float(k["l"])
                c = float(k["c"]); v = float(k["v"])
                order_book = self._build_order_book()
                trade_tape = self._build_trade_tape()
                # Reset accumulators
                self._trade_buy_vol = 0.0
                self._trade_sell_vol = 0.0
                self._trade_count = 0
                self._trades_sizes = []

            self.on_candle_cb(o, h, l, c, v, k["t"] / 1000,
                              order_book=order_book, trade_tape=trade_tape)
        except Exception as e:
            sys.stderr.write(f"[kline] parse error: {e}\n")

    def _on_kline_error(self, ws, error):
        sys.stderr.write(f"[kline] WS error: {error}\n")

    def _on_kline_close(self, ws, *args):
        sys.stdout.write(f"[kline] closed, reconnecting in {self.reconnect_delay}s...\n")
        time.sleep(self.reconnect_delay)
        if self._running:
            self._kline_ws.run_forever()

    def _run_kline(self):
        url = f"wss://fstream.binance.com/ws/{self._symbol.lower()}@kline_{self._interval}"
        self._kline_ws = websocket.WebSocketApp(
            url,
            on_open=lambda ws: self._log and self._log("SYS", f"WS kline connected: {self._symbol}@{self._interval}"),
            on_message=self._on_kline_msg,
            on_error=self._on_kline_error,
            on_close=self._on_kline_close,
        )
        self._log and self._log("SYS", f"WS kline starting: {self._symbol}@{self._interval}")
        self._kline_ws.run_forever()

    # ==================== Depth stream (optional) ====================

    def _on_depth_msg(self, ws, msg):
        try:
            data = json.loads(msg)
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            if not bids or not asks:
                return
            bid_qty = sum(float(b[1]) for b in bids[:5])
            ask_qty = sum(float(a[1]) for a in asks[:5])
            best_bid = float(bids[0][0]) if bids else 0
            best_ask = float(asks[0][0]) if asks else 0
            max_bid_qty = max((float(b[1]) for b in bids[:5]), default=0)
            max_ask_qty = max((float(a[1]) for a in asks[:5]), default=0)
            with self._lock:
                self._order_book = [bid_qty, ask_qty, best_bid, best_ask, max_bid_qty, max_ask_qty]
        except Exception as e:
            pass  # depth updates are frequent, ignore parse errors

    def _on_depth_error(self, ws, error):
        sys.stderr.write(f"[depth] WS error: {error}\n")

    def _on_depth_close(self, ws, *args):
        sys.stdout.write(f"[depth] closed, reconnecting in {self.reconnect_delay}s...\n")
        time.sleep(self.reconnect_delay)
        if self._running:
            self._depth_ws.run_forever()

    def _run_depth(self):
        url = f"wss://fstream.binance.com/ws/{self._symbol.lower()}@depth5@500ms"
        self._depth_ws = websocket.WebSocketApp(
            url,
            on_message=self._on_depth_msg,
            on_error=self._on_depth_error,
            on_close=self._on_depth_close,
        )
        sys.stdout.write(f"WS depth: {self._symbol}@depth5\n")
        self._depth_ws.run_forever()

    # ==================== Trade stream (optional) ====================

    def _on_trade_msg(self, ws, msg):
        try:
            data = json.loads(msg)
            price = float(data.get("p", 0))
            qty = float(data.get("q", 0))
            is_buyer_maker = data.get("m", False)
            vol = price * qty
            with self._lock:
                if is_buyer_maker:
                    self._trade_sell_vol += vol  # taker was seller
                else:
                    self._trade_buy_vol += vol   # taker was buyer
                self._trade_count += 1
                self._trades_sizes.append(qty)
        except Exception as e:
            pass  # trades are frequent, ignore parse errors

    def _on_trade_error(self, ws, error):
        sys.stderr.write(f"[trade] WS error: {error}\n")

    def _on_trade_close(self, ws, *args):
        sys.stdout.write(f"[trade] closed, reconnecting in {self.reconnect_delay}s...\n")
        time.sleep(self.reconnect_delay)
        if self._running:
            self._trade_ws.run_forever()

    def _run_trade(self):
        url = f"wss://fstream.binance.com/ws/{self._symbol.lower()}@aggTrade"
        self._trade_ws = websocket.WebSocketApp(
            url,
            on_message=self._on_trade_msg,
            on_error=self._on_trade_error,
            on_close=self._on_trade_close,
        )
        sys.stdout.write(f"WS trade: {self._symbol}@aggTrade\n")
        self._trade_ws.run_forever()

    # ==================== Helpers ====================

    def _build_order_book(self):
        if self._order_book:
            return self._order_book[:]
        return None

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

    # ==================== Public API ====================

    def connect(self, symbol: str, interval: str = "5m"):
        self._symbol = symbol.upper()
        self._interval = interval

        # Start kline (required)
        t_k = threading.Thread(target=self._run_kline, daemon=True)
        t_k.start()
        self._threads.append(t_k)

        # Start depth (optional, best-effort)
        t_d = threading.Thread(target=self._run_depth, daemon=True)
        t_d.start()
        self._threads.append(t_d)

        # Start trades (optional, best-effort)
        t_t = threading.Thread(target=self._run_trade, daemon=True)
        t_t.start()
        self._threads.append(t_t)

        # Wait forever on kline thread (primary)
        t_k.join()

    def stop(self):
        self._running = False
        for ws in [self._kline_ws, self._depth_ws, self._trade_ws]:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass