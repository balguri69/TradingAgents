"""Structural contracts for feature computation and feature storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, Sequence, runtime_checkable

from tradingagents.dataflows.dto.features import BaseFeatureDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe


@runtime_checkable
class FeatureComputer(Protocol):
    """Pure deterministic computer protocol producing immutable feature DTOs.
    
    Invariants:
    - Pure computation (no side effects, no I/O, no network calls).
    - Accepts standardized market DTOs (e.g., OHLCVSeriesDTO).
    - Produces strongly typed BaseFeatureDTO instances.
    - Zero future leakage: output timestamp strictly corresponds to the latest available input candle.
    """

    @property
    def feature_name(self) -> str:
        """Identifier or namespace of the feature produced by this computer."""
        ...

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[BaseFeatureDTO]:
        """Compute feature observations over input market data."""
        ...


@runtime_checkable
class FeatureStore(Protocol):
    """Thread-safe, high-performance in-memory Feature Store protocol."""

    def store_feature(
        self,
        feature: BaseFeatureDTO,
        ttl_seconds: float | None = None,
    ) -> None:
        """Store a single immutable feature observation."""
        ...

    def store_features(
        self,
        features: Sequence[BaseFeatureDTO],
        ttl_seconds: float | None = None,
    ) -> int:
        """Atomically store a batch of immutable feature observations."""
        ...

    def get_latest(
        self,
        symbol: str,
        timeframe: Timeframe,
        feature_name: str,
    ) -> BaseFeatureDTO | None:
        """Retrieve the most recent observation for a given series ($O(1)$)."""
        ...

    def get_as_of(
        self,
        symbol: str,
        timeframe: Timeframe,
        feature_name: str,
        as_of: datetime,
    ) -> BaseFeatureDTO | None:
        """Retrieve the latest observation where timestamp <= as_of (zero future leakage)."""
        ...

    def get_batch(
        self,
        symbol: str,
        timeframe: Timeframe,
        feature_names: Sequence[str],
        as_of: datetime | None = None,
    ) -> dict[str, BaseFeatureDTO]:
        """Retrieve multiple features for a symbol/timeframe in a single atomic snapshot."""
        ...

    def invalidate(
        self,
        symbol: str | None = None,
        timeframe: Timeframe | None = None,
        feature_name: str | None = None,
    ) -> int:
        """Invalidate cached entries matching the specified filter criteria."""
        ...

    def purge_expired(self) -> int:
        """Purge all entries whose TTL has elapsed."""
        ...
