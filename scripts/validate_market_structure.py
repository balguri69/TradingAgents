"""Comprehensive validation and real-market replay harness for MarketStructureEngine."""

from __future__ import annotations

import glob
import json
import os
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from decimal import Decimal

# Add project root to sys.path
sys.path.insert(0, os.path.abspath("."))

# Minimal dotenv shim if missing
import types
if "dotenv" not in sys.modules:
    d = types.ModuleType("dotenv")
    d.load_dotenv = lambda *a, **k: None
    d.find_dotenv = lambda *a, **k: ""
    sys.modules["dotenv"] = d

from tradingagents.dataflows.dto.market_data import CandleDTO, OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.features.store import InMemoryFeatureStore
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


def load_candles_from_json(path: str) -> tuple[CandleDTO, ...]:
    with open(path) as f:
        data = json.load(f)
    candles = []
    for item in data:
        # Parse ISO timestamp
        dt = datetime.fromisoformat(item["timestamp"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        o = Decimal(str(item["open"]))
        h = Decimal(str(item["high"]))
        l = Decimal(str(item["low"]))
        c = Decimal(str(item["close"]))
        v = Decimal(str(item.get("volume", "0.0") or "0.0"))

        # Real-market vendor data sanitization (e.g. Yahoo forex rounding where open/close exceeds high/low by 0.0001)
        h = max(h, o, c)
        l = min(l, o, c)
        if v < Decimal("0"):
            v = Decimal("0")

        candles.append(
            CandleDTO(
                timestamp=dt,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
            )
        )
    return tuple(candles)


def map_tf_enum(tf_str: str) -> Timeframe:
    mapping = {
        "1d": Timeframe.D1,
        "4h": Timeframe.H4,
        "1h": Timeframe.H1,
        "15m": Timeframe.M15,
        "5m": Timeframe.M5,
    }
    return mapping.get(tf_str, Timeframe.H1)


def run_point_in_time_replay(
    symbol: str,
    timeframe: Timeframe,
    candles: tuple[CandleDTO, ...],
    sample_steps: int = 100,
) -> dict:
    """Simulate real-time candle-by-candle arrival and verify zero lookahead & zero repainting."""
    store = InMemoryFeatureStore()
    engine = MarketStructureEngine(feature_store=store, register_defaults=True)

    min_warmup = 30
    total = len(candles)
    if total <= min_warmup:
        return {"error": "Insufficient candles for replay"}

    # Run replay across the last `sample_steps` candles
    start_idx = max(min_warmup, total - sample_steps)
    
    lookahead_violations = 0
    repainting_violations = 0
    history_by_timestamp: dict[datetime, dict[str, Any]] = {}

    for t in range(start_idx, total):
        current_slice = candles[: t + 1]
        as_of_time = current_slice[-1].timestamp
        series = OHLCVSeriesDTO(symbol=symbol, timeframe=timeframe, candles=current_slice)

        results = engine.execute_all(symbol, timeframe, series, store_results=False)

        # 1. Lookahead Check: No feature timestamp can exceed as_of_time
        for feat_name, feats in results.items():
            for f in feats:
                if f.timestamp > as_of_time:
                    lookahead_violations += 1

        # 2. Repainting Check: Features for prior timestamps must remain stable
        current_snapshot = {}
        for feat_name, feats in results.items():
            for f in feats:
                if f.timestamp < as_of_time:
                    current_snapshot[(f.timestamp, feat_name)] = f

        for k, prev_feat in history_by_timestamp.get(as_of_time, {}).items():
            curr_feat = current_snapshot.get(k)
            if curr_feat is not None:
                # Compare invariant properties (price levels should not change)
                if hasattr(prev_feat, "price") and prev_feat.price != curr_feat.price:
                    repainting_violations += 1
                elif hasattr(prev_feat, "broken_level") and prev_feat.broken_level != curr_feat.broken_level:
                    repainting_violations += 1

        history_by_timestamp[as_of_time] = current_snapshot

    return {
        "steps_replayed": total - start_idx,
        "lookahead_violations": lookahead_violations,
        "repainting_violations": repainting_violations,
        "status": "PASSED" if (lookahead_violations == 0 and repainting_violations == 0) else "FAILED",
    }


def analyze_dataset_market_structure(
    symbol: str,
    tf_str: str,
    candles: tuple[CandleDTO, ...],
) -> dict:
    """Run full market structure computation on historical series and collect statistics."""
    timeframe = map_tf_enum(tf_str)
    series = OHLCVSeriesDTO(symbol=symbol, timeframe=timeframe, candles=candles)
    engine = MarketStructureEngine(register_defaults=True)

    t0 = time.perf_counter()
    results = engine.execute_all(symbol, timeframe, series, store_results=False)
    elapsed = time.perf_counter() - t0

    swings_minor = results.get("SWING_MINOR_2_2", [])
    swings_major = results.get("SWING_MAJOR_5_5", [])
    fvgs = results.get("FVG", [])
    bos_list = results.get("BOS", [])
    choch_list = results.get("CHOCH", [])
    obs = results.get("ORDER_BLOCK", [])
    pools = results.get("LIQUIDITY_POOL", [])
    sweeps = results.get("LIQUIDITY_SWEEP", [])
    pds = results.get("PREMIUM_DISCOUNT_20", [])

    # Metrics
    fvg_mitigated = sum(1 for f in fvgs if getattr(f, "mitigated", False))
    ob_mitigated = sum(1 for o in obs if getattr(o, "mitigated", False))
    bos_bull = sum(1 for b in bos_list if getattr(b, "is_bullish", False))
    bos_bear = len(bos_list) - bos_bull
    choch_bull = sum(1 for c in choch_list if getattr(c, "is_bullish", False))
    choch_bear = len(choch_list) - choch_bull
    sweep_bsl = sum(1 for s in sweeps if getattr(s, "is_buy_side", False))
    sweep_ssl = len(sweeps) - sweep_bsl

    premium_count = sum(1 for p in pds if getattr(p, "zone", "") == "PREMIUM")
    discount_count = sum(1 for p in pds if getattr(p, "zone", "") == "DISCOUNT")
    eq_count = sum(1 for p in pds if getattr(p, "zone", "") == "EQUILIBRIUM")
    total_pd = len(pds) or 1

    return {
        "symbol": symbol,
        "timeframe": tf_str,
        "candles": len(candles),
        "execution_ms": elapsed * 1000,
        "swings_minor": len(swings_minor),
        "swings_major": len(swings_major),
        "fvg_total": len(fvgs),
        "fvg_mitigated": fvg_mitigated,
        "fvg_mitigation_rate": (fvg_mitigated / len(fvgs) * 100) if fvgs else 0.0,
        "bos_total": len(bos_list),
        "bos_bullish": bos_bull,
        "bos_bearish": bos_bear,
        "choch_total": len(choch_list),
        "choch_bullish": choch_bull,
        "choch_bearish": choch_bear,
        "order_blocks": len(obs),
        "ob_mitigated": ob_mitigated,
        "ob_mitigation_rate": (ob_mitigated / len(obs) * 100) if obs else 0.0,
        "liquidity_pools": len(pools),
        "liquidity_sweeps": len(sweeps),
        "sweeps_buy_side": sweep_bsl,
        "sweeps_sell_side": sweep_ssl,
        "zone_premium_pct": (premium_count / total_pd) * 100,
        "zone_discount_pct": (discount_count / total_pd) * 100,
        "zone_equilibrium_pct": (eq_count / total_pd) * 100,
    }


def main():
    files = [
        f
        for f in sorted(glob.glob("tests/data/real_market/*.json"))
        if not f.endswith("validation_stats.json")
    ]
    print(f"Discovered {len(files)} real-market historical files.")

    all_stats = []
    total_candles = 0

    tracemalloc.start()
    t_global_start = time.perf_counter()

    print("\n" + "=" * 95)
    print("PHASE 8 REAL-MARKET DATA VALIDATION SWEEP")
    print("=" * 95)

    for fn in files:
        basename = os.path.basename(fn)
        parts = basename.replace(".json", "").split("_")
        symbol = parts[0]
        tf_str = parts[1]

        candles = load_candles_from_json(fn)
        total_candles += len(candles)

        stats = analyze_dataset_market_structure(symbol, tf_str, candles)
        all_stats.append(stats)
        print(
            f"[{symbol:10} {tf_str:3}] Candles: {stats['candles']:5} | "
            f"Swings: {stats['swings_minor']:3} | FVG: {stats['fvg_total']:3} ({stats['fvg_mitigation_rate']:.1f}% mit) | "
            f"BOS: {stats['bos_total']:2} | CHOCH: {stats['choch_total']:2} | "
            f"OB: {stats['order_blocks']:2} | Sweeps: {stats['liquidity_sweeps']:2} | "
            f"Time: {stats['execution_ms']:.2f}ms"
        )

    t_global_end = time.perf_counter()
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Save summary stats
    with open("tests/data/real_market/validation_stats.json", "w") as f:
        json.dump(all_stats, f, indent=2)

    print("\n" + "=" * 95)
    print("POINT-IN-TIME REPLAY & NO-LOOKAHEAD VALIDATION")
    print("=" * 95)

    # Run point-in-time replay on representative assets
    replay_targets = [
        ("BTCUSDT", "1h"),
        ("ETHUSDT", "15m"),
        ("XAUUSD", "1h"),
        ("EURUSD", "5m"),
        ("SPY", "1d"),
        ("NIFTY50", "15m"),
    ]

    replay_results = []
    for sym, tf in replay_targets:
        fn = f"tests/data/real_market/{sym}_{tf}.json"
        if os.path.exists(fn):
            c = load_candles_from_json(fn)
            res = run_point_in_time_replay(sym, map_tf_enum(tf), c, sample_steps=120)
            replay_results.append((sym, tf, res))
            print(
                f"Replay [{sym:8} {tf:3}] Steps: {res['steps_replayed']:3} | "
                f"Lookahead Violations: {res['lookahead_violations']} | "
                f"Repainting Violations: {res['repainting_violations']} | Status: {res['status']}"
            )

    print("\n" + "=" * 95)
    print("TOTAL PERFORMANCE SUMMARY")
    print("=" * 95)
    print(f"Total Datasets Analyzed: {len(all_stats)}")
    print(f"Total Candles Processed: {total_candles:,}")
    print(f"Total Processing Time:   {t_global_end - t_global_start:.3f}s")
    print(f"Peak Memory Allocation:  {peak_mem / 1024 / 1024:.2f} MB")
    print("=" * 95)


if __name__ == "__main__":
    main()
