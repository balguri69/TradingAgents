"""Institutional Market Structure Engine (Smart Money Concepts)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import threading
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer, FeatureStore
from tradingagents.dataflows.dto.features import BaseFeatureDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series
from tradingagents.dataflows.features.structure.bos import BreakOfStructureComputer
from tradingagents.dataflows.features.structure.choch import ChangeOfCharacterComputer
from tradingagents.dataflows.features.structure.fvg import FairValueGapComputer
from tradingagents.dataflows.features.structure.liquidity import (
    LiquidityPoolComputer,
    LiquiditySweepComputer,
)
from tradingagents.dataflows.features.structure.order_blocks import OrderBlockComputer
from tradingagents.dataflows.features.structure.premium_discount import (
    PremiumDiscountComputer,
)
from tradingagents.dataflows.features.structure.swings import SwingComputer


class MarketStructureEngine:
    """Thread-safe orchestration engine for Smart Money Concepts and market structure analysis."""

    def __init__(
        self,
        feature_store: FeatureStore | None = None,
        register_defaults: bool = True,
    ) -> None:
        """Initialize the Market Structure engine.

        Args:
            feature_store: Optional FeatureStore where computed structure features are persisted.
            register_defaults: When True, registers default SMC computers.
        """
        self._feature_store = feature_store
        self._lock = threading.RLock()
        self._computers: dict[str, FeatureComputer] = {}

        # Deduplication memoization cache:
        # Key: (symbol, timeframe_val, feature_name, candle_count, last_timestamp, last_close)
        self._memo_cache: dict[tuple[str, str, str, int, datetime, Decimal], tuple[BaseFeatureDTO, ...]] = {}

        if register_defaults:
            self._register_default_computers()

    def _register_default_computers(self) -> None:
        """Register the baseline suite of Smart Money Concepts structural computers."""
        defaults: list[FeatureComputer] = [
            SwingComputer(left_bars=2, right_bars=2, is_major=False),  # Internal structure
            SwingComputer(left_bars=5, right_bars=5, is_major=True),   # External structure
            FairValueGapComputer(min_gap_bps=Decimal("0.0")),
            BreakOfStructureComputer(left_bars=2, right_bars=2),
            ChangeOfCharacterComputer(left_bars=2, right_bars=2),
            OrderBlockComputer(volume_threshold=Decimal("1.2"), lookback_avg=5),
            LiquidityPoolComputer(left_bars=2, right_bars=2, tolerance_bps=Decimal("10.0")),
            LiquiditySweepComputer(left_bars=2, right_bars=2),
            PremiumDiscountComputer(lookback_period=20),
        ]
        for comp in defaults:
            self.register_computer(comp)

    def register_computer(self, computer: FeatureComputer) -> None:
        """Register a structural FeatureComputer instance."""
        if not isinstance(computer, FeatureComputer):
            raise DTOValidationError(f"Expected FeatureComputer instance, got {type(computer)}")
        with self._lock:
            self._computers[computer.feature_name] = computer

    def unregister_computer(self, feature_name: str) -> bool:
        """Unregister a computer by feature name."""
        with self._lock:
            removed = self._computers.pop(feature_name, None)
            return removed is not None

    def get_computer(self, feature_name: str) -> FeatureComputer | None:
        """Retrieve registered computer by name."""
        with self._lock:
            return self._computers.get(feature_name)

    def list_computers(self) -> list[str]:
        """Return list of all registered structural computer names."""
        with self._lock:
            return sorted(list(self._computers.keys()))

    def clear_memo_cache(self) -> None:
        """Clear calculation deduplication cache."""
        with self._lock:
            self._memo_cache.clear()

    @staticmethod
    def _make_input_signature(
        symbol: str,
        timeframe: Timeframe,
        feature_name: str,
        data: OHLCVSeriesDTO,
    ) -> tuple[str, str, str, int, datetime, Decimal]:
        """Generate deterministic fingerprint of input series."""
        candles = data.candles
        last_candle = candles[-1]
        tf_str = timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)
        return (
            symbol.strip().upper(),
            tf_str,
            feature_name.strip(),
            len(candles),
            last_candle.timestamp,
            last_candle.close,
        )

    def execute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        feature_name: str,
        store_results: bool = True,
        ttl_seconds: float | None = None,
        store: FeatureStore | None = None,
    ) -> Sequence[BaseFeatureDTO]:
        """Execute a single structural computer and optionally persist results to FeatureStore."""
        validate_ohlcv_series(data, min_required=1)

        with self._lock:
            computer = self._computers.get(feature_name)
            if computer is None:
                raise ValueError(
                    f"No structural computer registered for feature '{feature_name}'. "
                    f"Available: {self.list_computers()}"
                )

            # Deduplication cache lookup
            sig = self._make_input_signature(symbol, timeframe, feature_name, data)
            cached_result = self._memo_cache.get(sig)
            if cached_result is not None:
                features = list(cached_result)
            else:
                features = list(computer.compute(symbol, timeframe, data))
                self._memo_cache[sig] = tuple(features)

            # Persist to FeatureStore
            target_store = store or self._feature_store
            if store_results and target_store is not None and features:
                target_store.store_features(features, ttl_seconds=ttl_seconds)

            return features

    def execute_batch(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        feature_names: Sequence[str],
        store_results: bool = True,
        ttl_seconds: float | None = None,
        store: FeatureStore | None = None,
    ) -> dict[str, Sequence[BaseFeatureDTO]]:
        """Execute specified structural computers under engine orchestration."""
        validate_ohlcv_series(data, min_required=1)
        results: dict[str, Sequence[BaseFeatureDTO]] = {}

        with self._lock:
            for name in feature_names:
                results[name] = self.execute(
                    symbol=symbol,
                    timeframe=timeframe,
                    data=data,
                    feature_name=name,
                    store_results=store_results,
                    ttl_seconds=ttl_seconds,
                    store=store,
                )
        return results

    def execute_all(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        store_results: bool = True,
        ttl_seconds: float | None = None,
        store: FeatureStore | None = None,
    ) -> dict[str, Sequence[BaseFeatureDTO]]:
        """Execute all registered market structure computers over the series."""
        with self._lock:
            all_names = list(self._computers.keys())
            return self.execute_batch(
                symbol=symbol,
                timeframe=timeframe,
                data=data,
                feature_names=all_names,
                store_results=store_results,
                ttl_seconds=ttl_seconds,
                store=store,
            )
