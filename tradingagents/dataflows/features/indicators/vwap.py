"""Volume-Weighted Average Price (VWAP) deterministic computer."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import VWAPDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series


class VWAPComputer(FeatureComputer):
    """Linear-time Volume-Weighted Average Price (VWAP) computer."""

    def __init__(self, reset_daily: bool = False, custom_name: str | None = None) -> None:
        self._reset_daily = reset_daily
        self._name = custom_name or ("VWAP_DAILY" if reset_daily else "VWAP")

    @property
    def feature_name(self) -> str:
        return self._name

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[VWAPDTO]:
        """Compute cumulative or session VWAP in O(N)."""
        validate_ohlcv_series(data, min_required=1)

        candles = data.candles
        dec_three = Decimal("3")
        results: list[VWAPDTO] = []

        cum_tp_vol = Decimal("0")
        cum_vol = Decimal("0")
        prev_date = None

        for c in candles:
            # Check daily session boundary reset if enabled
            if self._reset_daily:
                c_date = c.timestamp.date()
                if prev_date is not None and c_date != prev_date:
                    cum_tp_vol = Decimal("0")
                    cum_vol = Decimal("0")
                prev_date = c_date

            typical_price = (c.high + c.low + c.close) / dec_three
            cum_tp_vol += (typical_price * c.volume)
            cum_vol += c.volume

            if cum_vol > Decimal("0"):
                vwap_val = cum_tp_vol / cum_vol
            else:
                vwap_val = typical_price

            results.append(
                VWAPDTO(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=c.timestamp,
                    feature_name=self._name,
                    vwap=vwap_val,
                    volume_sum=cum_vol,
                )
            )

        return results
