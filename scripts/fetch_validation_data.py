"""Download real historical market data for Phase 8 validation."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

OUTPUT_DIR = "tests/data/real_market"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def fetch_binance_klines(symbol: str, interval: str, limit: int = 1000) -> list[dict]:
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    candles = []
    for item in data:
        # [open_time, open, high, low, close, volume, close_time, ...]
        dt = datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc).isoformat()
        candles.append({
            "timestamp": dt,
            "open": item[1],
            "high": item[2],
            "low": item[3],
            "close": item[4],
            "volume": item[5],
        })
    return candles

def fetch_yahoo_chart(symbol: str, interval: str, range_str: str) -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_str}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    
    result = data["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    quotes = result["indicators"]["quote"][0]
    opens = quotes.get("open", [])
    highs = quotes.get("high", [])
    lows = quotes.get("low", [])
    closes = quotes.get("close", [])
    volumes = quotes.get("volume", [])

    candles = []
    for i, ts in enumerate(timestamps):
        if (
            i < len(opens) and opens[i] is not None
            and i < len(highs) and highs[i] is not None
            and i < len(lows) and lows[i] is not None
            and i < len(closes) and closes[i] is not None
        ):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            vol = str(volumes[i]) if (i < len(volumes) and volumes[i] is not None) else "0.0"
            candles.append({
                "timestamp": dt,
                "open": f"{opens[i]:.4f}",
                "high": f"{highs[i]:.4f}",
                "low": f"{lows[i]:.4f}",
                "close": f"{closes[i]:.4f}",
                "volume": vol,
            })
    return candles

def main():
    assets_binance = [("BTCUSDT", "BTCUSDT"), ("ETHUSDT", "ETHUSDT")]
    tf_binance = [("1d", "1d"), ("4h", "4h"), ("1h", "1h"), ("15m", "15m"), ("5m", "5m")]

    for name, sym in assets_binance:
        for tf_label, interval in tf_binance:
            fn = f"{OUTPUT_DIR}/{name}_{tf_label}.json"
            if os.path.exists(fn):
                print(f"Skipping {fn}, already exists.")
                continue
            try:
                print(f"Fetching Binance {sym} {tf_label}...")
                candles = fetch_binance_klines(sym, interval, limit=1000)
                with open(fn, "w") as f:
                    json.dump(candles, f)
                print(f"Saved {len(candles)} candles to {fn}")
                time.sleep(0.2)
            except Exception as e:
                print(f"Failed {sym} {tf_label}: {e}")

    assets_yahoo = [
        ("XAUUSD", "GC=F"),
        ("EURUSD", "EURUSD=X"),
        ("GBPUSD", "GBPUSD=X"),
        ("SPY", "SPY"),
        ("QQQ", "QQQ"),
        ("NIFTY50", "%5ENSEI"),
        ("BANKNIFTY", "%5ENSEBANK"),
    ]
    tf_yahoo = [
        ("1d", "1d", "2y"),
        ("1h", "1h", "60d"),
        ("15m", "15m", "30d"),
        ("5m", "5m", "10d"),
    ]

    for name, sym in assets_yahoo:
        for tf_label, interval, rng in tf_yahoo:
            fn = f"{OUTPUT_DIR}/{name}_{tf_label}.json"
            if os.path.exists(fn):
                print(f"Skipping {fn}, already exists.")
                continue
            try:
                print(f"Fetching Yahoo {name} ({sym}) {tf_label} range={rng}...")
                candles = fetch_yahoo_chart(sym, interval, rng)
                with open(fn, "w") as f:
                    json.dump(candles, f)
                print(f"Saved {len(candles)} candles to {fn}")
                time.sleep(0.3)
            except Exception as e:
                print(f"Failed Yahoo {name} {tf_label}: {e}")

    # Generate 4h for Yahoo assets by aggregating 1h candles
    for name, _ in assets_yahoo:
        fn_1h = f"{OUTPUT_DIR}/{name}_1h.json"
        fn_4h = f"{OUTPUT_DIR}/{name}_4h.json"
        if os.path.exists(fn_1h) and not os.path.exists(fn_4h):
            with open(fn_1h) as f:
                c1h = json.load(f)
            # Aggregate every 4 candles
            c4h = []
            for i in range(0, len(c1h) - 3, 4):
                grp = c1h[i:i+4]
                high = max(float(c["high"]) for c in grp)
                low = min(float(c["low"]) for c in grp)
                vol = sum(float(c["volume"]) for c in grp)
                c4h.append({
                    "timestamp": grp[0]["timestamp"],
                    "open": grp[0]["open"],
                    "high": f"{high:.4f}",
                    "low": f"{low:.4f}",
                    "close": grp[-1]["close"],
                    "volume": f"{vol:.2f}",
                })
            with open(fn_4h, "w") as f:
                json.dump(c4h, f)
            print(f"Aggregated {len(c4h)} 4h candles for {name} to {fn_4h}")

if __name__ == "__main__":
    main()
