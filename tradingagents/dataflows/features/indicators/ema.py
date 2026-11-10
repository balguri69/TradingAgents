"""Exponential Moving Average (EMA) deterministic computer."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import EMADTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series


class EMAComputer(FeatureComputer):
    """Linear-time Exponential Moving Average (EMA) computer."""

    def __init__(self, period: int = 21, custom_name: str | None = None) -> None:
        if not isinstance(period, int) or period <= 0:
            raise DTOValidationError(f"period must be a positive integer, got {period}")
        self._period = period
        self._name = custom_name or f"EMA_{period}"
        # Multiplier k = 2 / (period + 1)
        self._multiplier = Decimal("2") / Decimal(period + 1)
        self._one_minus_k = Decimal("1") - self._multiplier

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
    ) -> Sequence[EMADTO]:
        """Compute EMA observations using single-pass O(N) recurrence."""
        validate_ohlcv_series(data, min_required=self._period)

        candles = data.candles
        dec_period = Decimal(self._period)
        results: list[EMADTO] = []

        # Seed EMA with SMA of first `period` candles
        current_ema = sum(c.close for c in candles[: self._period]) / dec_period
        results.append(
            EMADTO(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=candles[self._period - 1].timestamp,
                feature_name=self._name,
                period=self._period,
                value=current_ema,
            )
        )

        # Apply exponential recurrence across subsequent candles
        for idx in range(self._period, len(candles)):
            current_ema = (candles[idx].close * self._multiplier) + (current_ema * self._one_minus_k)
            results.append(
                EMADTO(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candles[idx].timestamp,
                    feature_name=self._name,
                    period=self._period,
                    value=current_ema,
                )
            )

        return results
