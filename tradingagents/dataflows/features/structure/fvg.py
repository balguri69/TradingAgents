"""Fair Value Gap (FVG) institutional price imbalance computer."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import FairValueGapDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series


class FairValueGapComputer(FeatureComputer):
    """Institutional 3-candle Fair Value Gap (imbalance) computer."""

    def __init__(
        self,
        min_gap_bps: Decimal | float = Decimal("0.0"),
        custom_name: str | None = None,
    ) -> None:
        dec_bps = Decimal(str(min_gap_bps))
        if dec_bps < Decimal("0"):
            raise DTOValidationError(f"min_gap_bps must be non-negative, got {min_gap_bps}")
        self._min_gap_bps = dec_bps
        self._name = custom_name or "FVG"

    @property
    def feature_name(self) -> str:
        return self._name

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[FairValueGapDTO]:
        """Detect bullish and bearish FVGs across 3-candle sequences in O(N)."""
        validate_ohlcv_series(data, min_required=3)

        candles = data.candles
        results: list[FairValueGapDTO] = []
        n = len(candles)

        for i in range(2, n):
            c_prev2 = candles[i - 2]
            c_curr = candles[i]

            # 1. Check Bullish FVG: candle[i].low > candle[i-2].high
            if c_curr.low > c_prev2.high:
                upper = c_curr.low
                lower = c_prev2.high
                gap_size = upper - lower
                bps = (gap_size / lower) * Decimal("10000")

                if bps >= self._min_gap_bps:
                    # Check mitigation by candles formed after i
                    mitigated = False
                    for k in range(i + 1, n):
                        if candles[k].low <= lower:
                            mitigated = True
                            break

                    results.append(
                        FairValueGapDTO(
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=c_curr.timestamp,
                            feature_name=self._name,
                            is_bullish=True,
                            upper_bound=upper,
                            lower_bound=lower,
                            mitigated=mitigated,
                        )
                    )

            # 2. Check Bearish FVG: candle[i].high < candle[i-2].low
            elif c_curr.high < c_prev2.low:
                upper = c_prev2.low
                lower = c_curr.high
                gap_size = upper - lower
                bps = (gap_size / upper) * Decimal("10000")

                if bps >= self._min_gap_bps:
                    # Check mitigation by candles formed after i
                    mitigated = False
                    for k in range(i + 1, n):
                        if candles[k].high >= upper:
                            mitigated = True
                            break

                    results.append(
                        FairValueGapDTO(
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=c_curr.timestamp,
                            feature_name=self._name,
                            is_bullish=False,
                            upper_bound=upper,
                            lower_bound=lower,
                            mitigated=mitigated,
                        )
                    )

        return results
