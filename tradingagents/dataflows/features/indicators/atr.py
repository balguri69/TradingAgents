"""Average True Range (ATR) deterministic computer using Wilder's smoothing."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import ATRDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series


class ATRComputer(FeatureComputer):
    """Linear-time Average True Range (ATR) computer."""

    def __init__(self, period: int = 14, custom_name: str | None = None) -> None:
        if not isinstance(period, int) or period <= 0:
            raise DTOValidationError(f"period must be a positive integer, got {period}")
        self._period = period
        self._name = custom_name or f"ATR_{period}"

    @property
    def feature_name(self) -> str:
        return self._name

    @property
    def period(self) -> int:
        return self._period

    @staticmethod
    def _compute_tr(high: Decimal, low: Decimal, prev_close: Decimal | None) -> Decimal:
        """Compute True Range (TR)."""
        hl = high - low
        if prev_close is None:
            return hl
        hc = abs(high - prev_close)
        lc = abs(low - prev_close)
        return max(hl, hc, lc)

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[ATRDTO]:
        """Compute ATR observations using Wilder's smoothed TR in O(N)."""
        validate_ohlcv_series(data, min_required=self._period)

        candles = data.candles
        dec_period = Decimal(self._period)
        dec_period_minus_one = Decimal(self._period - 1)
        results: list[ATRDTO] = []

        # 1. Compute True Ranges for initial seed window
        tr_list: list[Decimal] = []
        for i in range(self._period):
            prev_close = candles[i - 1].close if i > 0 else None
            tr_list.append(self._compute_tr(candles[i].high, candles[i].low, prev_close))

        current_atr = sum(tr_list) / dec_period
        results.append(
            ATRDTO(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=candles[self._period - 1].timestamp,
                feature_name=self._name,
                period=self._period,
                value=current_atr,
            )
        )

        # 2. Iterate across remaining candles with Wilder's recurrence
        for i in range(self._period, len(candles)):
            tr = self._compute_tr(candles[i].high, candles[i].low, candles[i - 1].close)
            current_atr = (current_atr * dec_period_minus_one + tr) / dec_period
            results.append(
                ATRDTO(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candles[i].timestamp,
                    feature_name=self._name,
                    period=self._period,
                    value=current_atr,
                )
            )

        return results
