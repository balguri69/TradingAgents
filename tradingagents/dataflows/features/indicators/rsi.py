"""Relative Strength Index (RSI) deterministic computer using Wilder's smoothing."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import RSIDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series


class RSIComputer(FeatureComputer):
    """Linear-time Relative Strength Index (RSI) computer."""

    def __init__(self, period: int = 14, custom_name: str | None = None) -> None:
        if not isinstance(period, int) or period <= 0:
            raise DTOValidationError(f"period must be a positive integer, got {period}")
        self._period = period
        self._name = custom_name or f"RSI_{period}"

    @property
    def feature_name(self) -> str:
        return self._name

    @property
    def period(self) -> int:
        return self._period

    @staticmethod
    def _compute_rsi_value(avg_gain: Decimal, avg_loss: Decimal) -> Decimal:
        """Calculate RSI from average gain and loss, handling zero division."""
        if avg_loss == Decimal("0"):
            if avg_gain == Decimal("0"):
                return Decimal("50.0")
            return Decimal("100.0")
        if avg_gain == Decimal("0"):
            return Decimal("0.0")

        rs = avg_gain / avg_loss
        rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))
        # Ensure within [0, 100] due to precision limits
        if rsi < Decimal("0"):
            return Decimal("0")
        if rsi > Decimal("100"):
            return Decimal("100")
        return rsi

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[RSIDTO]:
        """Compute RSI observations using Wilder's smoothed averages in O(N)."""
        validate_ohlcv_series(data, min_required=self._period + 1)

        candles = data.candles
        dec_period = Decimal(self._period)
        dec_period_minus_one = Decimal(self._period - 1)
        results: list[RSIDTO] = []

        # Initial seed: simple average of first `period` price changes
        sum_gain = Decimal("0")
        sum_loss = Decimal("0")
        for i in range(1, self._period + 1):
            delta = candles[i].close - candles[i - 1].close
            if delta > Decimal("0"):
                sum_gain += delta
            else:
                sum_loss += (-delta)

        avg_gain = sum_gain / dec_period
        avg_loss = sum_loss / dec_period

        first_rsi = self._compute_rsi_value(avg_gain, avg_loss)
        results.append(
            RSIDTO(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=candles[self._period].timestamp,
                feature_name=self._name,
                period=self._period,
                value=first_rsi,
            )
        )

        # Subsequent observations using Wilder's smoothing
        for i in range(self._period + 1, len(candles)):
            delta = candles[i].close - candles[i - 1].close
            gain = delta if delta > Decimal("0") else Decimal("0")
            loss = (-delta) if delta < Decimal("0") else Decimal("0")

            avg_gain = (avg_gain * dec_period_minus_one + gain) / dec_period
            avg_loss = (avg_loss * dec_period_minus_one + loss) / dec_period

            rsi = self._compute_rsi_value(avg_gain, avg_loss)
            results.append(
                RSIDTO(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candles[i].timestamp,
                    feature_name=self._name,
                    period=self._period,
                    value=rsi,
                )
            )

        return results
