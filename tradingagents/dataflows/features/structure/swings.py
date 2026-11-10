"""Institutional Swing High and Swing Low detection."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, NamedTuple, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import SwingPointDTO
from tradingagents.dataflows.dto.market_data import CandleDTO, OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series


class RawSwing(NamedTuple):
    """Raw swing pivot detection result."""

    candle_index: int
    is_high: bool
    price: Decimal
    timestamp: datetime
    confirmation_index: int
    confirmation_timestamp: datetime


def detect_swings(
    candles: Sequence[CandleDTO],
    left_bars: int = 2,
    right_bars: int = 2,
) -> list[RawSwing]:
    """Detect local pivot swing highs and lows with strictly non-lookahead confirmation.

    A swing formed at candle index `i` is strictly confirmed and observable only at
    candle `i + right_bars`.
    """
    if len(candles) < (left_bars + right_bars + 1):
        return []

    swings: list[RawSwing] = []
    total_candles = len(candles)

    for i in range(left_bars, total_candles - right_bars):
        c_i = candles[i]
        c_high = c_i.high
        c_low = c_i.low

        # Check Swing High
        is_swing_high = True
        for l in range(i - left_bars, i):
            if candles[l].high >= c_high:
                is_swing_high = False
                break
        if is_swing_high:
            for r in range(i + 1, i + right_bars + 1):
                if candles[r].high > c_high:
                    is_swing_high = False
                    break

        if is_swing_high:
            conf_idx = i + right_bars
            swings.append(
                RawSwing(
                    candle_index=i,
                    is_high=True,
                    price=c_high,
                    timestamp=c_i.timestamp,
                    confirmation_index=conf_idx,
                    confirmation_timestamp=candles[conf_idx].timestamp,
                )
            )

        # Check Swing Low
        is_swing_low = True
        for l in range(i - left_bars, i):
            if candles[l].low <= c_low:
                is_swing_low = False
                break
        if is_swing_low:
            for r in range(i + 1, i + right_bars + 1):
                if candles[r].low < c_low:
                    is_swing_low = False
                    break

        if is_swing_low:
            conf_idx = i + right_bars
            swings.append(
                RawSwing(
                    candle_index=i,
                    is_high=False,
                    price=c_low,
                    timestamp=c_i.timestamp,
                    confirmation_index=conf_idx,
                    confirmation_timestamp=candles[conf_idx].timestamp,
                )
            )

    return swings


class SwingComputer(FeatureComputer):
    """Institutional Swing High and Swing Low detector."""

    def __init__(
        self,
        left_bars: int = 2,
        right_bars: int = 2,
        is_major: bool = False,
        custom_name: str | None = None,
    ) -> None:
        if not isinstance(left_bars, int) or left_bars <= 0:
            raise DTOValidationError(f"left_bars must be positive integer, got {left_bars}")
        if not isinstance(right_bars, int) or right_bars <= 0:
            raise DTOValidationError(f"right_bars must be positive integer, got {right_bars}")

        self._left_bars = left_bars
        self._right_bars = right_bars
        self._is_major = is_major
        default_name = f"SWING_{'MAJOR' if is_major else 'MINOR'}_{left_bars}_{right_bars}"
        self._name = custom_name or default_name

    @property
    def feature_name(self) -> str:
        return self._name

    @property
    def is_major(self) -> bool:
        return self._is_major

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[SwingPointDTO]:
        """Detect swing points with point-in-time confirmation timestamps."""
        min_required = self._left_bars + self._right_bars + 1
        validate_ohlcv_series(data, min_required=min_required)

        raw_swings = detect_swings(data.candles, self._left_bars, self._right_bars)
        results: list[SwingPointDTO] = []

        for s in raw_swings:
            results.append(
                SwingPointDTO(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=s.confirmation_timestamp,
                    feature_name=self._name,
                    is_high=s.is_high,
                    price=s.price,
                    is_major=self._is_major,
                )
            )

        return results
