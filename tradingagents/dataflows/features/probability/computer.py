"""FeatureComputer implementation for the Probability Engine."""

from __future__ import annotations

from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer, FeatureStore
from tradingagents.dataflows.dto.features import BaseFeatureDTO, ProbabilityDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.features.probability.config import ScoringConfig
from tradingagents.dataflows.features.probability.engine import ProbabilityEngine


class ProbabilityComputer(FeatureComputer):
    """Computer adapter conforming to FeatureComputer protocol for orchestrators."""

    def __init__(
        self,
        feature_store: FeatureStore,
        config: ScoringConfig | None = None,
        feature_name: str = "probability",
    ) -> None:
        """Initialize ProbabilityComputer.

        Args:
            feature_store: FeatureStore instance to consume features from.
            config: Optional ScoringConfig.
            feature_name: Namespace identifier (default: "probability").
        """
        self._feature_store = feature_store
        self._config = config or ScoringConfig()
        self._feature_name = feature_name
        self._engine = ProbabilityEngine(feature_store=feature_store, config=self._config)

    @property
    def feature_name(self) -> str:
        return self._feature_name

    @property
    def engine(self) -> ProbabilityEngine:
        return self._engine

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[ProbabilityDTO]:
        """Compute directional probability observation for current market state."""
        as_of = kwargs.get("as_of")
        current_price = kwargs.get("current_price")
        store_results = kwargs.get("store_results", False)
        ttl_seconds = kwargs.get("ttl_seconds")

        return self._engine.execute(
            symbol=symbol,
            timeframe=timeframe,
            data=data,
            as_of=as_of,
            store_results=store_results,
            ttl_seconds=ttl_seconds,
        )
