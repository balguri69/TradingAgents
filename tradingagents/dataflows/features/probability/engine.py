"""Thread-safe orchestration engine for quantitative probability estimation."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from decimal import Decimal
import threading
from typing import Any, Mapping, Sequence

from tradingagents.dataflows.contracts.features import FeatureStore
from tradingagents.dataflows.dto.features import (
    BaseFeatureDTO,
    FeatureContributionDTO,
    PremiumDiscountDTO,
    ProbabilityDTO,
)
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.dto.validation import validate_utc_datetime
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.probability.confidence import ConfidenceCalculator
from tradingagents.dataflows.features.probability.config import ScoringConfig
from tradingagents.dataflows.features.probability.explainer import ExplanationBuilder
from tradingagents.dataflows.features.probability.normalizer import ScoreNormalizer
from tradingagents.dataflows.features.probability.scorer import ProbabilityScorer

DEFAULT_FEATURE_NAMES = (
    "bos",
    "BOS",
    "choch",
    "CHOCH",
    "order_block",
    "ORDER_BLOCK",
    "liquidity_sweep",
    "LIQUIDITY_SWEEP",
    "premium_discount",
    "PREMIUM_DISCOUNT",
    "PREMIUM_DISCOUNT_20",
    "fvg",
    "FVG",
    "ema_9",
    "EMA_9",
    "ema_21",
    "EMA_21",
    "sma_20",
    "SMA_20",
    "sma_50",
    "SMA_50",
    "rsi_14",
    "RSI_14",
    "rsi",
    "RSI",
    "macd",
    "MACD",
    "MACD_12_26_9",
    "vwap",
    "VWAP",
    "bollinger",
    "BOLLINGER",
    "BB_20_2.0",
    "volume_profile",
    "VOLUME_PROFILE",
    "VP_24_70",
    "atr_14",
    "ATR_14",
    "atr",
    "ATR",
)


class ProbabilityEngine:
    """Thread-safe orchestration engine producing deterministic directional probabilities."""

    def __init__(
        self,
        feature_store: FeatureStore | None = None,
        config: ScoringConfig | None = None,
        monitored_features: Sequence[str] | None = None,
    ) -> None:
        """Initialize the probability engine.

        Args:
            feature_store: Optional FeatureStore instance for feature retrieval and output persistence.
            config: Optional ScoringConfig defining weights and thresholds.
            monitored_features: Optional sequence of feature names to query from the store.
        """
        self._feature_store = feature_store
        self._config = config or ScoringConfig()
        self._monitored_features = tuple(monitored_features) if monitored_features is not None else DEFAULT_FEATURE_NAMES

        self._lock = threading.RLock()
        self._scorer = ProbabilityScorer(self._config)
        self._normalizer = ScoreNormalizer(self._config)
        self._confidence_calc = ConfidenceCalculator(self._config)
        self._explainer = ExplanationBuilder()

        # Bounded LRU memoization cache:
        # Key: (symbol, timeframe_val, as_of_iso, price_str, features_len) -> ProbabilityDTO
        self._memo_cache: OrderedDict[tuple[str, str, str, str, int], ProbabilityDTO] = OrderedDict()

    @property
    def feature_store(self) -> FeatureStore | None:
        return self._feature_store

    @property
    def config(self) -> ScoringConfig:
        return self._config

    @property
    def max_cache_size(self) -> int:
        return self._config.max_cache_size

    @property
    def cache_size(self) -> int:
        with self._lock:
            return len(self._memo_cache)

    def clear_memo_cache(self) -> None:
        """Clear the memoization cache."""
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
        store_results: bool = False,
        ttl_seconds: float | None = None,
        store: FeatureStore | None = None,
    ) -> ProbabilityDTO:
        """Compute probability distribution directly from a provided feature mapping."""
        if not symbol or not isinstance(symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        if not isinstance(timeframe, Timeframe):
            raise DTOValidationError(f"timeframe must be an instance of Timeframe, got {type(timeframe)}")
        validate_utc_datetime(timestamp, "timestamp")

        norm_sym = symbol.strip().upper()

        # Incur price if missing from PremiumDiscountDTO or other features
        ref_price = current_price
        if ref_price is None:
            pd = features.get("premium_discount")
            if isinstance(pd, PremiumDiscountDTO):
                ref_price = pd.current_price

        # 1. Deterministic Scoring
        bullish_score, bearish_score, contributions, pos_factors, neg_factors = self._scorer.score(
            features=features,
            current_price=ref_price,
            as_of=timestamp,
            timeframe=timeframe,
        )
        total_score = bullish_score - bearish_score

        # 2. Probability Normalization
        bull_prob, bear_prob, neutral_prob = self._normalizer.normalize(
            bullish_score=bullish_score,
            bearish_score=bearish_score,
        )

        # 3. Confidence Calculation
        confidence = self._confidence_calc.calculate(
            contributions=contributions,
            bullish_score=bullish_score,
            bearish_score=bearish_score,
        )

        # 4. Human-Readable Reasoning
        reasoning = self._explainer.build_reasoning(
            bullish_prob=bull_prob,
            bearish_prob=bear_prob,
            neutral_prob=neutral_prob,
            confidence=confidence,
            total_score=total_score,
            bullish_score=bullish_score,
            bearish_score=bearish_score,
            positive_factors=pos_factors,
            negative_factors=neg_factors,
            contributions=contributions,
        )

        # 5. Immutable DTO Construction
        dto = ProbabilityDTO(
            symbol=norm_sym,
            timeframe=timeframe,
            timestamp=timestamp,
            feature_name="probability",
            bullish_probability=bull_prob,
            bearish_probability=bear_prob,
            neutral_probability=neutral_prob,
            confidence=confidence,
            total_score=total_score,
            bullish_score=bullish_score,
            bearish_score=bearish_score,
            contributing_features=contributions,
            positive_factors=pos_factors,
            negative_factors=neg_factors,
            reasoning=reasoning,
        )

        # 6. Optional FeatureStore Persistence
        target_store = store or self._feature_store
        if store_results and target_store is not None:
            target_store.store_feature(dto, ttl_seconds=ttl_seconds)

        return dto

    def compute_probability(
        self,
        symbol: str,
        timeframe: Timeframe,
        as_of: datetime | None = None,
        current_price: Decimal | None = None,
        store_results: bool = True,
        ttl_seconds: float | None = None,
        store: FeatureStore | None = None,
    ) -> ProbabilityDTO:
        """Compute directional probabilities by querying features from the FeatureStore as of a point-in-time."""
        target_store = store or self._feature_store
        if target_store is None:
            raise ValueError(
                "Cannot compute probability without a FeatureStore. Provide store in constructor or argument."
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
            prob_dto = self.compute_from_features(
                symbol=norm_sym,
                timeframe=timeframe,
                timestamp=effective_ts,
                features=features,
                current_price=current_price,
                store_results=store_results,
                ttl_seconds=ttl_seconds,
                store=target_store,
            )

            # Evict oldest if capacity reached
            if len(self._memo_cache) >= self._config.max_cache_size:
                self._memo_cache.popitem(last=False)
            self._memo_cache[cache_key] = prob_dto
            return prob_dto

    def execute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO | None = None,
        as_of: datetime | None = None,
        store_results: bool = True,
        ttl_seconds: float | None = None,
        store: FeatureStore | None = None,
    ) -> Sequence[ProbabilityDTO]:
        """Execute probability computation over the latest candle in the series."""
        target_as_of = as_of
        current_price = None

        if data is not None and data.candles:
            last_c = data.candles[-1]
            if target_as_of is None:
                target_as_of = last_c.timestamp
            current_price = last_c.close

        dto = self.compute_probability(
            symbol=symbol,
            timeframe=timeframe,
            as_of=target_as_of,
            current_price=current_price,
            store_results=store_results,
            ttl_seconds=ttl_seconds,
            store=store,
        )
        return [dto]
