"""Generate visual chart overlays for Phase 8 real-market inspection."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

# Add project root to sys.path
sys.path.insert(0, os.path.abspath("."))

# Minimal dotenv shim
import types
if "dotenv" not in sys.modules:
    d = types.ModuleType("dotenv")
    d.load_dotenv = lambda *a, **k: None
    d.find_dotenv = lambda *a, **k: ""
    sys.modules["dotenv"] = d

from tradingagents.dataflows.dto.market_data import CandleDTO, OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.features.structure import MarketStructureEngine


def generate_ascii_chart(symbol: str, tf_str: str, slice_len: int = 40) -> str:
    fn = f"tests/data/real_market/{symbol}_{tf_str}.json"
    with open(fn) as f:
        raw = json.load(f)

    candles = []
    for item in raw[-slice_len:]:
        dt = datetime.fromisoformat(item["timestamp"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        o = Decimal(str(item["open"]))
        h = Decimal(str(item["high"]))
        l = Decimal(str(item["low"]))
        c = Decimal(str(item["close"]))
        v = Decimal(str(item.get("volume", "0.0") or "0.0"))
        candles.append(CandleDTO(dt, o, max(h, o, c), min(l, o, c), c, max(Decimal("0"), v)))

    series = OHLCVSeriesDTO(symbol=symbol, timeframe=Timeframe.H1, candles=tuple(candles))
    engine = MarketStructureEngine(register_defaults=True)
    results = engine.execute_all(symbol, Timeframe.H1, series, store_results=False)

    swings = results.get("SWING_MINOR_2_2", [])
    fvgs = results.get("FVG", [])
    bos_list = results.get("BOS", [])
    choch_list = results.get("CHOCH", [])

    lines = [f"=== SMC CHART OVERLAY: {symbol} [{tf_str}] (Last {slice_len} Bars) ==="]
    for i, c in enumerate(candles):
        # Check if candle corresponds to any detected feature
        tags = []
        for s in swings:
            if s.timestamp == c.timestamp:
                tags.append(f"[SWING {'HIGH' if s.is_high else 'LOW'} @ {s.price}]")
        for f in fvgs:
            if f.timestamp == c.timestamp:
                tags.append(f"[{'BULL' if f.is_bullish else 'BEAR'} FVG {f.lower_bound}-{f.upper_bound}]")
        for b in bos_list:
            if b.timestamp == c.timestamp:
                tags.append(f"[BOS {'BULL' if b.is_bullish else 'BEAR'} @ {b.broken_level}]")
        for ch in choch_list:
            if ch.timestamp == c.timestamp:
                tags.append(f"[CHOCH {'BULL' if ch.is_bullish else 'BEAR'} @ {ch.pivot_level}]")

        tag_str = " ".join(tags)
        bar_type = "▲ GREEN" if c.close >= c.open else "▼ RED  "
        lines.append(
            f"Bar {i:02d} | {c.timestamp.strftime('%Y-%m-%d %H:%M')} | "
            f"O:{float(c.open):10.2f} H:{float(c.high):10.2f} L:{float(c.low):10.2f} C:{float(c.close):10.2f} | "
            f"{bar_type} {tag_str}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    btc_chart = generate_ascii_chart("BTCUSDT", "1h", slice_len=25)
    xau_chart = generate_ascii_chart("XAUUSD", "1d", slice_len=25)
    spy_chart = generate_ascii_chart("SPY", "1d", slice_len=25)

    with open("tests/data/real_market/chart_overlay_samples.txt", "w") as f:
        f.write(btc_chart + "\n\n" + xau_chart + "\n\n" + spy_chart)

    print("Generated chart overlay samples.")
