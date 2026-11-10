"""Audit script to empirically verify SMC edge cases and algorithmic limitations."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.abspath("."))

import types
if "dotenv" not in sys.modules:
    d = types.ModuleType("dotenv")
    d.load_dotenv = lambda *a, **k: None
    d.find_dotenv = lambda *a, **k: ""
    sys.modules["dotenv"] = d

from tradingagents.dataflows.dto.market_data import CandleDTO, OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.features.structure import (
    BreakOfStructureComputer,
    ChangeOfCharacterComputer,
    FairValueGapComputer,
    LiquidityPoolComputer,
    LiquiditySweepComputer,
    MarketStructureEngine,
    OrderBlockComputer,
    PremiumDiscountComputer,
    SwingComputer,
)


def load_candles(path: str) -> tuple[CandleDTO, ...]:
    with open(path) as f:
        data = json.load(f)
    candles = []
    for item in data:
        dt = datetime.fromisoformat(item["timestamp"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        o = Decimal(str(item["open"]))
        h = Decimal(str(item["high"]))
        l = Decimal(str(item["low"]))
        c = Decimal(str(item["close"]))
        v = Decimal(str(item.get("volume", "0.0") or "0.0"))
        candles.append(CandleDTO(dt, o, max(h, o, c), min(l, o, c), c, max(Decimal("0"), v)))
    return tuple(candles)


def audit_forex_order_blocks():
    """Verify that zero volume in Forex prevents OrderBlock detection."""
    fn = "tests/data/real_market/EURUSD_1h.json"
    candles = load_candles(fn)
    ob_comp = OrderBlockComputer()
    series = OHLCVSeriesDTO("EURUSD", Timeframe.H1, candles)
    obs = ob_comp.compute("EURUSD", Timeframe.H1, series)
    zero_vol_count = sum(1 for c in candles if c.volume == Decimal("0"))
    return {
        "asset": "EURUSD 1h",
        "total_candles": len(candles),
        "zero_volume_candles": zero_vol_count,
        "order_blocks_detected": len(obs),
    }


def audit_liquidity_sweep_redundancy():
    """Check if consecutive bars wicking above the same level create duplicate sweeps."""
    fn = "tests/data/real_market/BTCUSDT_1h.json"
    candles = load_candles(fn)
    sweep_comp = LiquiditySweepComputer()
    series = OHLCVSeriesDTO("BTCUSDT", Timeframe.H1, candles)
    sweeps = sweep_comp.compute("BTCUSDT", Timeframe.H1, series)
    
    # Check consecutive sweeps with same level
    consecutive_same_level = 0
    for i in range(1, len(sweeps)):
        if sweeps[i].swept_level == sweeps[i-1].swept_level:
            consecutive_same_level += 1

    return {
        "asset": "BTCUSDT 1h",
        "total_sweeps": len(sweeps),
        "repeated_level_sweeps": consecutive_same_level,
    }


def audit_choch_frequency_by_timeframe():
    """Measure CHoCH frequency across timeframes to quantify whipsaw rate in lower timeframes."""
    results = {}
    for tf in ["1d", "4h", "1h", "15m", "5m"]:
        fn = f"tests/data/real_market/BTCUSDT_{tf}.json"
        candles = load_candles(fn)
        choch_comp = ChangeOfCharacterComputer()
        series = OHLCVSeriesDTO("BTCUSDT", Timeframe.H1, candles)
        chochs = choch_comp.compute("BTCUSDT", Timeframe.H1, series)
        results[tf] = {
            "candles": len(candles),
            "choch_count": len(chochs),
            "choch_rate_pct": (len(chochs) / len(candles)) * 100,
        }
    return results


def main():
    ob_audit = audit_forex_order_blocks()
    sweep_audit = audit_liquidity_sweep_redundancy()
    choch_audit = audit_choch_frequency_by_timeframe()

    print("=== AUDIT RESULTS ===")
    print("Forex Order Block Audit:", ob_audit)
    print("Liquidity Sweep Redundancy Audit:", sweep_audit)
    print("CHoCH Frequency Audit by Timeframe:", choch_audit)


if __name__ == "__main__":
    main()
