import math
import sys
import time

from exchange.binance_rest import BinanceFuturesAPI
from .base import BaseTrader


class RealTrader(BaseTrader):
    def __init__(self, api_key, api_secret, symbol="SOLUSDT", leverage=1,
                 config_file=None, lr=0.01, tau=24.0, sl=0.05, tp=0.12,
                 db=None, telegram_queue=None):
        self.binance = BinanceFuturesAPI(api_key, api_secret)
        self.db = db
        self.telegram_queue = telegram_queue
        self.user_id = None
        super().__init__(symbol, leverage, config_file, lr, tau, sl, tp)

    def _init_exchange(self):
        """Sync leverage and check balance on startup."""
        try:
            self.binance.set_leverage(self.symbol, self.leverage)
            bal = self.binance.get_balance()
            self.equity = float(bal) if bal else self.equity
            print(f"[Real] Balance: ${self.equity:.2f} | Leverage: {self.leverage}x")
            self._log("SYS", f"Balance: ${self.equity:.2f}, leverage: {self.leverage}x")
        except Exception as e:
            print(f"[Real] Init error: {e}")
            self._log("ERROR", f"Init: {e}")

    def _get_qty(self, price: float) -> float:
        """Calculate position size — 10% of equity at current price."""
        risk_amount = self.equity * 0.1 * self.leverage
        raw_qty = risk_amount / max(price, 1e-8)
        info = self.binance.get_exchange_info()
        for s in info.get("symbols", []):
            if s["symbol"] == self.symbol:
                for f in s.get("filters", []):
                    if f["filterType"] == "LOT_SIZE":
                        step = float(f["stepSize"])
                        qty = math.floor(raw_qty / step) * step
                        return max(qty, float(f["minQty"]))
        return max(round(raw_qty, 4), 0.001)

    def on_entry(self, side, price, ts_str):
        super().on_entry(side, price, ts_str)
        try:
            qty = self._get_qty(price)
            if qty <= 0:
                self._log("ERROR", "Invalid quantity for entry")
                return
            order = self.binance.market_order(self.symbol, side, qty)
            self._log("EXEC", f"{side} {qty} {self.symbol} @ MARKET — filled qty: {order.get('executedQty', '?')}")
            if self.telegram_queue:
                self.telegram_queue.put(f"[REAL] {side} {qty} {self.symbol}")
        except Exception as e:
            self._log("ERROR", f"Order failed: {e}")
            self.pos = 0  # revert paper position

    def on_exit(self, side, price, pnl_pct, reason, ts_str):
        super().on_exit(side, price, pnl_pct, reason, ts_str)
        try:
            close_side = "SELL" if side == "BUY" else "BUY"
            pos = self.binance.get_position(self.symbol)
            qty = abs(float(pos.get("positionAmt", 0)))
            if qty > 0:
                self.binance.market_order(self.symbol, close_side, qty, reduce_only=True)
                self._log("EXEC", f"CLOSE {self.symbol} {qty} — {reason}")
            if self.db and self.user_id:
                self.db.write_trade(
                    user_id=self.user_id,
                    symbol=self.symbol,
                    side=side,
                    entry_price=self.entry_price,
                    exit_price=price,
                    quantity=qty,
                    leverage=self.leverage,
                    pnl=pnl_pct * self.equity / (1 + pnl_pct),
                    pnl_pct=pnl_pct,
                    close_reason=reason,
                )
            if self.telegram_queue:
                self.telegram_queue.put(f"[REAL] CLOSE {self.symbol} PnL={pnl_pct*100:.2f}%")
        except Exception as e:
            self._log("ERROR", f"Close failed: {e}")

    def _log(self, level, message):
        print(f"[{level}] {message}")
        if self.db and self.user_id:
            self.db.write_log(self.user_id, level.lower(), message)

    def set_user(self, user_id: str):
        self.user_id = user_id

    def sync_db_every_candle(self):
        """Call this after each candle to write equity to Supabase."""
        if self.db and self.user_id:
            self.db.write_equity(self.user_id, self.equity, self.equity, self.symbol)
