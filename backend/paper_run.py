"""Paper trading — runs 1500 candles through PaperTrader locally."""
import sys, os, time, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from exchange.binance_rest import BinanceFuturesAPI
from exchange.screener import AssetScreener
from trader.paper import PaperTrader
from snn.cwrapper import quick_backtest

api = BinanceFuturesAPI(os.getenv('API_KEY'), os.getenv('API_SECRET'))

print("=== PAPER TRADER LOCAL ===")
print()

# Screener
print("Scanning assets...")
scr = AssetScreener(api)
candidates = scr.scan(top_n=5)
for c in candidates[:5]:
    print("  %s @ $%.4f vol=%.1f%% score=%.2f" % (c['symbol'], c['price'], c['volatility'], c['score']))

# Quick backtest on top 3 to pick the best
best_symbol = None
best_risk = -999
for c in candidates[:3]:
    klines = api.get_klines(c['symbol'], '5m', 500)
    data = np.zeros((len(klines), 5), dtype=np.float32)
    for i, k in enumerate(klines):
        data[i] = [float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])]
    r = quick_backtest(data, leverage=1)
    print("  %s: %dt WR=%.0f%% PnL=%.1f%% risk=%.2f" % (c['symbol'], r['trades'], r['winrate']*100, r['total_pnl']*100, r['risk_score']))
    if r['risk_score'] > best_risk:
        best_risk = r['risk_score']
        best_symbol = c

print()
print("Selected: %s (risk=%.2f)" % (best_symbol['symbol'], best_risk))
print()

# Download full history for the selected symbol
print("Fetching 1500 candles for %s..." % best_symbol['symbol'])
klines = api.get_klines(best_symbol['symbol'], '5m', 1500)
candles = np.zeros((len(klines), 5), dtype=np.float32)
for i, k in enumerate(klines):
    candles[i] = [float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])]

print("Got %d candles. Starting paper trader..." % len(candles))
print()

# Create paper trader
trader = PaperTrader(
    symbol=best_symbol['symbol'],
    leverage=1,
    lr=0.01, tau=96.0, sl=0.05, tp=0.12,
)
trader.volatility_pct = best_symbol['volatility']
trader._base_threshold = 0.40

# Adaptive SL/TP
vol = best_symbol['volatility'] / 100.0
trader.sl = max(0.05, vol * 0.3)
trader.tp = max(0.12, vol * 0.8)
print("Adaptive SL/TP: %.1f%% / %.1f%%" % (trader.sl*100, trader.tp*100))

# Feed candles
for c_idx in range(len(candles)):
    o, h, l, cl, v = candles[c_idx]
    ts = time.time()  # approximate timestamp
    action = trader.on_candle(o, h, l, cl, v, ts)
    if c_idx % 100 == 0:
        print("  Candle #%d/%d | Eq=$%.4f | Trades:%d | %.1f%% done" % (
            c_idx, len(candles), trader.equity, trader.trades, 100.0*c_idx/len(candles)))

# Summary
trader.summary()
print()
print("base_th: %.3f, no_trade_streak: %d" % (trader._base_threshold, trader._no_trade_streak))
print("DONE")
