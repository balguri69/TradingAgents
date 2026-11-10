"""Comprehensive out-of-sample quantitative validation harness for Phase 11 Risk Engine."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import glob
import json
import math
import os
import sys
import time
import tracemalloc

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
from tradingagents.dataflows.features.indicators import IndicatorEngine
from tradingagents.dataflows.features.probability import ProbabilityEngine
from tradingagents.dataflows.features.store import InMemoryFeatureStore
from tradingagents.dataflows.features.structure import MarketStructureEngine
from tradingagents.orchestration.orchestrator import MultiAgentOrchestrator
from tradingagents.risk.config import RiskConfig
from tradingagents.risk.engine import RiskEngine


def map_tf_enum(tf_str: str) -> Timeframe:
    mapping = {
        "1d": Timeframe.D1,
        "4h": Timeframe.H4,
        "1h": Timeframe.H1,
        "15m": Timeframe.M15,
        "5m": Timeframe.M5,
    }
    return mapping[tf_str.lower()]


def load_candles_from_json(filepath: str) -> tuple[CandleDTO, ...]:
    with open(filepath, "r", encoding="utf-8") as f:
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

        h = max(h, o, c)
        l = min(l, o, c)
        if v < Decimal("0"):
            v = Decimal("0.0")

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


def run_risk_validation(max_files: int | None = None) -> dict:
    files = sorted([
        f for f in glob.glob("tests/data/real_market/*.json")
        if not f.endswith("validation_stats.json") and not f.endswith("probability_validation_results.json")
    ])
    if max_files is not None:
        files = files[:max_files]

    print(f"Loaded {len(files)} historical market datasets for Risk Engine validation.")

    total_samples = 0
    t0 = time.perf_counter()
    tracemalloc.start()

    # Collectors for analysis
    horizons = (5, 10, 20)

    # 1. By Risk Level (LOW, MODERATE, HIGH, EXTREME)
    risk_level_stats = {
        h: defaultdict(lambda: {
            "count": 0,
            "sum_adverse_excursion": 0.0,
            "max_adverse_excursion": 0.0,
            "adverse_excursions": [],
            "sum_forward_drawdown": 0.0,
            "max_forward_drawdown": 0.0,
            "forward_drawdowns": [],
            "sum_vol_expansion": 0.0,
        })
        for h in horizons
    }

    # 2. By Volatility Regime (COMPRESSED, NORMAL, ELEVATED, EXPLOSIVE)
    vol_regime_stats = {
        h: defaultdict(lambda: {
            "count": 0,
            "sum_vol_expansion": 0.0,
            "vol_expansions": [],
            "breakout_moves": 0,
            "sum_max_move": 0.0,
        })
        for h in horizons
    }

    # 3. By Regime Tradeability (True vs False)
    tradeability_stats = {
        h: {
            True: {
                "count": 0,
                "sum_adverse_excursion": 0.0,
                "max_adverse_excursion": 0.0,
                "adverse_excursions": [],
                "sum_return": 0.0,
                "win_count": 0,
            },
            False: {
                "count": 0,
                "sum_adverse_excursion": 0.0,
                "max_adverse_excursion": 0.0,
                "adverse_excursions": [],
                "sum_return": 0.0,
                "win_count": 0,
            },
        }
        for h in horizons
    }

    # 4. By Invalidation Risk (LOW, MODERATE, ELEVATED, CRITICAL)
    invalidation_stats = {
        h: defaultdict(lambda: {
            "count": 0,
            "invalidation_hits": 0,
            "sum_adverse_excursion": 0.0,
        })
        for h in horizons
    }

    # 5. By Position Suitability
    suitability_stats = {
        h: defaultdict(lambda: {
            "count": 0,
            "sum_drawdown": 0.0,
            "sum_adverse_excursion": 0.0,
        })
        for h in horizons
    }

    # 6. Correlation tracking: (Risk Score vs Forward Drawdown, Conflict Ratio vs Forward AE)
    correlation_pairs = {
        h: {
            "risk_score": [],
            "drawdown": [],
            "conflict_ratio": [],
            "adverse_excursion": [],
            "vol_score": [],
            "vol_expansion": [],
        }
        for h in horizons
    }

    # 7. Asset Class and Timeframe breakdown
    asset_breakdown = defaultdict(lambda: defaultdict(int))
    tf_breakdown = defaultdict(lambda: defaultdict(int))

    for idx, fn in enumerate(files, 1):
        basename = os.path.basename(fn)
        parts = basename.replace(".json", "").split("_")
        symbol = parts[0]
        tf_str = parts[1]
        tf_enum = map_tf_enum(tf_str)

        if symbol in {"BTCUSDT", "ETHUSDT"}:
            asset_class = "CRYPTO"
        elif symbol in {"EURUSD", "GBPUSD"}:
            asset_class = "FOREX"
        elif symbol in {"SPY", "QQQ"}:
            asset_class = "EQUITIES"
        elif symbol in {"NIFTY50", "BANKNIFTY"}:
            asset_class = "INDICES"
        elif symbol in {"XAUUSD"}:
            asset_class = "COMMODITIES"
        else:
            asset_class = "OTHER"

        candles = load_candles_from_json(fn)
        if len(candles) < 60:
            continue

        series = OHLCVSeriesDTO(symbol=symbol, timeframe=tf_enum, candles=candles)

        # Build feature store and compute baseline features up to historical point
        store = InMemoryFeatureStore()
        ind_engine = IndicatorEngine(feature_store=store)
        struct_engine = MarketStructureEngine(feature_store=store)
        prob_engine = ProbabilityEngine(feature_store=store)
        orchestrator = MultiAgentOrchestrator(feature_store=store)
        risk_engine = RiskEngine(feature_store=store)

        ind_engine.execute_all(symbol, tf_enum, series, store_results=True)
        struct_engine.execute_all(symbol, tf_enum, series, store_results=True)
        prob_engine.execute(symbol, tf_enum, series, store_results=True)

        # Precompute rolling TR and return standard deviation
        closes = [float(c.close) for c in candles]
        highs = [float(c.high) for c in candles]
        lows = [float(c.low) for c in candles]
        n_candles = len(candles)

        # True ranges
        tr_list = []
        log_rets = []
        for i in range(1, n_candles):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            tr_list.append(tr)
            ret = math.log(closes[i] / closes[i - 1]) if closes[i - 1] > 0 else 0.0
            log_rets.append(ret)

        warmup = 35
        file_samples = 0

        for i in range(warmup, n_candles - 21):
            curr_c = candles[i]
            ts = curr_c.timestamp
            c0 = closes[i]

            # Past 14-candle realized volatility (annualized / bar std)
            past_rets = log_rets[max(0, i - 14):i]
            mean_past = sum(past_rets) / max(1, len(past_rets))
            var_past = sum((x - mean_past) ** 2 for x in past_rets) / max(1, len(past_rets))
            past_vol = math.sqrt(var_past) if var_past > 0 else 0.001

            # Upstream orchestration assessment strictly as of ts
            upstream_assessment = orchestrator.assess(
                symbol=symbol,
                timeframe=tf_enum,
                as_of=ts,
                current_price=curr_c.close,
            )

            # Risk Engine assessment strictly as of ts
            risk_dto = risk_engine.assess_risk(
                symbol=symbol,
                timeframe=tf_enum,
                as_of=ts,
                current_price=curr_c.close,
                upstream_assessment=upstream_assessment,
                directional_intent=upstream_assessment.directional_bias.value,
                store_results=False,
            )

            total_samples += 1
            file_samples += 1

            r_level = risk_dto.risk_level.value
            v_regime = risk_dto.volatility_regime.value
            is_tradeable = risk_dto.regime_tradeable
            inv_risk = risk_dto.invalidation_risk.value
            suitability = risk_dto.position_suitability.value
            risk_score_val = float(risk_dto.risk_score)
            conflict_ratio_val = float(risk_dto.signal_conflict_ratio)
            vol_score_val = float(risk_dto.sub_metrics.volatility_score)

            asset_breakdown[asset_class][r_level] += 1
            tf_breakdown[tf_str][r_level] += 1

            # Evaluate forward outcomes across horizons
            for h in horizons:
                f_closes = closes[i + 1: i + 1 + h]
                f_highs = highs[i + 1: i + 1 + h]
                f_lows = lows[i + 1: i + 1 + h]

                min_low = min(f_lows)
                max_high = max(f_highs)
                end_close = f_closes[-1]

                # Drawdown from current close
                dd = max(0.0, (c0 - min_low) / c0)
                runup = max(0.0, (max_high - c0) / c0)

                # Directional adverse excursion
                direction = upstream_assessment.directional_bias.value
                if direction == "BULLISH":
                    ae = dd  # adverse excursion for long is downward dip
                    ret = (end_close - c0) / c0
                elif direction == "BEARISH":
                    ae = runup  # adverse excursion for short is upward spike
                    ret = (c0 - end_close) / c0
                else:  # NEUTRAL
                    ae = max(dd, runup)
                    ret = -abs(end_close - c0) / c0  # neutral suffers from large directional drift

                # Forward realized volatility
                f_rets = log_rets[i: i + h]
                mean_f = sum(f_rets) / max(1, len(f_rets))
                var_f = sum((x - mean_f) ** 2 for x in f_rets) / max(1, len(f_rets))
                forward_vol = math.sqrt(var_f) if var_f > 0 else 0.001
                vol_expansion = forward_vol / past_vol if past_vol > 0 else 1.0

                # Max excursion move
                max_abs_move = max(abs(max_high - c0) / c0, abs(c0 - min_low) / c0)

                # 1. Update Risk Level Stats
                rl_entry = risk_level_stats[h][r_level]
                rl_entry["count"] += 1
                rl_entry["sum_adverse_excursion"] += ae
                rl_entry["max_adverse_excursion"] = max(rl_entry["max_adverse_excursion"], ae)
                rl_entry["adverse_excursions"].append(ae)
                rl_entry["sum_forward_drawdown"] += dd
                rl_entry["max_forward_drawdown"] = max(rl_entry["max_forward_drawdown"], dd)
                rl_entry["forward_drawdowns"].append(dd)
                rl_entry["sum_vol_expansion"] += vol_expansion

                # 2. Update Volatility Regime Stats
                vr_entry = vol_regime_stats[h][v_regime]
                vr_entry["count"] += 1
                vr_entry["sum_vol_expansion"] += vol_expansion
                vr_entry["vol_expansions"].append(vol_expansion)
                vr_entry["sum_max_move"] += max_abs_move
                if max_abs_move > 0.015:  # >= 1.5% breakout move
                    vr_entry["breakout_moves"] += 1

                # 3. Update Tradeability Stats
                tr_entry = tradeability_stats[h][is_tradeable]
                tr_entry["count"] += 1
                tr_entry["sum_adverse_excursion"] += ae
                tr_entry["max_adverse_excursion"] = max(tr_entry["max_adverse_excursion"], ae)
                tr_entry["adverse_excursions"].append(ae)
                tr_entry["sum_return"] += ret
                if ret > 0:
                    tr_entry["win_count"] += 1

                # 4. Update Invalidation Stats
                inv_entry = invalidation_stats[h][inv_risk]
                inv_entry["count"] += 1
                inv_entry["sum_adverse_excursion"] += ae
                # Invalidation hit if adverse move exceeds 1.5%
                if ae >= 0.015:
                    inv_entry["invalidation_hits"] += 1

                # 5. Update Position Suitability Stats
                suit_entry = suitability_stats[h][suitability]
                suit_entry["count"] += 1
                suit_entry["sum_drawdown"] += dd
                suit_entry["sum_adverse_excursion"] += ae

                # 6. Correlation Pairs
                correlation_pairs[h]["risk_score"].append(risk_score_val)
                correlation_pairs[h]["drawdown"].append(dd)
                correlation_pairs[h]["conflict_ratio"].append(conflict_ratio_val)
                correlation_pairs[h]["adverse_excursion"].append(ae)
                correlation_pairs[h]["vol_score"].append(vol_score_val)
                correlation_pairs[h]["vol_expansion"].append(vol_expansion)

        if idx % 5 == 0 or idx == len(files):
            print(f"[{idx}/{len(files)}] Processed {symbol}_{tf_str} ({file_samples} candles, cumulative: {total_samples})")

    elapsed = time.perf_counter() - t0
    cur_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"\nCompleted validation over {total_samples} candle observations in {elapsed:.2f}s ({total_samples/elapsed:.1f} candles/sec).")

    # Helper for Pearson correlation
    def pearson(x: list[float], y: list[float]) -> float:
        n = len(x)
        if n < 2:
            return 0.0
        mx = sum(x) / n
        my = sum(y) / n
        num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
        den_x = math.sqrt(sum((x[i] - mx) ** 2 for i in range(n)))
        den_y = math.sqrt(sum((y[i] - my) ** 2 for i in range(n)))
        if den_x == 0 or den_y == 0:
            return 0.0
        return num / (den_x * den_y)

    # Compile summarized report
    report = {
        "metadata": {
            "total_files": len(files),
            "total_samples": total_samples,
            "elapsed_seconds": elapsed,
            "throughput_candles_per_sec": total_samples / elapsed if elapsed > 0 else 0,
            "peak_memory_mb": peak_mem / (1024 * 1024),
        },
        "correlations": {
            f"h{h}": {
                "corr_risk_score_vs_drawdown": pearson(correlation_pairs[h]["risk_score"], correlation_pairs[h]["drawdown"]),
                "corr_conflict_vs_adverse_excursion": pearson(correlation_pairs[h]["conflict_ratio"], correlation_pairs[h]["adverse_excursion"]),
                "corr_vol_score_vs_vol_expansion": pearson(correlation_pairs[h]["vol_score"], correlation_pairs[h]["vol_expansion"]),
            }
            for h in horizons
        },
        "risk_levels": {},
        "volatility_regimes": {},
        "tradeability": {},
        "invalidation_risk": {},
        "position_suitability": {},
        "asset_breakdown": {k: dict(v) for k, v in asset_breakdown.items()},
        "timeframe_breakdown": {k: dict(v) for k, v in tf_breakdown.items()},
    }

    # Format risk levels
    for h in horizons:
        report["risk_levels"][f"h{h}"] = {}
        for r_lvl, stats in risk_level_stats[h].items():
            cnt = stats["count"]
            if cnt == 0:
                continue
            sorted_aes = sorted(stats["adverse_excursions"])
            sorted_dds = sorted(stats["forward_drawdowns"])
            p95_ae = sorted_aes[int(0.95 * cnt)] if cnt > 20 else stats["max_adverse_excursion"]
            p95_dd = sorted_dds[int(0.95 * cnt)] if cnt > 20 else stats["max_forward_drawdown"]
            report["risk_levels"][f"h{h}"][r_lvl] = {
                "count": cnt,
                "pct_of_total": cnt / total_samples * 100,
                "avg_adverse_excursion_pct": (stats["sum_adverse_excursion"] / cnt) * 100,
                "max_adverse_excursion_pct": stats["max_adverse_excursion"] * 100,
                "p95_adverse_excursion_pct": p95_ae * 100,
                "avg_forward_drawdown_pct": (stats["sum_forward_drawdown"] / cnt) * 100,
                "max_forward_drawdown_pct": stats["max_forward_drawdown"] * 100,
                "p95_forward_drawdown_pct": p95_dd * 100,
                "avg_vol_expansion": stats["sum_vol_expansion"] / cnt,
            }

    # Format volatility regimes
    for h in horizons:
        report["volatility_regimes"][f"h{h}"] = {}
        for v_reg, stats in vol_regime_stats[h].items():
            cnt = stats["count"]
            if cnt == 0:
                continue
            sorted_vols = sorted(stats["vol_expansions"])
            p90_vol = sorted_vols[int(0.90 * cnt)] if cnt > 20 else 1.0
            report["volatility_regimes"][f"h{h}"][v_reg] = {
                "count": cnt,
                "pct_of_total": cnt / total_samples * 100,
                "avg_vol_expansion": stats["sum_vol_expansion"] / cnt,
                "p90_vol_expansion": p90_vol,
                "breakout_rate_pct": (stats["breakout_moves"] / cnt) * 100,
                "avg_max_move_pct": (stats["sum_max_move"] / cnt) * 100,
            }

    # Format tradeability
    for h in horizons:
        report["tradeability"][f"h{h}"] = {}
        for is_tr, stats in tradeability_stats[h].items():
            cnt = stats["count"]
            if cnt == 0:
                continue
            sorted_aes = sorted(stats["adverse_excursions"])
            p95_ae = sorted_aes[int(0.95 * cnt)] if cnt > 20 else stats["max_adverse_excursion"]
            report["tradeability"][f"h{h}"]["TRADEABLE" if is_tr else "NON_TRADEABLE"] = {
                "count": cnt,
                "pct_of_total": cnt / total_samples * 100,
                "avg_adverse_excursion_pct": (stats["sum_adverse_excursion"] / cnt) * 100,
                "p95_adverse_excursion_pct": p95_ae * 100,
                "avg_return_pct": (stats["sum_return"] / cnt) * 100,
                "win_rate_pct": (stats["win_count"] / cnt) * 100,
            }

    # Format invalidation
    for h in horizons:
        report["invalidation_risk"][f"h{h}"] = {}
        for inv_lvl, stats in invalidation_stats[h].items():
            cnt = stats["count"]
            if cnt == 0:
                continue
            report["invalidation_risk"][f"h{h}"][inv_lvl] = {
                "count": cnt,
                "pct_of_total": cnt / total_samples * 100,
                "invalidation_hit_rate_pct": (stats["invalidation_hits"] / cnt) * 100,
                "avg_adverse_excursion_pct": (stats["sum_adverse_excursion"] / cnt) * 100,
            }

    # Format suitability
    for h in horizons:
        report["position_suitability"][f"h{h}"] = {}
        for suit, stats in suitability_stats[h].items():
            cnt = stats["count"]
            if cnt == 0:
                continue
            report["position_suitability"][f"h{h}"][suit] = {
                "count": cnt,
                "pct_of_total": cnt / total_samples * 100,
                "avg_drawdown_pct": (stats["sum_drawdown"] / cnt) * 100,
                "avg_adverse_excursion_pct": (stats["sum_adverse_excursion"] / cnt) * 100,
            }

    # Output file
    out_path = "tests/data/risk_validation_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\nSaved risk validation results to {out_path}")
    return report


if __name__ == "__main__":
    run_risk_validation()
