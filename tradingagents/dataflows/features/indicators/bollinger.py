"""Bollinger Bands deterministic computer."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import BollingerBandsDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series


class BollingerBandsComputer(FeatureComputer):
    """Bollinger Bands volatility boundaries computer using pure Decimal precision."""

    def __init__(
        self,
        period: int = 20,
        num_std_dev: Decimal | float = Decimal("2.0"),
        custom_name: str | None = None,
    ) -> None:
        if not isinstance(period, int) or period <= 0:
            raise DTOValidationError(f"period must be a positive integer, got {period}")
        dec_std = Decimal(str(num_std_dev))
        if dec_std <= Decimal("0"):
            raise DTOValidationError(f"num_std_dev must be positive, got {num_std_dev}")

        self._period = period
        self._num_std_dev = dec_std
        self._name = custom_name or f"BB_{period}_{num_std_dev}"

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
    ) -> Sequence[BollingerBandsDTO]:
        """Compute middle band, upper band, lower band, and bandwidth."""
        validate_ohlcv_series(data, min_required=self._period)

        candles = data.candles
        dec_period = Decimal(self._period)
        results: list[BollingerBandsDTO] = []

        # Sliding window calculation
        for idx in range(self._period - 1, len(candles)):
            window = candles[idx - self._period + 1 : idx + 1]
            middle_band = sum(c.close for c in window) / dec_period

            # Variance = sum((x - mean)^2) / N
            sum_sq_diff = sum((c.close - middle_band) ** 2 for c in window)
            variance = sum_sq_diff / dec_period
            std_dev = variance.sqrt()

            upper_band = middle_band + (self._num_std_dev * std_dev)
            lower_band = middle_band - (self._num_std_dev * std_dev)

            # Safeguard positive decimal invariant for lower band in edge cases
            if lower_band <= Decimal("0"):
                lower_band = Decimal("0.00000001")
            if lower_band > middle_band:
                lower_band = middle_band
            if upper_band < middle_band:
                upper_band = middle_band

            bandwidth_bps = ((upper_band - lower_band) / middle_band) * Decimal("10000")

            results.append(
                BollingerBandsDTO(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candles[idx].timestamp,
                    feature_name=self._name,
                    middle_band=middle_band,
                    upper_band=upper_band,
                    lower_band=lower_band,
                    bandwidth_bps=bandwidth_bps,
                    period=self._period,
                    num_std_dev=self._num_std_dev,
                )
            )

        return results
