import json
import sys
import time
import websocket


class BinanceWSListener:
    def __init__(self, on_candle, on_error=None, reconnect_delay=5):
        self.on_candle_cb = on_candle
        self.on_error_cb = on_error
        self.reconnect_delay = reconnect_delay
        self.ws = None
        self._last_close_time = 0

        # Accumulated trade tape stats for current 5-minute window
        self._trade_buy_vol = 0.0
        self._trade_sell_vol = 0.0
        self._trade_count = 0
        self._trades = []  # last 50 trade sizes for large trade detection

        # Latest order book snapshot
        self._order_book = None

    def _on_message(self, ws, msg):
        try:
            parsed = json.loads(msg)

            # Handle combined stream format: {"stream": "...", "data": {...}}
            if "stream" in parsed:
                stream = parsed["stream"]
                data = parsed.get("data", parsed)
            else:
                data = parsed
                stream = "kline"  # fallback

            if "depth" in stream:
                self._handle_depth(data)
            elif "aggTrade" in stream:
                self._handle_trade(data)
            else:
                self._handle_kline(data)

        except Exception as e:
            sys.stderr.write(f"WS on_message: {e}\n")

    def _handle_kline(self, data):
        k = data.get("k", data)
        if not k.get("x", False):
            return  # candle not closed yet
        ct = k["T"]
        if ct <= self._last_close_time:
            return
        self._last_close_time = ct
        o = float(k["o"]); h = float(k["h"]); l = float(k["l"])
        c = float(k["c"]); v = float(k["v"])

        # Build order book snapshot
        order_book = self._build_order_book()

        # Build trade tape summary for this window
        trade_tape = self._build_trade_tape()

        # Reset accumulators for next window
        self._trade_buy_vol = 0.0
        self._trade_sell_vol = 0.0
        self._trade_count = 0
        self._trades = []

        self.on_candle_cb(o, h, l, c, v, k["t"] / 1000,
                          order_book=order_book, trade_tape=trade_tape)

    def _handle_depth(self, data):
        """Store latest order book depth 5 snapshot."""
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        if not bids or not asks:
            return
        bid_qty = sum(float(b[1]) for b in bids[:5])
        ask_qty = sum(float(a[1]) for a in asks[:5])
        best_bid = float(bids[0][0]) if bids else 0
        best_ask = float(asks[0][0]) if asks else 0
        max_bid_qty = max((float(b[1]) for b in bids[:5])) if bids else 0
        max_ask_qty = max((float(a[1]) for a in asks[:5])) if asks else 0
        self._order_book = [bid_qty, ask_qty, best_bid, best_ask, max_bid_qty, max_ask_qty]

    def _handle_trade(self, data):
        """Accumulate trade stats for current 5-minute window."""
        price = float(data.get("p", 0))
        qty = float(data.get("q", 0))
        is_buyer_maker = data.get("m", False)
        vol = price * qty

        # m=True: buyer was maker (limit), so taker was seller = aggressive SELL
        if is_buyer_maker:
            self._trade_sell_vol += vol
        else:
            self._trade_buy_vol += vol

        self._trade_count += 1
        self._trades.append(qty)

    def _build_order_book(self):
        if self._order_book:
            return self._order_book[:]
        return None

    def _build_trade_tape(self):
        """Build trade tape summary for the 5-minute window."""
        if self._trade_count == 0:
            return None
        total_vol = self._trade_buy_vol + self._trade_sell_vol
        if total_vol == 0:
            return None
        # Large trade ratio: fraction of trades > 2x median size
        if len(self._trades) > 1:
            self._trades.sort()
            median = self._trades[len(self._trades) // 2]
            large_count = sum(1 for q in self._trades if q > 2 * median)
            large_ratio = large_count / len(self._trades)
        else:
            large_ratio = 0.0
        return [self._trade_buy_vol, self._trade_sell_vol,
                float(self._trade_count), large_ratio]

    def _on_error(self, ws, error):
        sys.stderr.write(f"WS error: {error}\n")
        if self.on_error_cb:
            self.on_error_cb(error)

    def _on_close(self, ws, close_status, close_msg):
        sys.stdout.write(f"WS closed, reconnecting in {self.reconnect_delay}s...\n")
        time.sleep(self.reconnect_delay)
        self.ws.run_forever()

    def _on_open(self, ws):
        sys.stdout.write(f"WS connected: {self.symbol} (kline+depth+trade)\n")

    def connect(self, symbol: str, interval: str = "5m"):
        self.symbol = symbol.upper()
        self.interval = interval
        sym = self.symbol.lower()
        # Combined stream: kline + order book + trades
        self.url = (
            f"wss://fstream.binance.com/stream?streams="
            f"{sym}@kline_{interval}/{sym}@depth5@500ms/{sym}@aggTrade"
        )
        self.ws = websocket.WebSocketApp(
            self.url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws.run_forever()

    def stop(self):
        if self.ws:
            self.ws.close()