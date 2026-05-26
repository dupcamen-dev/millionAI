import math
import json
import time
import numpy as np
from .binance_rest import BinanceFuturesAPI

class AssetScreener:
    def __init__(self, api: BinanceFuturesAPI):
        self.api = api

    def scan(self, top_n=5, min_volume=100_000_000, max_price=1000):
        info = self.api.get_exchange_info()
        tickers = self.api.get_ticker()
        ticker_map = {t["symbol"]: t for t in tickers} if isinstance(tickers, list) else {}

        candidates = []
        for s in info.get("symbols", []):
            if not s["symbol"].endswith("USDT"):
                continue
            if s["status"] != "TRADING":
                continue
            if s.get("contractType") != "PERPETUAL":
                continue
            t = ticker_map.get(s["symbol"])
            if not t:
                continue
            price = float(t.get("lastPrice", 0) or 0)
            vol_usdt = float(t.get("quoteVolume", 0) or 0)
            if price <= 0 or price >= max_price:
                continue
            if vol_usdt < min_volume:
                continue
            klines = self.api.get_klines(s["symbol"], "5m", 100)
            if not klines or len(klines) < 20:
                continue
            data = np.zeros((len(klines), 5), dtype=np.float32)
            for i, k in enumerate(klines):
                data[i] = [float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])]

            atr = np.mean([max(data[i,2]-data[i,3],
                               abs(data[i,2]-data[i-1,3]),
                               abs(data[i,3]-data[i-1,3]))
                          for i in range(1, len(data), 5)])
            vol_ratio = atr / price
            score = vol_ratio * math.log(max(vol_usdt, 1e6)) / price

            candidates.append({
                "symbol": s["symbol"],
                "price": float(price),
                "volume": float(vol_usdt),
                "volatility": float(vol_ratio * 100),
                "score": float(score),
            })

        candidates.sort(key=lambda x: -x["score"])
        return candidates[:top_n]
