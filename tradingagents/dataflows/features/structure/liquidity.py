"""Resting liquidity pools and liquidity sweeps detection."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import LiquidityPoolDTO, LiquiditySweepDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series
from tradingagents.dataflows.features.structure.swings import detect_swings


class LiquidityPoolComputer(FeatureComputer):
    """Resting liquidity pools computer (Equal Highs - EQH, Equal Lows - EQL)."""

    def __init__(
        self,
        left_bars: int = 2,
        right_bars: int = 2,
        tolerance_bps: Decimal | float = Decimal("10.0"),
        custom_name: str | None = None,
    ) -> None:
        if not isinstance(left_bars, int) or left_bars <= 0:
            raise DTOValidationError(f"left_bars must be positive integer, got {left_bars}")
        if not isinstance(right_bars, int) or right_bars <= 0:
            raise DTOValidationError(f"right_bars must be positive integer, got {right_bars}")
        dec_bps = Decimal(str(tolerance_bps))
        if dec_bps < Decimal("0"):
            raise DTOValidationError(f"tolerance_bps must be non-negative, got {tolerance_bps}")

        self._left_bars = left_bars
        self._right_bars = right_bars
        self._tolerance_bps = dec_bps
        self._name = custom_name or "LIQUIDITY_POOL"

    @property
    def feature_name(self) -> str:
        return self._name

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[LiquidityPoolDTO]:
        """Detect Equal Highs and Equal Lows resting liquidity pools."""
        min_required = self._left_bars + self._right_bars + 2
        validate_ohlcv_series(data, min_required=min_required)

        candles = data.candles
        raw_swings = detect_swings(candles, self._left_bars, self._right_bars)
        if len(raw_swings) < 2:
            return []

        results: list[LiquidityPoolDTO] = []
        high_swings = [s for s in raw_swings if s.is_high]
        low_swings = [s for s in raw_swings if not s.is_high]

        # 1. Detect Equal Highs (EQH)
        for i in range(1, len(high_swings)):
            s_curr = high_swings[i]
            s_prev = high_swings[i - 1]
            diff = abs(s_curr.price - s_prev.price)
            avg_price = (s_curr.price + s_prev.price) / Decimal("2")
            bps = (diff / avg_price) * Decimal("10000")

            if bps <= self._tolerance_bps:
                # Check if swept later
                swept = any(c.high > max(s_curr.price, s_prev.price) for c in candles[s_curr.confirmation_index :])
                results.append(
                    LiquidityPoolDTO(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=s_curr.confirmation_timestamp,
                        feature_name=self._name,
                        is_high=True,
                        level=avg_price,
                        touch_count=2,
                        tolerance_bps=self._tolerance_bps,
                        swept=swept,
                    )
                )

        # 2. Detect Equal Lows (EQL)
        for i in range(1, len(low_swings)):
            s_curr = low_swings[i]
            s_prev = low_swings[i - 1]
            diff = abs(s_curr.price - s_prev.price)
            avg_price = (s_curr.price + s_prev.price) / Decimal("2")
            bps = (diff / avg_price) * Decimal("10000")

            if bps <= self._tolerance_bps:
                swept = any(c.low < min(s_curr.price, s_prev.price) for c in candles[s_curr.confirmation_index :])
                results.append(
                    LiquidityPoolDTO(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=s_curr.confirmation_timestamp,
                        feature_name=self._name,
                        is_high=False,
                        level=avg_price,
                        touch_count=2,
                        tolerance_bps=self._tolerance_bps,
                        swept=swept,
                    )
                )

        return results


class LiquiditySweepComputer(FeatureComputer):
    """Institutional Liquidity Sweep detector."""

    def __init__(
        self,
        left_bars: int = 2,
        right_bars: int = 2,
        custom_name: str | None = None,
    ) -> None:
        if not isinstance(left_bars, int) or left_bars <= 0:
            raise DTOValidationError(f"left_bars must be positive integer, got {left_bars}")
        if not isinstance(right_bars, int) or right_bars <= 0:
            raise DTOValidationError(f"right_bars must be positive integer, got {right_bars}")

        self._left_bars = left_bars
        self._right_bars = right_bars
        self._name = custom_name or "LIQUIDITY_SWEEP"

    @property
    def feature_name(self) -> str:
        return self._name

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[LiquiditySweepDTO]:
        """Detect sweeps of confirmed swing highs and lows where price wicks beyond but closes within."""
        min_required = self._left_bars + self._right_bars + 2
        validate_ohlcv_series(data, min_required=min_required)

        candles = data.candles
        raw_swings = detect_swings(candles, self._left_bars, self._right_bars)
        if not raw_swings:
            return []

        results: list[LiquiditySweepDTO] = []
        n = len(candles)

        swing_idx = 0
        active_high: Decimal | None = None
        active_low: Decimal | None = None

        for i in range(n):
            while swing_idx < len(raw_swings) and raw_swings[swing_idx].confirmation_index <= i:
                s = raw_swings[swing_idx]
                if s.is_high:
                    active_high = s.price
                else:
                    active_low = s.price
                swing_idx += 1

            c = candles[i]

            # 1. Buy-side Sweep: Wick penetrates active swing high, but close finishes below it
            if active_high is not None and c.high > active_high and c.close < active_high:
                results.append(
                    LiquiditySweepDTO(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=c.timestamp,
                        feature_name=self._name,
                        is_buy_side=True,
                        swept_level=active_high,
                        rejection_price=c.close,
                    )
                )
                # Level is consumed once swept; do not re-sweep on subsequent wicks
                active_high = None
            elif active_high is not None and c.close >= active_high:
                # Level is violated with body close (breakout); no longer active for wick sweep
                active_high = None

            # 2. Sell-side Sweep: Wick penetrates active swing low, but close finishes above it
            if active_low is not None and c.low < active_low and c.close > active_low:
                results.append(
                    LiquiditySweepDTO(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=c.timestamp,
                        feature_name=self._name,
                        is_buy_side=False,
                        swept_level=active_low,
                        rejection_price=c.close,
                    )
                )
                # Level is consumed once swept; do not re-sweep on subsequent wicks
                active_low = None
            elif active_low is not None and c.close <= active_low:
                # Level is violated with body close (breakout); no longer active for wick sweep
                active_low = None

        return results
