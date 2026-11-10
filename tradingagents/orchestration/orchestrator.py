"""Thread-safe, deterministic Multi-Agent Orchestrator for institutional market assessment."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from decimal import Decimal
import threading
from typing import Any, Mapping, Sequence

from tradingagents.dataflows.contracts.features import FeatureStore
from tradingagents.dataflows.dto.features import (
    BaseFeatureDTO,
    PremiumDiscountDTO,
)
from tradingagents.dataflows.dto.validation import validate_utc_datetime
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.orchestration.agents import (
    ConfidenceEvidenceAgent,
    FinalSynthesisAgent,
    MarketStructureAgent,
    ProbabilityAgent,
    RiskContextAgent,
    TechnicalAnalysisAgent,
)
from tradingagents.orchestration.dto import MarketAssessmentDTO
from tradingagents.orchestration.protocols import MarketOrchestrator

DEFAULT_MONITORED_FEATURES = (
    "bos", "BOS",
    "choch", "CHOCH",
    "order_block", "ORDER_BLOCK",
    "liquidity_sweep", "LIQUIDITY_SWEEP",
    "premium_discount", "PREMIUM_DISCOUNT", "PREMIUM_DISCOUNT_20",
    "fvg", "FVG",
    "swing_high", "SWING_HIGH", "swing_low", "SWING_LOW",
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


class MultiAgentOrchestrator:
    """Thread-safe deterministic orchestrator coordinating specialized analytical agents.
    
    Adheres strictly to Phase 10 constraints:
    - Zero trade execution, zero order generation, zero stop/take-profit artifacts.
    - Standard library only, no external ML/AI in the core decision path.
    - Bounded LRU memoization with quantized price awareness to prevent memory leaks.
    """

    def __init__(
        self,
        feature_store: FeatureStore | None = None,
        technical_agent: TechnicalAnalysisAgent | None = None,
        structure_agent: MarketStructureAgent | None = None,
        probability_agent: ProbabilityAgent | None = None,
        risk_agent: RiskContextAgent | None = None,
        confidence_agent: ConfidenceEvidenceAgent | None = None,
        synthesis_agent: FinalSynthesisAgent | None = None,
        monitored_features: Sequence[str] | None = None,
        max_cache_size: int = 10000,
    ) -> None:
        if max_cache_size <= 0:
            raise ValueError(f"max_cache_size must be positive, got {max_cache_size}")

        self._feature_store = feature_store
        self._max_cache_size = max_cache_size
        self._monitored_features = tuple(monitored_features) if monitored_features is not None else DEFAULT_MONITORED_FEATURES

        self._lock = threading.RLock()
        self._technical_agent = technical_agent or TechnicalAnalysisAgent()
        self._structure_agent = structure_agent or MarketStructureAgent()
        self._probability_agent = probability_agent or ProbabilityAgent()
        self._risk_agent = risk_agent or RiskContextAgent()
        self._confidence_agent = confidence_agent or ConfidenceEvidenceAgent()
        self._synthesis_agent = synthesis_agent or FinalSynthesisAgent()

        # Bounded LRU Cache: (symbol, timeframe, as_of_iso, price_str, feature_len) -> MarketAssessmentDTO
        self._memo_cache: OrderedDict[tuple[str, str, str, str, int], MarketAssessmentDTO] = OrderedDict()

    @property
    def feature_store(self) -> FeatureStore | None:
        return self._feature_store

    @property
    def max_cache_size(self) -> int:
        return self._max_cache_size

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

    def assess_from_features(
        self,
        symbol: str,
        timeframe: Timeframe,
        timestamp: datetime,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
    ) -> MarketAssessmentDTO:
        """Assess directly from an in-memory feature mapping deterministically."""
        if not symbol or not isinstance(symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        if not isinstance(timeframe, Timeframe):
            raise DTOValidationError(f"timeframe must be an instance of Timeframe, got {type(timeframe)}")
        validate_utc_datetime(timestamp, "timestamp")

        norm_sym = symbol.strip().upper()

        # Resolve price reference if missing from PremiumDiscountDTO
        ref_price = current_price
        if ref_price is None:
            pd = features.get("premium_discount")
            if isinstance(pd, PremiumDiscountDTO):
                ref_price = pd.current_price

        # 1. Technical Analysis Agent Execution
        tech_assessment = self._technical_agent.analyze(
            symbol=norm_sym,
            timeframe=timeframe,
            features=features,
            current_price=ref_price,
            as_of=timestamp,
        )

        # 2. Market Structure Agent Execution
        structure_assessment = self._structure_agent.analyze(
            symbol=norm_sym,
            timeframe=timeframe,
            features=features,
            current_price=ref_price,
            as_of=timestamp,
        )

        # 3. Probability Agent Execution
        probability_assessment = self._probability_agent.analyze(
            symbol=norm_sym,
            timeframe=timeframe,
            features=features,
            current_price=ref_price,
            as_of=timestamp,
        )

        # 4. Risk Context Agent Execution
        risk_assessment = self._risk_agent.analyze(
            symbol=norm_sym,
            timeframe=timeframe,
            features=features,
            current_price=ref_price,
            as_of=timestamp,
            technical_assessment=tech_assessment,
            structure_assessment=structure_assessment,
        )

        # 5. Confidence & Evidence Agent Execution
        confidence_assessment = self._confidence_agent.analyze(
            symbol=norm_sym,
            timeframe=timeframe,
            features=features,
            current_price=ref_price,
            as_of=timestamp,
            technical_assessment=tech_assessment,
            structure_assessment=structure_assessment,
            probability_assessment=probability_assessment,
            risk_assessment=risk_assessment,
        )

        # 6. Final Synthesis Agent Execution
        final_assessment = self._synthesis_agent.analyze(
            symbol=norm_sym,
            timeframe=timeframe,
            features=features,
            current_price=ref_price,
            as_of=timestamp,
            technical_assessment=tech_assessment,
            structure_assessment=structure_assessment,
            probability_assessment=probability_assessment,
            risk_assessment=risk_assessment,
            confidence_assessment=confidence_assessment,
        )

        return final_assessment

    def assess(
        self,
        symbol: str,
        timeframe: Timeframe,
        as_of: datetime | None = None,
        current_price: Decimal | None = None,
        store: FeatureStore | None = None,
    ) -> MarketAssessmentDTO:
        """Query FeatureStore point-in-time features and produce unified market assessment."""
        target_store = store or self._feature_store
        if target_store is None:
            raise ValueError(
                "Cannot assess without a FeatureStore. Provide store in constructor or method argument."
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
            cache_key = (norm_sym, norm_tf, effective_ts.isoformat(), price_str, len(features))
            cached = self._memo_cache.get(cache_key)
            if cached is not None:
                self._memo_cache.move_to_end(cache_key)
                return cached

            # Compute observation
            assessment = self.assess_from_features(
                symbol=norm_sym,
                timeframe=timeframe,
                timestamp=effective_ts,
                features=features,
                current_price=current_price,
            )

            # Evict oldest if capacity reached
            if len(self._memo_cache) >= self._max_cache_size:
                self._memo_cache.popitem(last=False)
            self._memo_cache[cache_key] = assessment
            return assessment
