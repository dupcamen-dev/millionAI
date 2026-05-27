import math
import sys
import time

import numpy as np

from exchange.binance_rest import BinanceFuturesAPI, BinanceAPIError, INSUFFICIENT_BALANCE, INSUFFICIENT_MARGIN, INVALID_API_KEY, RATE_LIMIT
from exchange.screener import AssetScreener
from .base import BaseTrader

# Try C backtest from compiled library first, fall back to Python
try:
    from snn.cwrapper import quick_backtest as _c_quick_backtest
except (ImportError, FileNotFoundError, OSError):
    _c_quick_backtest = None

try:
    from trader.backtest import quick_backtest as _py_quick_backtest
except ImportError:
    _py_quick_backtest = None

def quick_backtest(data, **kwargs):
    if _c_quick_backtest is not None:
        return _c_quick_backtest(data, **kwargs)
    if _py_quick_backtest is not None:
        return _py_quick_backtest(data, **kwargs)
    raise RuntimeError("No backtest engine available")

ERR_MESSAGES = {
    INSUFFICIENT_BALANCE: "Insufficient balance. Deposit USDT to your Futures wallet.",
    INSUFFICIENT_MARGIN: "Insufficient margin. Reduce position size or add margin.",
    INVALID_API_KEY: "Invalid API key. Check key permissions (Futures enabled).",
    RATE_LIMIT: "Rate limit hit. Waiting before next request.",
}

def select_leverage(volatility_pct: float) -> int:
    return 1

class RealTrader(BaseTrader):
    def __init__(self, api_key, api_secret, symbol="SOLUSDT", leverage=1,
                 config_file=None, lr=0.01, tau=96.0, sl=0.05, tp=0.12,
                 db=None, telegram_queue=None, auto_symbol=False):
        self.binance = BinanceFuturesAPI(api_key, api_secret)
        self.db = db
        self.telegram_queue = telegram_queue
        self.user_id = None
        self._lot_step = None
        self._lot_min_qty = None
        self.auto_symbol = auto_symbol
        self.screener = AssetScreener(self.binance) if auto_symbol else None
        self.last_screener_candidates = []
        self.last_backtest_risk_score = 0.0
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
                        if f["filterType"] == "MIN_NOTIONAL":
                            self._min_notional = float(f.get("notional", 5))
                    self._log("SYS", f"Lot: step={self._lot_step} min_qty={self._lot_min_qty} min_notional={self._min_notional}")
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
            self._log("SYS", "Loading lot size...")
            self._load_lot_size()
            if self.auto_symbol:
                self._log("SYS", "Auto-selecting symbol via screener+backtest...")
                self._auto_select_symbol()
            else:
                self.binance.set_leverage(self.symbol, self.leverage)
            bal = self.binance.get_balance()
            self.equity = float(bal) if bal else 0.0
            self._log("SYS", f"Balance: ${self.equity:.2f} | Leverage: {self.leverage}x | Symbol: {self.symbol}")
            print(f"[Real] Connected. Balance: ${self.equity:.2f} | {self.symbol} {self.leverage}x")
        except BinanceAPIError as e:
            msg = ERR_MESSAGES.get(e.code, f"Init: [{e.code}] {e.message}")
            self._log("ERROR", msg)
            raise
        except Exception as e:
            self._log("ERROR", f"Init error: {e}")
            raise

    def _auto_select_symbol(self, top_n=5, backtest_top=3):
        """Run screener -> backtest top candidates -> pick best by risk_score."""
        if getattr(self, '_selecting', False):
            return
        self._selecting = True
        try:
            self._log("SYS", "Scanning assets...")
            candidates = self.screener.scan(top_n=top_n)
            self.last_screener_candidates = candidates or []
            if not candidates:
                self._log("ERROR", "Screener found no candidates, using default symbol")
                self.binance.set_leverage(self.symbol, self.leverage)
                return

            for c in candidates:
                self._log("SYS", f"  {c['symbol']} @ ${c['price']:.4f} vol={c['volatility']:.2f}% score={c['score']:.2f}")

            best_asset = None
            best_risk = -999
            best_result = None
            warm_weights = {}
            warm_states = {}

            if self.db and self.user_id:
                for c in candidates[:backtest_top]:
                    try:
                        state = self.db.load_model_state(self.user_id, c["symbol"])
                        if state and state.get("weights"):
                            warm_weights[c["symbol"]] = state
                            warm_states[c["symbol"]] = state
                            self._log("SYS", f"  Found saved state for {c['symbol']} (risk={state.get('risk_score', 0):.2f}, trades={state.get('rstpd', {}).get('trades', 0)})")
                    except Exception:
                        pass
            backtest_list = candidates[:backtest_top]
            total = len(backtest_list)

            for idx, a in enumerate(backtest_list, 1):
                self._log("SYS", f"Backtest {idx}/{total}: {a['symbol']}...")
                t0 = time.time()
                try:
                    self._log("SYS", f"  Fetching klines for {a['symbol']}...")
                    raw = self.binance.get_klines(a["symbol"], "5m", 1500)
                    self._log("SYS", f"  Got {len(raw) if raw else 0} candles in {time.time()-t0:.1f}s")
                except Exception as e:
                    self._log("WARN", f"  skip — kline fetch failed: {e}")
                    time.sleep(1)
                    continue
                if not raw or len(raw) < 400:
                    self._log("WARN", f"  skip — insufficient data ({len(raw) if raw else 0} candles)")
                    continue
                self._log("SYS", f"  Building data array...")
                data = np.zeros((len(raw), 5), dtype=np.float32)
                for i, k in enumerate(raw):
                    data[i] = [float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])]
                self._log("SYS", f"  Running backtest on {len(data)} candles...")
                t1 = time.time()
                init_weights = warm_weights.get(a["symbol"], {}).get("weights")
                if init_weights:
                    self._log("SYS", f"  Warm-starting with saved weights")
                vol = a["volatility"] / 100.0
                eff_sl = max(0.05, vol * 0.3)
                eff_tp = max(0.12, vol * 0.8)
                r = quick_backtest(data, init_weights=init_weights, leverage=1, sl=eff_sl, tp=eff_tp)
                self._log("SYS", f"  Backtest took {time.time()-t1:.1f}s")
                risk = r["risk_score"]
                self._log("SYS", f"  {r['trades']}t WR:{r['winrate']*100:.0f}% PnL:{r['total_pnl']*100:.1f}% risk:{risk:.2f}")
                if risk > best_risk:
                    best_risk = risk
                    best_asset = a
                    best_result = r

            if best_asset is None:
                self._log("WARN", "No backtest passed, using top screener pick (fallback)")
                best_asset = candidates[0]
                best_result = None

            self.symbol = best_asset["symbol"]

            # Reload lot size for the new symbol (invalidate cache)
            self._lot_step = None
            self._lot_min_qty = None
            self._load_lot_size()

            # Adaptive SL/TP from screener volatility
            vol = best_asset["volatility"] / 100.0
            self.sl = max(0.05, vol * 0.3)
            self.tp = max(0.12, vol * 0.8)
            self.volatility_pct = best_asset["volatility"]
            self._log("SYS", f"Adaptive SL/TP: {self.sl*100:.1f}% / {self.tp*100:.1f}% (vol={best_asset['volatility']:.1f}%)")

            if best_result and best_result["trades"] > 0:
                risk = best_result["risk_score"]
                self.last_backtest_risk_score = risk
                self.leverage = 1
                self.binance.set_leverage(self.symbol, self.leverage)
                if best_result.get("weights"):
                    from snn.neuron import TradingNeuron
                    self.neurons = [TradingNeuron(nucleus=np.array(w, dtype=np.float32)) for w in best_result["weights"]]
                    self._log("SYS", f"Loaded trained weights from backtest ({len(self.neurons)} neurons)")
                    if self.db and self.user_id:
                        try:
                            state = self._c_snn.save_state() if self._use_c_backend() else None
                            if state is None:
                                weights_list = [n.nucleus.tolist() for n in self.neurons]
                                state = {"weights": weights_list, "leverage": self.leverage,
                                          "risk_score": risk, "eligibility": [], "membrane": [],
                                          "rstpd": {}}
                            else:
                                state["leverage"] = self.leverage
                                state["risk_score"] = risk
                            self.db.save_model_state(self.user_id, self.symbol, state)
                            self._log("SYS", f"Saved full model state for {self.symbol} to DB")
                        except Exception as ex:
                            self._log("WARN", f"Failed to save state: {ex}")
                self._log("SYS", f"Selected: {self.symbol} {self.leverage}x (risk={risk:.2f} | {best_result['trades']}t)")
                # Init compiled C SNN with backtest weights + saved eligibility state
                saved_state = warm_states.get(self.symbol)
                if self.init_c_snn(loaded_state=saved_state):
                    self._log("SYS", "C SNN backend initialized (compiled from Million)")
            else:
                self.leverage = 1
                self.binance.set_leverage(self.symbol, self.leverage)
                self._log("SYS", f"Selected: {self.symbol} {self.leverage}x (fallback)")

            print(f"[Screener] Selected {self.symbol} @ ${best_asset['price']:.4f} -> {self.leverage}x")
        except Exception as e:
            self._log("ERROR", f"Auto-select failed: {e}")
            self.binance.set_leverage(self.symbol, self.leverage)
        finally:
            self._selecting = False

    def _get_qty(self, price: float) -> float:
        self._load_lot_size()
        min_notional = getattr(self, '_min_notional', 5.0)
        step = self._lot_step or 0.001
        min_qty = self._lot_min_qty or 0.001

        raw_qty = self.equity * self.leverage * 0.95 / max(price, 1e-8)
        qty = math.floor(raw_qty / step) * step
        qty = max(qty, min_qty)

        # Enforce minimum notional (5 USDT for non-reduce-only orders)
        notional = qty * price
        if notional < min_notional:
            qty = math.ceil(min_notional / price / step) * step
            qty = max(qty, min_qty)
            self._log("SYS", f"Raised qty to {qty} for min notional ${min_notional}")

        # v1: risk scaling from volatility
        qty *= getattr(self, '_risk_scale', 1.0)
        qty = max(qty, min_qty)
        qty = math.floor(qty / step) * step
        return max(qty, min_qty)

    def on_entry(self, side, price, ts_str):
        super().on_entry(side, price, ts_str)
        if self.equity <= 0:
            self._log("BALANCE", f"Cannot trade: wallet is $0.00")
            self.pos = 0
            return
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

            self._log("EXEC", f"ORDER: {side} {qty} {self.symbol} notional=${qty*price:.2f} margin=${needed:.2f} balance=${self.equity:.2f}")
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
                self.db.write_equity(self.user_id, self.equity, self.equity)
            self._tg(f"[REAL] CLOSE {self.symbol} {reason} PnL={pnl_pct*100:.2f}%")
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

    def _log_state(self, ts_str, buy, sell, th, equity, eps):
        msg = f"Eq=${equity:.4f} buy={buy:.3f} sell={sell:.3f} th={th:.3f} eps={eps:.3f}"
        print(f"{ts_str} {msg}")
        self._log("SYS", msg)

    def _tg(self, text):
        if self.telegram_queue:
            self.telegram_queue.put(text)

    def set_user(self, user_id: str):
        self.user_id = user_id

    def sync_db_every_candle(self):
        if self.db and self.user_id:
            self.db.write_equity(self.user_id, self.equity, self.equity)
