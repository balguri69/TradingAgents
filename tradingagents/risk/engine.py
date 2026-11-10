"""Thread-safe, deterministic Risk Engine for institutional multi-asset market risk assessment."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import threading
from typing import Any, Mapping, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer, FeatureStore
from tradingagents.dataflows.dto.features import (
    BaseFeatureDTO,
    PremiumDiscountDTO,
)
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.dto.validation import validate_utc_datetime
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.risk.config import RiskConfig
from tradingagents.risk.dto import RiskAssessmentDTO, RiskSubMetricsDTO
from tradingagents.risk.enums import (
    DrawdownRisk,
    InvalidationRisk,
    PositionSuitability,
    RiskLevel,
    VolatilityRegime,
)
from tradingagents.risk.evaluators import (
    ConflictRiskEvaluator,
    InvalidationRiskEvaluator,
    RegimeQualityEvaluator,
    VolatilityRiskEvaluator,
)

DEFAULT_MONITORED_FEATURES = (
    "bos", "BOS",
    "choch", "CHOCH",
    "order_block", "ORDER_BLOCK",
    "liquidity_sweep", "LIQUIDITY_SWEEP",
    "premium_discount", "PREMIUM_DISCOUNT", "PREMIUM_DISCOUNT_20",
    "fvg", "FVG",
    "liquidity_pool", "LIQUIDITY_POOL",
    "ema_9", "EMA_9",
    "ema_21", "EMA_21",
    "sma_20", "SMA_20",
    "sma_50", "SMA_50",
    "rsi_14", "RSI_14", "rsi", "RSI",
    "macd", "MACD", "MACD_12_26_9",
    "vwap", "VWAP",
    "bollinger", "BOLLINGER", "BB_20_2.0",
    "volume_profile", "VOLUME_PROFILE", "VP_24_70",
    "atr_14", "ATR_14", "atr", "ATR",
    "probability", "PROBABILITY",
)

PRECISION_TWO = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")


class RiskEngine:
    """Thread-safe, deterministic engine evaluating multi-dimensional institutional market risk.
    
    Guarantees:
    - Pure point-in-time correctness.
    - Zero trade execution, zero order routing.
    - Standard-library only arithmetic and logic.
    - Bounded LRU memoization with price awareness.
    """

    def __init__(
        self,
        feature_store: FeatureStore | None = None,
        config: RiskConfig | None = None,
        monitored_features: Sequence[str] | None = None,
    ) -> None:
        self._feature_store = feature_store
        self._config = config or RiskConfig()
        self._monitored_features = tuple(monitored_features) if monitored_features is not None else DEFAULT_MONITORED_FEATURES

        self._lock = threading.RLock()
        self._volatility_eval = VolatilityRiskEvaluator(self._config)
        self._conflict_eval = ConflictRiskEvaluator(self._config)
        self._invalidation_eval = InvalidationRiskEvaluator(self._config)
        self._regime_eval = RegimeQualityEvaluator(self._config)

        # Bounded LRU Cache: (symbol, timeframe, as_of_iso, price_str, feature_len) -> RiskAssessmentDTO
        self._memo_cache: OrderedDict[tuple[str, str, str, str, int], RiskAssessmentDTO] = OrderedDict()

    @property
    def feature_store(self) -> FeatureStore | None:
        return self._feature_store

    @property
    def config(self) -> RiskConfig:
        return self._config

    @property
    def max_cache_size(self) -> int:
        return self._config.max_cache_size

    @property
    def cache_size(self) -> int:
        with self._lock:
            return len(self._memo_cache)

    def clear_memo_cache(self) -> None:
        """Clear the LRU memoization cache."""
        with self._lock:
            self._memo_cache.clear()

    @staticmethod
    def _normalize_timeframe(tf: Timeframe | str) -> str:
        if isinstance(tf, Timeframe):
            return tf.value
        return str(tf)

    def compute_from_features(
        self,
        symbol: str,
        timeframe: Timeframe,
        timestamp: datetime,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
        upstream_assessment: Any | None = None,
        directional_intent: str | None = None,
        store_results: bool = False,
        ttl_seconds: float | None = None,
        store: FeatureStore | None = None,
    ) -> RiskAssessmentDTO:
        """Compute structured risk assessment directly from in-memory features deterministically."""
        if not symbol or not isinstance(symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        if not isinstance(timeframe, Timeframe):
            raise DTOValidationError(f"timeframe must be an instance of Timeframe, got {type(timeframe)}")
        validate_utc_datetime(timestamp, "timestamp")

        norm_sym = symbol.strip().upper()
        cfg = self._config

        # Incur price if missing from PremiumDiscountDTO
        ref_price = current_price
        if ref_price is None:
            pd = features.get("premium_discount")
            if isinstance(pd, PremiumDiscountDTO):
                ref_price = pd.current_price

        # Infer directional intent from upstream assessment if available
        intent = directional_intent
        if intent is None and upstream_assessment is not None:
            bias_attr = getattr(upstream_assessment, "directional_bias", None)
            if bias_attr:
                intent = getattr(bias_attr, "value", str(bias_attr))

        # 1. Volatility Risk Evaluation
        vol_regime, vol_score, vol_factors = self._volatility_eval.evaluate(
            features=features,
            current_price=ref_price,
        )

        # 2. Conflict Risk Evaluation
        conflict_ratio, conflict_score, conflict_factors = self._conflict_eval.evaluate(
            features=features,
            upstream_assessment=upstream_assessment,
        )

        # 3. Structural Invalidation & Dealing Range Evaluation
        inv_risk, inv_score, dr_score, inv_factors = self._invalidation_eval.evaluate(
            features=features,
            current_price=ref_price,
            directional_intent=intent,
        )

        # 4. Regime Quality, Chop, & Reversal Risk Evaluation
        regime_quality, chop_score, lr_score, regime_factors = self._regime_eval.evaluate(
            features=features,
            current_price=ref_price,
        )

        # 5. Composite Risk Score Synthesis
        # Inverted regime quality (lower quality = higher risk)
        inverted_quality_risk = (HUNDRED - regime_quality)
        raw_composite_score = (
            (cfg.weight_volatility_risk * vol_score)
            + (cfg.weight_conflict_risk * conflict_score)
            + (cfg.weight_invalidation_risk * inv_score)
            + (cfg.weight_regime_quality * inverted_quality_risk)
            + (cfg.weight_liquidity_reversal_risk * lr_score)
        )
        composite_score = max(ZERO, min(HUNDRED, raw_composite_score)).quantize(
            PRECISION_TWO, rounding=ROUND_HALF_UP
        )

        # 6. Composite Risk Level Classification
        # Escalate risk level if severe cross-discipline conflict or explosive volatility is detected
        if (
            composite_score >= cfg.risk_threshold_high
            or conflict_ratio >= Decimal("0.70")
            or vol_regime == VolatilityRegime.EXPLOSIVE
        ):
            risk_level = RiskLevel.EXTREME
        elif (
            composite_score >= cfg.risk_threshold_moderate
            or conflict_ratio >= Decimal("0.45")
            or vol_regime == VolatilityRegime.ELEVATED
        ):
            risk_level = RiskLevel.HIGH
        elif composite_score >= cfg.risk_threshold_low or conflict_ratio >= Decimal("0.20"):
            risk_level = RiskLevel.MODERATE
        else:
            risk_level = RiskLevel.LOW

        # 7. Regime Tradeability Verification
        is_tradeable = (
            (conflict_ratio <= cfg.max_tradeable_conflict_ratio)
            and (composite_score <= cfg.max_tradeable_risk_score)
            and (risk_level != RiskLevel.EXTREME)
        )

        # 8. Drawdown Risk Assessment
        if vol_score >= Decimal("80.00") or inv_score >= Decimal("80.00"):
            drawdown_risk = DrawdownRisk.SEVERE
        elif vol_score >= Decimal("55.00") or inv_score >= Decimal("55.00") or conflict_score >= Decimal("50.00"):
            drawdown_risk = DrawdownRisk.HIGH
        elif vol_score >= Decimal("35.00") or inv_score >= Decimal("35.00"):
            drawdown_risk = DrawdownRisk.MODERATE
        else:
            drawdown_risk = DrawdownRisk.LOW

        # 9. Capital Position Suitability Guidance (Analytical only)
        if not is_tradeable or risk_level == RiskLevel.EXTREME:
            position_suitability = PositionSuitability.UNSUITABLE_CASH_ONLY
        elif risk_level == RiskLevel.HIGH:
            position_suitability = PositionSuitability.DEFENSIVE_MINIMAL
        elif risk_level == RiskLevel.MODERATE:
            position_suitability = PositionSuitability.SELECTIVE_REDUCED
        else:
            position_suitability = PositionSuitability.FAVORABLE

        # Compile Granular Risk Factors
        all_factors = vol_factors + conflict_factors + inv_factors + regime_factors
        if not all_factors:
            all_factors.append("Orderly regime: Low volatility, aligned disciplines, and minimal structural friction")

        # 10. Explanatory Reasoning Construction
        reasoning = (
            f"=== INSTITUTIONAL RISK ASSESSMENT: {norm_sym} [{timeframe.value}] ===\n"
            f"Risk Level: {risk_level.value} (Score: {composite_score}/100) | Tradeable: {is_tradeable}\n"
            f"Volatility: {vol_regime.value} ({vol_score}/100) | Drawdown Risk: {drawdown_risk.value}\n"
            f"Signal Conflict: {conflict_ratio:.2f} ({conflict_score}/100) | Invalidation Proximity: {inv_risk.value} ({inv_score}/100)\n"
            f"Regime Quality: {regime_quality}/100 (Chop: {chop_score}/100) | Position Suitability: {position_suitability.value}\n"
            f"Key Friction Drivers: {'; '.join(all_factors[:3])}"
        )

        sub_metrics = RiskSubMetricsDTO(
            volatility_score=vol_score,
            conflict_score=conflict_score,
            dealing_range_score=dr_score,
            invalidation_score=inv_score,
            regime_quality_score=regime_quality,
            liquidity_reversal_score=lr_score,
            chop_score=chop_score,
        )

        dto = RiskAssessmentDTO(
            symbol=norm_sym,
            timeframe=timeframe,
            timestamp=timestamp,
            feature_name="risk_assessment",
            risk_level=risk_level,
            volatility_regime=vol_regime,
            regime_tradeable=is_tradeable,
            invalidation_risk=inv_risk,
            signal_conflict_ratio=conflict_ratio,
            drawdown_risk=drawdown_risk,
            regime_quality=regime_quality,
            position_suitability=position_suitability,
            risk_score=composite_score,
            sub_metrics=sub_metrics,
            risk_factors=tuple(all_factors),
            explanatory_reasoning=reasoning,
        )

        # Store back into FeatureStore if requested
        target_store = store or self._feature_store
        if store_results and target_store is not None:
            target_store.store_feature(dto, ttl_seconds=ttl_seconds)

        return dto

    def assess_risk(
        self,
        symbol: str,
        timeframe: Timeframe,
        as_of: datetime | None = None,
        current_price: Decimal | None = None,
        upstream_assessment: Any | None = None,
        directional_intent: str | None = None,
        store_results: bool = True,
        ttl_seconds: float | None = None,
        store: FeatureStore | None = None,
    ) -> RiskAssessmentDTO:
        """Query FeatureStore point-in-time features and produce institutional risk assessment."""
        target_store = store or self._feature_store
        if target_store is None:
            raise ValueError(
                "Cannot assess risk without a FeatureStore. Provide store in constructor or method argument."
            )

        if not symbol or not isinstance(symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        if not isinstance(timeframe, Timeframe):
            raise DTOValidationError(f"timeframe must be an instance of Timeframe, got {type(timeframe)}")

        norm_sym = symbol.strip().upper()
        norm_tf = self._normalize_timeframe(timeframe)

        with self._lock:
            # Query point-in-time features atomically
            features = target_store.get_batch(
                symbol=norm_sym,
                timeframe=timeframe,
                feature_names=self._monitored_features,
                as_of=as_of,
            )

            # Resolve effective timestamp
            if as_of is not None:
                validate_utc_datetime(as_of, "as_of")
                effective_ts = as_of
            elif features:
                effective_ts = max(f.timestamp for f in features.values())
            else:
                effective_ts = datetime.now(timezone.utc)

            # Check bounded LRU memo cache
            price_str = f"{current_price:.8f}" if current_price is not None else "NONE"
            intent_str = str(directional_intent) if directional_intent is not None else "AUTO"
            cache_key = (norm_sym, norm_tf, effective_ts.isoformat(), f"{price_str}:{intent_str}", len(features))
            cached = self._memo_cache.get(cache_key)
            if cached is not None:
                self._memo_cache.move_to_end(cache_key)
                return cached

            # Compute observation
            assessment = self.compute_from_features(
                symbol=norm_sym,
                timeframe=timeframe,
                timestamp=effective_ts,
                features=features,
                current_price=current_price,
                upstream_assessment=upstream_assessment,
                directional_intent=directional_intent,
                store_results=store_results,
                ttl_seconds=ttl_seconds,
                store=target_store,
            )

            # Evict oldest if capacity reached
            if len(self._memo_cache) >= self._config.max_cache_size:
                self._memo_cache.popitem(last=False)
            self._memo_cache[cache_key] = assessment
            return assessment

    def execute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO | None = None,
        as_of: datetime | None = None,
        store_results: bool = True,
        ttl_seconds: float | None = None,
        store: FeatureStore | None = None,
    ) -> Sequence[RiskAssessmentDTO]:
        """Execute risk computation over the latest candle in the series."""
        target_as_of = as_of
        current_price = None

        if data is not None and data.candles:
            last_c = data.candles[-1]
            if target_as_of is None:
                target_as_of = last_c.timestamp
            current_price = last_c.close

        dto = self.assess_risk(
            symbol=symbol,
            timeframe=timeframe,
            as_of=target_as_of,
            current_price=current_price,
            store_results=store_results,
            ttl_seconds=ttl_seconds,
            store=store,
        )
        return [dto]


class RiskComputer(FeatureComputer):
    """Adapter implementing FeatureComputer protocol for RiskEngine."""

    def __init__(self, risk_engine: RiskEngine | None = None) -> None:
        self._engine = risk_engine or RiskEngine()

    @property
    def feature_name(self) -> str:
        return "risk_assessment"

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        series: OHLCVSeriesDTO,
    ) -> Sequence[RiskAssessmentDTO]:
        return self._engine.execute(symbol=symbol, timeframe=timeframe, data=series, store_results=False)
