"""Thread-safe indicator computation and orchestration engine."""

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
from tradingagents.dataflows.features.indicators.atr import ATRComputer
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series
from tradingagents.dataflows.features.indicators.bollinger import BollingerBandsComputer
from tradingagents.dataflows.features.indicators.ema import EMAComputer
from tradingagents.dataflows.features.indicators.macd import MACDComputer
from tradingagents.dataflows.features.indicators.rsi import RSIComputer
from tradingagents.dataflows.features.indicators.sma import SMAComputer
from tradingagents.dataflows.features.indicators.volume_profile import VolumeProfileComputer
from tradingagents.dataflows.features.indicators.vwap import VWAPComputer


class IndicatorEngine:
    """Thread-safe orchestration engine for deterministic technical indicator calculation."""

    def __init__(
        self,
        feature_store: FeatureStore | None = None,
        register_defaults: bool = True,
    ) -> None:
        """Initialize the indicator engine.

        Args:
            feature_store: Optional FeatureStore instance where calculated features are written.
            register_defaults: When True, registers default institutional indicator computers.
        """
        self._feature_store = feature_store
        self._lock = threading.RLock()
        self._computers: dict[str, FeatureComputer] = {}

        # Cache to prevent duplicate computations:
        # Key: (symbol, timeframe_val, feature_name, len_candles, last_timestamp, last_close)
        # Value: tuple of BaseFeatureDTO
        self._memo_cache: dict[tuple[str, str, str, int, datetime, Decimal], tuple[BaseFeatureDTO, ...]] = {}

        if register_defaults:
            self._register_default_computers()

    def _register_default_computers(self) -> None:
        """Register the baseline suite of institutional technical indicator computers."""
        defaults: list[FeatureComputer] = [
            SMAComputer(period=20),
            SMAComputer(period=50),
            EMAComputer(period=9),
            EMAComputer(period=21),
            RSIComputer(period=14),
            ATRComputer(period=14),
            MACDComputer(fast_period=12, slow_period=26, signal_period=9),
            BollingerBandsComputer(period=20, num_std_dev=Decimal("2.0")),
            VWAPComputer(reset_daily=False),
            VolumeProfileComputer(num_bins=24, value_area_pct=Decimal("0.70")),
        ]
        for comp in defaults:
            self.register_computer(comp)

    def register_computer(self, computer: FeatureComputer) -> None:
        """Register a FeatureComputer instance."""
        if not isinstance(computer, FeatureComputer):
            raise DTOValidationError(f"Expected FeatureComputer instance, got {type(computer)}")
        with self._lock:
            self._computers[computer.feature_name] = computer

    def unregister_computer(self, feature_name: str) -> bool:
        """Remove a computer by feature name."""
        with self._lock:
            removed = self._computers.pop(feature_name, None)
            return removed is not None

    def get_computer(self, feature_name: str) -> FeatureComputer | None:
        """Retrieve a registered computer by feature name."""
        with self._lock:
            return self._computers.get(feature_name)

    def list_computers(self) -> list[str]:
        """Return list of all registered feature computer names."""
        with self._lock:
            return sorted(list(self._computers.keys()))

    def clear_memo_cache(self) -> None:
        """Clear the duplicate computation prevention cache."""
        with self._lock:
            self._memo_cache.clear()

    @staticmethod
    def _make_input_signature(
        symbol: str,
        timeframe: Timeframe,
        feature_name: str,
        data: OHLCVSeriesDTO,
    ) -> tuple[str, str, str, int, datetime, Decimal]:
        """Generate fingerprint of calculation input to avoid redundant recomputations."""
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
        """Execute a single registered indicator computer."""
        validate_ohlcv_series(data, min_required=1)

        with self._lock:
            computer = self._computers.get(feature_name)
            if computer is None:
                raise ValueError(
                    f"No computer registered for feature '{feature_name}'. "
                    f"Available: {self.list_computers()}"
                )

            # Check duplicate computation cache
            sig = self._make_input_signature(symbol, timeframe, feature_name, data)
            cached_result = self._memo_cache.get(sig)
            if cached_result is not None:
                features = list(cached_result)
            else:
                features = list(computer.compute(symbol, timeframe, data))
                self._memo_cache[sig] = tuple(features)

            # Direct storage into FeatureStore
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
        """Execute multiple designated indicators sequentially under engine coordination."""
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
        """Execute all registered indicator computers over the provided series."""
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
