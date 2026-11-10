"""Change of Character (CHoCH) structural reversal computer."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import ChangeOfCharacterDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series
from tradingagents.dataflows.features.structure.swings import detect_swings


class ChangeOfCharacterComputer(FeatureComputer):
    """Institutional Change of Character (CHoCH) computer detecting trend reversal triggers."""

    def __init__(
        self,
        left_bars: int = 2,
        right_bars: int = 2,
        require_close_break: bool = True,
        custom_name: str | None = None,
    ) -> None:
        if not isinstance(left_bars, int) or left_bars <= 0:
            raise DTOValidationError(f"left_bars must be positive integer, got {left_bars}")
        if not isinstance(right_bars, int) or right_bars <= 0:
            raise DTOValidationError(f"right_bars must be positive integer, got {right_bars}")

        self._left_bars = left_bars
        self._right_bars = right_bars
        self._require_close_break = require_close_break
        self._name = custom_name or "CHOCH"

    @property
    def feature_name(self) -> str:
        return self._name

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[ChangeOfCharacterDTO]:
        """Detect structural shifts from bullish to bearish or bearish to bullish."""
        min_required = self._left_bars + self._right_bars + 2
        validate_ohlcv_series(data, min_required=min_required)

        candles = data.candles
        raw_swings = detect_swings(candles, self._left_bars, self._right_bars)
        if not raw_swings:
            return []

        results: list[ChangeOfCharacterDTO] = []
        n = len(candles)

        swing_idx = 0
        active_high: Decimal | None = None
        active_low: Decimal | None = None
        current_trend_bullish: bool | None = None

        for i in range(n):
            while swing_idx < len(raw_swings) and raw_swings[swing_idx].confirmation_index <= i:
                s = raw_swings[swing_idx]
                if s.is_high:
                    active_high = s.price
                else:
                    active_low = s.price
                swing_idx += 1

            c = candles[i]
            break_val_high = c.close if self._require_close_break else c.high
            break_val_low = c.close if self._require_close_break else c.low

            # 1. Bullish CHoCH: Established bearish trend breaks above active swing high
            if current_trend_bullish is False and active_high is not None and break_val_high > active_high:
                results.append(
                    ChangeOfCharacterDTO(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=c.timestamp,
                        feature_name=self._name,
                        is_bullish=True,
                        pivot_level=active_high,
                    )
                )
                current_trend_bullish = True
                active_high = None

            # 2. Bearish CHoCH: Established bullish trend breaks below active swing low
            elif current_trend_bullish is True and active_low is not None and break_val_low < active_low:
                results.append(
                    ChangeOfCharacterDTO(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=c.timestamp,
                        feature_name=self._name,
                        is_bullish=False,
                        pivot_level=active_low,
                    )
                )
                current_trend_bullish = False
                active_low = None

            # Seed initial trend if not established yet
            elif current_trend_bullish is None:
                if active_high is not None and break_val_high > active_high:
                    current_trend_bullish = True
                    active_high = None
                elif active_low is not None and break_val_low < active_low:
                    current_trend_bullish = False
                    active_low = None

        return results
