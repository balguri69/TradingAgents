"""Comprehensive out-of-sample quantitative validation harness for Phase 9 Probability Engine."""

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
from tradingagents.dataflows.features.probability import ProbabilityEngine, ScoringConfig
from tradingagents.dataflows.features.store import InMemoryFeatureStore
from tradingagents.dataflows.features.structure import MarketStructureEngine


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

        # Vendor rounding correction (e.g. Yahoo forex rounding where open/close exceeds high/low by 0.0001)
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


def evaluate_prediction(
    pred_direction: str,
    actual_return: float,
    threshold: float,
) -> tuple[str, bool]:
    """Determine actual ternary outcome and whether prediction was correct."""
    if actual_return > threshold:
        actual_class = "BULLISH"
    elif actual_return < -threshold:
        actual_class = "BEARISH"
    else:
        actual_class = "NEUTRAL"

    is_correct = (pred_direction == actual_class)
    return actual_class, is_correct


def run_probability_validation(max_files: int | None = None) -> dict:
    files = sorted([
        f for f in glob.glob("tests/data/real_market/*.json")
        if not f.endswith("validation_stats.json")
    ])
    if max_files is not None:
        files = files[:max_files]

    print(f"Loaded {len(files)} historical market datasets for validation.")

    # Validation aggregators
    total_samples = 0
    predictions_record = []

    # Horizonal metrics: h in (5, 10, 20)
    horizons = (5, 10, 20)
    horizon_stats = {
        h: {
            "correct": 0,
            "total": 0,
            "directional_correct": 0,
            "directional_total": 0,
            "confusion": defaultdict(lambda: defaultdict(int)),
            "per_class": defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "support": 0}),
            "confidence_buckets": defaultdict(lambda: {"correct": 0, "total": 0, "dir_correct": 0, "dir_total": 0}),
            "calibration_bull": defaultdict(lambda: {"sum_prob": 0.0, "positive_count": 0, "total": 0}),
            "calibration_bear": defaultdict(lambda: {"sum_prob": 0.0, "positive_count": 0, "total": 0}),
            "regimes": defaultdict(lambda: {"correct": 0, "total": 0, "dir_correct": 0, "dir_total": 0}),
            "features_attribution": defaultdict(lambda: {"correct": 0, "total": 0, "dir_correct": 0, "dir_total": 0}),
            "by_asset_class": defaultdict(lambda: {"correct": 0, "total": 0, "dir_correct": 0, "dir_total": 0}),
            "by_timeframe": defaultdict(lambda: {"correct": 0, "total": 0, "dir_correct": 0, "dir_total": 0}),
        }
        for h in horizons
    }

    t0 = time.perf_counter()

    for idx, fn in enumerate(files, 1):
        basename = os.path.basename(fn)
        parts = basename.replace(".json", "").split("_")
        symbol = parts[0]
        tf_str = parts[1]
        tf_enum = map_tf_enum(tf_str)

        # Classify asset class
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

        # Build feature store and compute features up to historical point
        store = InMemoryFeatureStore()
        ind_engine = IndicatorEngine(feature_store=store)
        struct_engine = MarketStructureEngine(feature_store=store)
        prob_engine = ProbabilityEngine(feature_store=store)

        ind_engine.execute_all(symbol, tf_enum, series, store_results=True)
        struct_engine.execute_all(symbol, tf_enum, series, store_results=True)

        # Compute rolling ATR for threshold scaling
        tr_list = []
        for i in range(1, len(candles)):
            curr = candles[i]
            prev = candles[i - 1]
            tr = max(
                curr.high - curr.low,
                abs(curr.high - prev.close),
                abs(curr.low - prev.close),
            )
            tr_list.append(float(tr))

        # Replay candles sequentially
        warmup = 35
        n_candles = len(candles)

        dataset_samples = 0
        for i in range(warmup, n_candles - 21):
            curr_c = candles[i]
            ts = curr_c.timestamp
            close_price = curr_c.close

            # Forward prices
            c5 = float(candles[i + 5].close)
            c10 = float(candles[i + 10].close)
            c20 = float(candles[i + 20].close)
            c0 = float(close_price)

            r5 = (c5 - c0) / c0
            r10 = (c10 - c0) / c0
            r20 = (c20 - c0) / c0

            # Local ATR
            local_atr = (sum(tr_list[max(0, i - 14):i]) / max(1, len(tr_list[max(0, i - 14):i])))
            atr_pct = local_atr / c0 if c0 > 0 else 0.005

            # Dynamic neutrality threshold per horizon
            # Move within 0.25 ATR is considered neutral/noise
            thresh_5 = max(0.0005, min(0.015, 0.25 * atr_pct))
            thresh_10 = max(0.0008, min(0.020, 0.35 * atr_pct))
            thresh_20 = max(0.0010, min(0.030, 0.50 * atr_pct))

            # Probability computation strictly as of ts
            dto = prob_engine.compute_probability(
                symbol=symbol,
                timeframe=tf_enum,
                as_of=ts,
                current_price=close_price,
                store_results=False,
            )

            p_bull = float(dto.bullish_probability)
            p_bear = float(dto.bearish_probability)
            p_neutral = float(dto.neutral_probability)
            conf = float(dto.confidence)

            # Dominant ternary class
            if p_neutral >= 50.0:
                pred_class = "NEUTRAL"
            elif p_bull > p_bear and p_bull >= p_neutral:
                pred_class = "BULLISH"
            elif p_bear > p_bull and p_bear >= p_neutral:
                pred_class = "BEARISH"
            elif p_bull > p_bear:
                pred_class = "BULLISH"
            elif p_bear > p_bull:
                pred_class = "BEARISH"
            else:
                pred_class = "NEUTRAL"

            # Dominant directional bias
            dir_bias = None
            if p_bull > p_bear and p_bull >= 30.0:
                dir_bias = "BULLISH"
            elif p_bear > p_bull and p_bear >= 30.0:
                dir_bias = "BEARISH"

            # Confidence bucket
            if conf >= 90.0:
                conf_bucket = "90-100%"
            elif conf >= 80.0:
                conf_bucket = "80-90%"
            elif conf >= 70.0:
                conf_bucket = "70-80%"
            elif conf >= 60.0:
                conf_bucket = "60-70%"
            elif conf >= 50.0:
                conf_bucket = "50-60%"
            else:
                conf_bucket = "40-50%"

            # Calibration buckets for probabilities
            def get_prob_bin(p: float) -> str:
                b = int(p // 10) * 10
                b = min(90, max(0, b))
                return f"{b}-{b+10}%"

            bin_bull = get_prob_bin(p_bull)
            bin_bear = get_prob_bin(p_bear)

            # Regime detection
            # 1. Volatility regime: ATR relative to asset volatility
            vol_regime = "HIGH_VOLATILITY" if atr_pct > 0.008 else "LOW_VOLATILITY"
            # 2. Trend regime: price vs 20-bar SMA
            sma20_val = sum(float(candles[k].close) for k in range(i - 19, i + 1)) / 20.0
            price_dist = abs(c0 - sma20_val) / sma20_val
            trend_regime = "TRENDING" if price_dist > (0.5 * atr_pct) else "RANGING"

            # Active features
            active_feat_names = [c.feature_name.lower() for c in dto.contributing_features if c.score != Decimal("0")]

            # Record stats across horizons
            horiz_data = [
                (5, r5, thresh_5),
                (10, r10, thresh_10),
                (20, r20, thresh_20),
            ]

            for h, ret, thresh in horiz_data:
                act_class, is_correct = evaluate_prediction(pred_class, ret, thresh)
                st = horizon_stats[h]

                st["total"] += 1
                if is_correct:
                    st["correct"] += 1

                # Confusion matrix
                st["confusion"][pred_class][act_class] += 1

                # Precision / Recall support
                st["per_class"][act_class]["support"] += 1
                if is_correct:
                    st["per_class"][pred_class]["tp"] += 1
                else:
                    st["per_class"][pred_class]["fp"] += 1
                    st["per_class"][act_class]["fn"] += 1

                # Directional evaluation (when engine takes directional stance)
                if dir_bias is not None:
                    st["directional_total"] += 1
                    is_dir_correct = (
                        (dir_bias == "BULLISH" and ret > 0) or
                        (dir_bias == "BEARISH" and ret < 0)
                    )
                    if is_dir_correct:
                        st["directional_correct"] += 1

                    # Confidence bucket directional accuracy
                    st["confidence_buckets"][conf_bucket]["dir_total"] += 1
                    if is_dir_correct:
                        st["confidence_buckets"][conf_bucket]["dir_correct"] += 1

                    # Regime directional accuracy
                    st["regimes"][trend_regime]["dir_total"] += 1
                    st["regimes"][vol_regime]["dir_total"] += 1
                    if is_dir_correct:
                        st["regimes"][trend_regime]["dir_correct"] += 1
                        st["regimes"][vol_regime]["dir_correct"] += 1

                    # Asset class & Timeframe stats
                    st["by_asset_class"][asset_class]["dir_total"] += 1
                    if is_dir_correct:
                        st["by_asset_class"][asset_class]["dir_correct"] += 1
                    st["by_timeframe"][tf_str]["dir_total"] += 1
                    if is_dir_correct:
                        st["by_timeframe"][tf_str]["dir_correct"] += 1

                    # Feature attribution
                    for fn_item in active_feat_names:
                        st["features_attribution"][fn_item]["dir_total"] += 1
                        if is_dir_correct:
                            st["features_attribution"][fn_item]["dir_correct"] += 1

                # Confidence bucket overall accuracy
                st["confidence_buckets"][conf_bucket]["total"] += 1
                if is_correct:
                    st["confidence_buckets"][conf_bucket]["correct"] += 1

                # Calibration updates
                st["calibration_bull"][bin_bull]["total"] += 1
                st["calibration_bull"][bin_bull]["sum_prob"] += p_bull
                if ret > thresh:
                    st["calibration_bull"][bin_bull]["positive_count"] += 1

                st["calibration_bear"][bin_bear]["total"] += 1
                st["calibration_bear"][bin_bear]["sum_prob"] += p_bear
                if ret < -thresh:
                    st["calibration_bear"][bin_bear]["positive_count"] += 1

            total_samples += 1
            dataset_samples += 1

        print(f"[{idx:2}/{len(files):2}] {symbol:10} {tf_str:3} ({asset_class:11}) | Evaluated: {dataset_samples:4} predictions")

    t1 = time.perf_counter()
    print(f"\nCompleted validation over {total_samples:,} predictions across {len(files)} datasets in {t1 - t0:.2f}s.")

    # Calculate final precision, recall, F1, calibration, etc.
    summary = {
        "total_datasets": len(files),
        "total_predictions_evaluated": total_samples,
        "runtime_seconds": t1 - t0,
        "horizons": {},
    }

    for h in horizons:
        st = horizon_stats[h]
        tot = max(1, st["total"])
        overall_acc = (st["correct"] / tot) * 100.0

        dir_tot = max(1, st["directional_total"])
        dir_acc = (st["directional_correct"] / dir_tot) * 100.0

        # Per-class metrics
        class_metrics = {}
        for c in ["BULLISH", "BEARISH", "NEUTRAL"]:
            tp = st["per_class"][c]["tp"]
            fp = st["per_class"][c]["fp"]
            fn = st["per_class"][c]["fn"]
            supp = st["per_class"][c]["support"]

            prec = (tp / (tp + fp) * 100.0) if (tp + fp) > 0 else 0.0
            rec = (tp / (tp + fn) * 100.0) if (tp + fn) > 0 else 0.0
            f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0

            class_metrics[c] = {
                "precision": prec,
                "recall": rec,
                "f1": f1,
                "support": supp,
            }

        # Confidence analysis
        conf_analysis = {}
        for b in ["40-50%", "50-60%", "60-70%", "70-80%", "80-90%", "90-100%"]:
            b_data = st["confidence_buckets"][b]
            b_tot = b_data["total"]
            b_dir_tot = b_data["dir_total"]
            b_acc = (b_data["correct"] / b_tot * 100.0) if b_tot > 0 else 0.0
            b_dir_acc = (b_data["dir_correct"] / b_dir_tot * 100.0) if b_dir_tot > 0 else 0.0
            conf_analysis[b] = {
                "samples": b_tot,
                "overall_accuracy": b_acc,
                "directional_samples": b_dir_tot,
                "directional_accuracy": b_dir_acc,
            }

        # Calibration curves & ECE
        calib_bull = {}
        ece_bull_num = 0.0
        for b_name in sorted(st["calibration_bull"].keys()):
            b_dat = st["calibration_bull"][b_name]
            cnt = b_dat["total"]
            if cnt > 0:
                mean_pred = b_dat["sum_prob"] / cnt
                realized = (b_dat["positive_count"] / cnt) * 100.0
                ece_bull_num += abs(mean_pred - realized) * cnt
                calib_bull[b_name] = {
                    "count": cnt,
                    "mean_pred_pct": mean_pred,
                    "realized_pct": realized,
                    "error": abs(mean_pred - realized),
                }
        ece_bull = (ece_bull_num / tot) if tot > 0 else 0.0

        calib_bear = {}
        ece_bear_num = 0.0
        for b_name in sorted(st["calibration_bear"].keys()):
            b_dat = st["calibration_bear"][b_name]
            cnt = b_dat["total"]
            if cnt > 0:
                mean_pred = b_dat["sum_prob"] / cnt
                realized = (b_dat["positive_count"] / cnt) * 100.0
                ece_bear_num += abs(mean_pred - realized) * cnt
                calib_bear[b_name] = {
                    "count": cnt,
                    "mean_pred_pct": mean_pred,
                    "realized_pct": realized,
                    "error": abs(mean_pred - realized),
                }
        ece_bear = (ece_bear_num / tot) if tot > 0 else 0.0

        # Regimes
        regime_analysis = {}
        for r_name, r_data in st["regimes"].items():
            r_tot = r_data["dir_total"]
            r_acc = (r_data["dir_correct"] / r_tot * 100.0) if r_tot > 0 else 0.0
            regime_analysis[r_name] = {
                "samples": r_tot,
                "directional_accuracy": r_acc,
            }

        # Asset classes
        asset_class_analysis = {}
        for ac_name, ac_data in st["by_asset_class"].items():
            ac_tot = ac_data["dir_total"]
            ac_acc = (ac_data["dir_correct"] / ac_tot * 100.0) if ac_tot > 0 else 0.0
            asset_class_analysis[ac_name] = {
                "samples": ac_tot,
                "directional_accuracy": ac_acc,
            }

        # Timeframes
        tf_analysis = {}
        for tf_k, tf_data in st["by_timeframe"].items():
            tf_tot = tf_data["dir_total"]
            tf_acc = (tf_data["dir_correct"] / tf_tot * 100.0) if tf_tot > 0 else 0.0
            tf_analysis[tf_k] = {
                "samples": tf_tot,
                "directional_accuracy": tf_acc,
            }

        # Features attribution
        feat_analysis = {}
        for f_name, f_data in sorted(st["features_attribution"].items()):
            f_tot = f_data["dir_total"]
            f_acc = (f_data["dir_correct"] / f_tot * 100.0) if f_tot > 0 else 0.0
            feat_analysis[f_name] = {
                "samples": f_tot,
                "directional_accuracy": f_acc,
            }

        summary["horizons"][f"h{h}"] = {
            "overall_accuracy": overall_acc,
            "directional_accuracy": dir_acc,
            "directional_samples": dir_tot,
            "confusion_matrix": {k: dict(v) for k, v in st["confusion"].items()},
            "class_metrics": class_metrics,
            "confidence_analysis": conf_analysis,
            "calibration_bullish": calib_bull,
            "calibration_bearish": calib_bear,
            "expected_calibration_error_bull": ece_bull,
            "expected_calibration_error_bear": ece_bear,
            "regimes": regime_analysis,
            "asset_classes": asset_class_analysis,
            "timeframes": tf_analysis,
            "features_attribution": feat_analysis,
        }

    # Save to JSON
    out_path = "tests/data/probability_validation_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nValidation statistics successfully persisted to {out_path}")
    return summary


if __name__ == "__main__":
    run_probability_validation()
