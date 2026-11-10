"""Break of Structure (BOS) trend continuation computer."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import BreakOfStructureDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series
from tradingagents.dataflows.features.structure.swings import detect_swings


class BreakOfStructureComputer(FeatureComputer):
    """Institutional Break of Structure (BOS) computer confirming trend continuation."""

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
        self._name = custom_name or "BOS"

    @property
    def feature_name(self) -> str:
        return self._name

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[BreakOfStructureDTO]:
        """Detect structural breaks of prior confirmed swing highs and swing lows."""
        min_required = self._left_bars + self._right_bars + 2
        validate_ohlcv_series(data, min_required=min_required)

        candles = data.candles
        raw_swings = detect_swings(candles, self._left_bars, self._right_bars)
        if not raw_swings:
            return []

        results: list[BreakOfStructureDTO] = []
        n = len(candles)

        # Track active swing pivots as of each candle index
        # A swing is eligible to be broken only AFTER its confirmation index
        swing_idx = 0
        active_high: Decimal | None = None
        active_low: Decimal | None = None
        current_trend_bullish: bool | None = None

        for i in range(n):
            # Update active swings that have reached confirmation index
            while swing_idx < len(raw_swings) and raw_swings[swing_idx].confirmation_index <= i:
                s = raw_swings[swing_idx]
                if s.is_high:
                    active_high = s.price
                else:
                    active_low = s.price
                swing_idx += 1

            c = candles[i]
            break_val = c.close if self._require_close_break else c.high
            break_val_low = c.close if self._require_close_break else c.low

            # 1. Bullish BOS: Price breaks above active confirmed swing high in an established/neutral uptrend
            if active_high is not None and break_val > active_high:
                if current_trend_bullish is not False:
                    results.append(
                        BreakOfStructureDTO(
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=c.timestamp,
                            feature_name=self._name,
                            is_bullish=True,
                            broken_level=active_high,
                            displacement_volume=c.volume,
                        )
                    )
                current_trend_bullish = True
                active_high = None  # Consume the broken swing high

            # 2. Bearish BOS: Price breaks below active confirmed swing low in an established/neutral downtrend
            elif active_low is not None and break_val_low < active_low:
                if current_trend_bullish is not True:
                    results.append(
                        BreakOfStructureDTO(
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=c.timestamp,
                            feature_name=self._name,
                            is_bullish=False,
                            broken_level=active_low,
                            displacement_volume=c.volume,
                        )
                    )
                current_trend_bullish = False
                active_low = None  # Consume the broken swing low

        return results
