from .base import BaseTrader, _NATIVE_SNN

class PaperTrader(BaseTrader):
    """Paper trader — no real orders, only internal equity tracking.
       Fully matches RealTrader decision logic (v1/v2/EvoBrain)."""

    def __init__(self, symbol="SOLUSDT", leverage=1, config_file=None,
                 lr=0.01, tau=96.0, sl=0.05, tp=0.12):
        super().__init__(symbol, leverage, config_file, lr, tau, sl, tp)

        # Paper-specific
        self.volatility_pct = 20.0  # default for vol_threshold
        self.db = None
        self.user_id = None

        # Try C SNN backend if available
        if _NATIVE_SNN is not None and self.neurons:
            weights = [n.nucleus.tolist() for n in self.neurons]
            self._c_snn = _NATIVE_SNN(init_weights=weights, lr=lr, tau=tau)
            print("[Paper] C SNN backend initialized")

    def on_entry(self, side, price, ts_str):
        """Simulated entry — no Binance order, just logging."""
        if self._use_c_backend():
            raw_buy, raw_sell, _ = self._c_snn.forward_raw(
                self.vol_history[-1:] if self.vol_history else [0]*14
            )
        qty = self._get_qty(price) if hasattr(self, '_get_qty') else 0
        print(f"{ts_str} [PAPER] {side} {qty:.0f} {self.symbol} @ ${price:.6f} ({self.leverage}x)")

    def on_exit(self, side, price, pnl_pct, reason, ts_str):
        """Simulated exit — just logging, equity already updated in base."""
        print(f"{ts_str} [PAPER] {reason} @ ${price:.6f} PnL={pnl_pct*100:.2f}% Eq=${self.equity:.4f}")

    def _get_qty(self, price):
        """Simple position sizing for paper trading (no Binance lot size checks)."""
        qty = self.equity * self.leverage * 0.95 / max(price, 1e-8)
        qty *= getattr(self, '_risk_scale', 1.0)
        # Keep at least 5 USDT notional
        if qty * price < 5.0:
            qty = 5.0 / price
        return qty