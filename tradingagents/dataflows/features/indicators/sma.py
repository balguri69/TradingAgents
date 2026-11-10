"""Simple Moving Average (SMA) deterministic computer."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import SMADTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series


class SMAComputer(FeatureComputer):
    """Linear-time Simple Moving Average (SMA) computer."""

    def __init__(self, period: int = 50, custom_name: str | None = None) -> None:
        if not isinstance(period, int) or period <= 0:
            raise DTOValidationError(f"period must be a positive integer, got {period}")
        self._period = period
        self._name = custom_name or f"SMA_{period}"

    @property
    def feature_name(self) -> str:
        return self._name

    @property
    def period(self) -> int:
        return self._period

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[SMADTO]:
        """Compute SMA observations using a single-pass O(N) sliding window."""
        validate_ohlcv_series(data, min_required=self._period)

        candles = data.candles
        dec_period = Decimal(self._period)
        results: list[SMADTO] = []

        # Initial window sum
        current_sum = sum(c.close for c in candles[: self._period])
        results.append(
            SMADTO(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=candles[self._period - 1].timestamp,
                feature_name=self._name,
                period=self._period,
                value=current_sum / dec_period,
            )
        )

        # Slide window across remainder in O(1) per step
        for idx in range(self._period, len(candles)):
            current_sum += candles[idx].close - candles[idx - self._period].close
            results.append(
                SMADTO(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candles[idx].timestamp,
                    feature_name=self._name,
                    period=self._period,
                    value=current_sum / dec_period,
                )
            )

        return results
