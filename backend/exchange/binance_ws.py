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

    def _on_message(self, ws, msg):
        try:
            data = json.loads(msg)
            k = data.get("k", {})
            if k.get("x", False):
                ct = k["T"]
                if ct <= self._last_close_time:
                    return
                self._last_close_time = ct
                o, h, l, c, v = float(k["o"]), float(k["h"]), float(k["l"]), float(k["c"]), float(k["v"])
                self.on_candle_cb(o, h, l, c, v, k["t"] / 1000)
        except Exception as e:
            sys.stderr.write(f"WS on_message: {e}\n")

    def _on_error(self, ws, error):
        sys.stderr.write(f"WS error: {error}\n")
        if self.on_error_cb:
            self.on_error_cb(error)

    def _on_close(self, ws, close_status, close_msg):
        sys.stdout.write(f"WS closed, reconnecting in {self.reconnect_delay}s...\n")
        time.sleep(self.reconnect_delay)
        self.ws.run_forever()

    def _on_open(self, ws):
        sys.stdout.write(f"WS connected: {self.url}\n")

    def connect(self, symbol: str, interval: str = "5m"):
        self.symbol = symbol.upper()
        self.interval = interval
        self.url = f"wss://fstream.binance.com/market/ws/{self.symbol.lower()}@kline_{interval}"
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
