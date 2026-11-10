"""Institutional Order Block computer."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import OrderBlockDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series


class OrderBlockComputer(FeatureComputer):
    """Institutional Order Block detection before price displacement."""

    def __init__(
        self,
        volume_threshold: Decimal | float = Decimal("1.2"),
        lookback_avg: int = 5,
        displacement_atr_mult: Decimal | float = Decimal("1.5"),
        custom_name: str | None = None,
    ) -> None:
        dec_vol = Decimal(str(volume_threshold))
        if dec_vol <= Decimal("0"):
            raise DTOValidationError(f"volume_threshold must be positive, got {volume_threshold}")
        if not isinstance(lookback_avg, int) or lookback_avg <= 0:
            raise DTOValidationError(f"lookback_avg must be a positive integer, got {lookback_avg}")
        dec_disp = Decimal(str(displacement_atr_mult))
        if dec_disp <= Decimal("0"):
            raise DTOValidationError(f"displacement_atr_mult must be positive, got {displacement_atr_mult}")

        self._volume_threshold = dec_vol
        self._lookback_avg = lookback_avg
        self._displacement_atr_mult = dec_disp
        self._name = custom_name or "ORDER_BLOCK"

    @property
    def feature_name(self) -> str:
        return self._name

    @property
    def displacement_atr_mult(self) -> Decimal:
        return self._displacement_atr_mult

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[OrderBlockDTO]:
        """Detect bullish and bearish order blocks in O(N)."""
        min_required = self._lookback_avg + 2
        validate_ohlcv_series(data, min_required=min_required)

        candles = data.candles
        results: list[OrderBlockDTO] = []
        n = len(candles)

        # Detect whether feed has valid non-zero volume
        has_valid_volume = any(c.volume > Decimal("0") for c in candles)

        for i in range(self._lookback_avg + 1, n):
            c_curr = candles[i]
            c_ob = candles[i - 1]

            # Primary: Volume surge logic when valid volume exists
            if has_valid_volume:
                window_vol = sum(candles[k].volume for k in range(i - self._lookback_avg, i))
                avg_vol = window_vol / Decimal(self._lookback_avg)
                if avg_vol > Decimal("0"):
                    vol_surge_ratio = c_curr.volume / avg_vol
                    displacement_confirmed = (vol_surge_ratio >= self._volume_threshold)
                else:
                    displacement_confirmed = False
                    vol_surge_ratio = Decimal("1.0")
            else:
                # Fallback: Price-displacement rule using rolling true range (ATR) for zero-volume feeds
                tr_sum = Decimal("0")
                for k in range(i - self._lookback_avg, i):
                    prev_c = candles[k - 1].close if k > 0 else None
                    hl = candles[k].high - candles[k].low
                    if prev_c is not None:
                        tr = max(hl, abs(candles[k].high - prev_c), abs(candles[k].low - prev_c))
                    else:
                        tr = hl
                    tr_sum += tr
                rolling_atr = tr_sum / Decimal(self._lookback_avg)

                if rolling_atr > Decimal("0"):
                    # Institutional displacement measured by candle body expansion
                    body_disp = abs(c_curr.close - c_curr.open)
                    surge_ratio = body_disp / rolling_atr
                    displacement_confirmed = (surge_ratio >= self._displacement_atr_mult)
                    vol_surge_ratio = surge_ratio
                else:
                    displacement_confirmed = False
                    vol_surge_ratio = Decimal("1.0")

            if not displacement_confirmed:
                continue

            # 1. Bullish Order Block: Bearish candle (c_ob) followed by strong bullish displacement (c_curr)
            is_ob_bearish_candle = c_ob.close <= c_ob.open
            is_curr_bullish_displacement = c_curr.close > c_ob.high
            if is_ob_bearish_candle and is_curr_bullish_displacement:
                top = c_ob.high
                bottom = c_ob.low
                # Check mitigation in subsequent candles
                mitigated = False
                for k in range(i + 1, n):
                    if candles[k].low <= bottom:
                        mitigated = True
                        break

                results.append(
                    OrderBlockDTO(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=c_curr.timestamp,
                        feature_name=self._name,
                        is_bullish=True,
                        top_price=top,
                        bottom_price=bottom,
                        volume_surge_ratio=vol_surge_ratio,
                        mitigated=mitigated,
                    )
                )

            # 2. Bearish Order Block: Bullish candle (c_ob) followed by strong bearish displacement (c_curr)
            is_ob_bullish_candle = c_ob.close >= c_ob.open
            is_curr_bearish_displacement = c_curr.close < c_ob.low
            if is_ob_bullish_candle and is_curr_bearish_displacement:
                top = c_ob.high
                bottom = c_ob.low
                # Check mitigation in subsequent candles
                mitigated = False
                for k in range(i + 1, n):
                    if candles[k].high >= top:
                        mitigated = True
                        break

                results.append(
                    OrderBlockDTO(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=c_curr.timestamp,
                        feature_name=self._name,
                        is_bullish=False,
                        top_price=top,
                        bottom_price=bottom,
                        volume_surge_ratio=vol_surge_ratio,
                        mitigated=mitigated,
                    )
                )

        return results
