"""Download historical klines from Binance → binary .bin format.

Usage: python scripts/download_binance_klines.py

Output: data/btc_usdt_5m.bin
Format: [int32 count][float O,H,L,C,V] × count
"""
import struct, time, urllib.request, json, os
import numpy as np

SYMBOL = "BTCUSDT"
INTERVAL = "5m"
YEARS = 1
OUT = os.path.join(os.path.dirname(__file__), '..', 'data', f'{SYMBOL.lower()}_{INTERVAL}.bin')

def fetch_klines(start_time: int, limit: int = 1000) -> list:
    url = (f"https://api.binance.com/api/v3/klines?"
           f"symbol={SYMBOL}&interval={INTERVAL}"
           f"&startTime={start_time}&limit={limit}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    # 1 year back from now in milliseconds
    end = int(time.time() * 1000)
    start = end - YEARS * 365 * 24 * 60 * 60 * 1000

    all_candles = []
    cur = start
    while cur < end:
        print(f"  fetching {cur}...", end=" ", flush=True)
        try:
            data = fetch_klines(cur)
        except Exception as e:
            print(f"retry after error: {e}")
            time.sleep(5)
            continue
        if not data:
            break
        all_candles.extend(data)
        cur = data[-1][0] + 1  # next open_time
        print(f"{len(data)} candles (total {len(all_candles)})")
        time.sleep(0.2)  # rate limit

    print(f"Total: {len(all_candles)} candles")

    # Extract OHLCV: O H L C V
    n = len(all_candles)
    ohlcv = np.zeros((n, 5), dtype=np.float64)
    for i, c in enumerate(all_candles):
        ohlcv[i] = [float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])]

    # Write binary: [int32 count][float O,H,L,C,V] × n
    buf = struct.pack('i', n)
    buf += ohlcv.astype(np.float32).tobytes()
    with open(OUT, 'wb') as f:
        f.write(buf)
    print(f"Written: {OUT} ({os.path.getsize(OUT):,} bytes, {n} candles)")

    # Stats
    print(f"  Price range: ${ohlcv[:,3].min():.2f} - ${ohlcv[:,3].max():.2f}")
    print(f"  Mean volume: {ohlcv[:,4].mean():.0f}")

if __name__ == '__main__':
    main()
