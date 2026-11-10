"""Premium vs Discount zone institutional valuation computer."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import PremiumDiscountDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series


class PremiumDiscountComputer(FeatureComputer):
    """Institutional Premium vs Discount zone computer."""

    def __init__(
        self,
        lookback_period: int = 20,
        equilibrium_band_pct: Decimal | float = Decimal("1.0"),
        custom_name: str | None = None,
    ) -> None:
        if not isinstance(lookback_period, int) or lookback_period <= 1:
            raise DTOValidationError(f"lookback_period must be an integer >= 2, got {lookback_period}")
        dec_band = Decimal(str(equilibrium_band_pct))
        if dec_band < Decimal("0"):
            raise DTOValidationError(f"equilibrium_band_pct must be non-negative, got {equilibrium_band_pct}")

        self._lookback_period = lookback_period
        self._equilibrium_band_pct = dec_band
        self._name = custom_name or f"PREMIUM_DISCOUNT_{lookback_period}"

    @property
    def feature_name(self) -> str:
        return self._name

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[PremiumDiscountDTO]:
        """Compute Premium/Discount classification for each candle window in O(N)."""
        validate_ohlcv_series(data, min_required=self._lookback_period)

        candles = data.candles
        results: list[PremiumDiscountDTO] = []
        n = len(candles)

        for i in range(self._lookback_period - 1, n):
            window = candles[i - self._lookback_period + 1 : i + 1]
            c_curr = window[-1]

            r_high = max(c.high for c in window)
            r_low = min(c.low for c in window)
            eq = (r_high + r_low) / Decimal("2")
            c_price = c_curr.close

            spread = r_high - r_low
            if spread == Decimal("0"):
                pct = Decimal("50.0")
                zone = "EQUILIBRIUM"
            else:
                pct = ((c_price - r_low) / spread) * Decimal("100")
                half_band = self._equilibrium_band_pct / Decimal("2")
                if pct > (Decimal("50.0") + half_band):
                    zone = "PREMIUM"
                elif pct < (Decimal("50.0") - half_band):
                    zone = "DISCOUNT"
                else:
                    zone = "EQUILIBRIUM"

            results.append(
                PremiumDiscountDTO(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=c_curr.timestamp,
                    feature_name=self._name,
                    range_high=r_high,
                    range_low=r_low,
                    equilibrium=eq,
                    current_price=c_price,
                    zone=zone,
                    percentile=pct,
                )
            )

        return results
