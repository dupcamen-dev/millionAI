import math
import numpy as np
from .binance_rest import BinanceFuturesAPI


class AssetScreener:
    def __init__(self, api: BinanceFuturesAPI):
        self.api = api

    def scan(self, top_n=5, min_volume=100_000_000):
        import time
        t0 = time.time()
        tickers = self.api.get_ticker()
        if not isinstance(tickers, list):
            return []
        print(f"[Screener] Got {len(tickers)} tickers in {time.time()-t0:.1f}s")

        candidates = []
        for t in tickers:
            symbol = t.get("symbol", "")
            if not symbol.endswith("USDT"):
                continue
            price = float(t.get("lastPrice", 0) or 0)
            vol_usdt = float(t.get("quoteVolume", 0) or 0)
            price_change = abs(float(t.get("priceChangePercent", 0) or 0))
            high = float(t.get("highPrice", 0) or 0)
            low = float(t.get("lowPrice", 0) or 0)
            if price <= 0 or price >= 1000 or vol_usdt < min_volume:
                continue
            if high <= 0 or low <= 0:
                continue
            volatility_pct = price_change
            range_pct = (high - low) / low * 100 if low > 0 else 0
            score = (volatility_pct + range_pct) * math.log(max(vol_usdt, 1e6)) / 1000

            candidates.append({
                "symbol": symbol,
                "price": price,
                "volume": vol_usdt,
                "volatility": volatility_pct,
                "score": score,
            })

        candidates.sort(key=lambda x: -x["score"])
        print(f"[Screener] Top {min(top_n, len(candidates))}/{len(candidates)} candidates in {time.time()-t0:.1f}s")
        return candidates[:top_n]