import math
import sys
import time

from exchange.binance_rest import BinanceFuturesAPI, BinanceAPIError, INSUFFICIENT_BALANCE, INSUFFICIENT_MARGIN, INVALID_API_KEY, RATE_LIMIT
from exchange.screener import AssetScreener
from .base import BaseTrader

ERR_MESSAGES = {
    INSUFFICIENT_BALANCE: "Insufficient balance. Deposit USDT to your Futures wallet.",
    INSUFFICIENT_MARGIN: "Insufficient margin. Reduce position size or add margin.",
    INVALID_API_KEY: "Invalid API key. Check key permissions (Futures enabled).",
    RATE_LIMIT: "Rate limit hit. Waiting before next request.",
}

def select_leverage(volatility_pct: float) -> int:
    if volatility_pct < 0.5:
        return 10
    elif volatility_pct < 1.0:
        return 5
    elif volatility_pct < 2.0:
        return 3
    elif volatility_pct < 4.0:
        return 2
    else:
        return 1

class RealTrader(BaseTrader):
    def __init__(self, api_key, api_secret, symbol="SOLUSDT", leverage=1,
                 config_file=None, lr=0.01, tau=24.0, sl=0.05, tp=0.12,
                 db=None, telegram_queue=None, auto_symbol=False):
        self.binance = BinanceFuturesAPI(api_key, api_secret)
        self.db = db
        self.telegram_queue = telegram_queue
        self.user_id = None
        self._lot_step = None
        self._lot_min_qty = None
        self.auto_symbol = auto_symbol
        self.screener = AssetScreener(self.binance) if auto_symbol else None
        super().__init__(symbol, leverage, config_file, lr, tau, sl, tp)

    def _load_lot_size(self):
        if self._lot_step is not None:
            return
        try:
            info = self.binance.get_exchange_info()
            for s in info.get("symbols", []):
                if s["symbol"] == self.symbol:
                    for f in s.get("filters", []):
                        if f["filterType"] == "LOT_SIZE":
                            self._lot_step = float(f["stepSize"])
                            self._lot_min_qty = float(f["minQty"])
                            return
                    for f in s.get("filters", []):
                        if f["filterType"] == "MIN_NOTIONAL":
                            self._min_notional = float(f.get("notional", 5))
                            return
            self._lot_step = 0.001
            self._lot_min_qty = 0.001
        except Exception as e:
            self._log("ERROR", f"Failed to load LOT_SIZE: {e}")
            self._lot_step = 0.001
            self._lot_min_qty = 0.001
        self._min_notional = 5.0

    def _init_exchange(self):
        try:
            self._load_lot_size()
            if self.auto_symbol:
                self._auto_select_symbol()
            else:
                self.binance.set_leverage(self.symbol, self.leverage)
            bal = self.binance.get_balance()
            self.equity = float(bal) if bal else self.equity
            self._log("SYS", f"Balance: ${self.equity:.2f} | Leverage: {self.leverage}x | Symbol: {self.symbol}")
            print(f"[Real] Connected. Balance: ${self.equity:.2f} | {self.symbol} {self.leverage}x")
        except BinanceAPIError as e:
            if e.code == INVALID_API_KEY:
                self._log("CRITICAL", f"API key rejected: {e.message}")
            else:
                self._log("ERROR", f"Init: [{e.code}] {e.message}")
            sys.exit(1)
        except Exception as e:
            self._log("ERROR", f"Init error: {e}")
            sys.exit(1)

    def _auto_select_symbol(self):
        """Run screener, pick best symbol, set leverage."""
        try:
            candidates = self.screener.scan(top_n=1)
            if not candidates:
                self._log("ERROR", "Screener found no candidates, using default symbol")
                self.binance.set_leverage(self.symbol, self.leverage)
                return
            best = candidates[0]
            self.symbol = best["symbol"]
            self.leverage = select_leverage(best["volatility"])
            self.binance.set_leverage(self.symbol, self.leverage)
            self._log("SYS", f"Screener: {self.symbol} (vol={best['volatility']:.2f}%, score={best['score']:.4f}) -> {self.leverage}x")
            print(f"[Screener] Selected {self.symbol} @ ${best['price']:.4f} vol={best['volatility']:.2f}% -> {self.leverage}x")
            # Re-load LOT_SIZE for new symbol
            self._lot_step = None
            self._lot_min_qty = None
            self._load_lot_size()
        except Exception as e:
            self._log("ERROR", f"Screener failed: {e}")
            self.binance.set_leverage(self.symbol, self.leverage)

    def _get_qty(self, price: float) -> float:
        self._load_lot_size()
        min_notional = getattr(self, '_min_notional', 5.0)
        step = self._lot_step or 0.001
        min_qty = self._lot_min_qty or 0.001

        raw_qty = self.equity * 0.1 * self.leverage / max(price, 1e-8)
        qty = math.floor(raw_qty / step) * step
        qty = max(qty, min_qty)

        # Enforce minimum notional (5 USDT for non-reduce-only orders)
        notional = qty * price
        if notional < min_notional:
            qty = math.ceil(min_notional / price / step) * step
            qty = max(qty, min_qty)
            self._log("SYS", f"Raised qty to {qty} for min notional ${min_notional}")

        return qty

    def on_entry(self, side, price, ts_str):
        super().on_entry(side, price, ts_str)
        try:
            bal = self.binance.get_balance()
            self.equity = float(bal) if bal else self.equity
            qty = self._get_qty(price)
            if qty <= 0:
                self._log("ERROR", "Invalid quantity for entry")
                self.pos = 0
                return

            needed = qty * price / self.leverage
            if needed > self.equity:
                self._log("BALANCE", f"Insufficient: need ${needed:.2f}, have ${self.equity:.2f}")
                self.pos = 0
                return

            order = self.binance.market_order(self.symbol, side, qty)
            filled_qty = order.get("executedQty", "0")
            fill_price = order.get("avgPrice", str(price))
            self.entry_price = float(fill_price) if fill_price != str(price) else price
            self._log("EXEC", f"{side} {qty} {self.symbol} @ ${self.entry_price:.4f} filled: {filled_qty}")
            self._tg(f"[REAL] {side} {qty} {self.symbol} @ ${self.entry_price:.4f}")
        except BinanceAPIError as e:
            msg = ERR_MESSAGES.get(e.code, f"Order error [{e.code}]: {e.message}")
            self._log("ERROR", msg)
            if e.code in (INSUFFICIENT_BALANCE, INSUFFICIENT_MARGIN):
                self._log("BALANCE", f"Balance: ${self.equity:.2f}")
            self.pos = 0
            if e.code == RATE_LIMIT:
                time.sleep(5)
            # Try to re-select symbol if -2015 (key issue) or other perm errors
            if self.auto_symbol and e.code in (-2015, -2010):
                self._auto_select_symbol()
        except Exception as e:
            self._log("ERROR", f"Entry failed: {e}")
            self.pos = 0

    def on_exit(self, side, price, pnl_pct, reason, ts_str):
        super().on_exit(side, price, pnl_pct, reason, ts_str)
        try:
            close_side = "SELL" if side == "BUY" else "BUY"
            pos = self.binance.get_position(self.symbol)
            qty = abs(float(pos.get("positionAmt", 0)))
            if qty <= 0:
                self._log("WARN", f"No position to close for {self.symbol}")
                return

            order = self.binance.market_order(self.symbol, close_side, qty, reduce_only=True)
            fill_price = float(order.get("avgPrice", str(price)))
            self._log("EXEC", f"CLOSE {qty} {self.symbol} @ ${fill_price:.4f} — {reason}")

            if self.db and self.user_id:
                pnl_usd = pnl_pct * self.equity / max(1 + pnl_pct, 1e-8)
                self.db.write_trade(
                    user_id=self.user_id, symbol=self.symbol, side=side,
                    entry_price=self.entry_price, exit_price=fill_price,
                    quantity=qty, leverage=self.leverage,
                    pnl=pnl_usd, pnl_pct=pnl_pct, close_reason=reason,
                )
                self.db.write_equity(self.user_id, self.equity, self.equity, self.symbol)
            self._tg(f"[REAL] CLOSE {self.symbol} {reason} PnL={pnl_pct*100:.2f}%")

            # Auto-switch symbol after trade close
            if self.auto_symbol:
                self._log("SYS", "Re-running screener for next trade...")
                self._auto_select_symbol()
        except BinanceAPIError as e:
            msg = ERR_MESSAGES.get(e.code, f"Close error [{e.code}]: {e.message}")
            self._log("ERROR", msg)
            if e.code == RATE_LIMIT:
                time.sleep(5)
        except Exception as e:
            self._log("ERROR", f"Close failed: {e}")

    def _log(self, level, message):
        line = f"[{level}] {message}"
        print(line)
        if level == "ERROR" or level == "BALANCE" or level == "CRITICAL":
            sys.stderr.write(line + "\n")
        if self.db and self.user_id:
            self.db.write_log(self.user_id, level.lower(), message)

    def _tg(self, text):
        if self.telegram_queue:
            self.telegram_queue.put(text)

    def set_user(self, user_id: str):
        self.user_id = user_id

    def sync_db_every_candle(self):
        if self.db and self.user_id:
            self.db.write_equity(self.user_id, self.equity, self.equity, self.symbol)
