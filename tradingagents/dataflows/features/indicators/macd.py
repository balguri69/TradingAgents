"""Moving Average Convergence Divergence (MACD) deterministic computer."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import MACDDTO
from tradingagents.dataflows.dto.market_data import OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series


class MACDComputer(FeatureComputer):
    """Linear-time MACD computer producing MACD line, signal line, and histogram."""

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        custom_name: str | None = None,
    ) -> None:
        if not isinstance(fast_period, int) or fast_period <= 0:
            raise DTOValidationError(f"fast_period must be a positive integer, got {fast_period}")
        if not isinstance(slow_period, int) or slow_period <= 0:
            raise DTOValidationError(f"slow_period must be a positive integer, got {slow_period}")
        if not isinstance(signal_period, int) or signal_period <= 0:
            raise DTOValidationError(f"signal_period must be a positive integer, got {signal_period}")
        if fast_period >= slow_period:
            raise DTOValidationError(f"fast_period ({fast_period}) must be < slow_period ({slow_period})")

        self._fast_period = fast_period
        self._slow_period = slow_period
        self._signal_period = signal_period
        self._name = custom_name or f"MACD_{fast_period}_{slow_period}_{signal_period}"

        self._k_fast = Decimal("2") / Decimal(fast_period + 1)
        self._k_slow = Decimal("2") / Decimal(slow_period + 1)
        self._k_signal = Decimal("2") / Decimal(signal_period + 1)

    @property
    def feature_name(self) -> str:
        return self._name

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[MACDDTO]:
        """Compute MACD, Signal, and Histogram observations in O(N)."""
        min_required = self._slow_period + self._signal_period - 1
        validate_ohlcv_series(data, min_required=min_required)

        candles = data.candles
        dec_fast = Decimal(self._fast_period)
        dec_slow = Decimal(self._slow_period)
        dec_sig = Decimal(self._signal_period)

        # 1. Compute Fast EMA starting from index fast_period - 1
        fast_ema = sum(c.close for c in candles[: self._fast_period]) / dec_fast
        fast_emas: list[Decimal] = [fast_ema]
        for idx in range(self._fast_period, len(candles)):
            fast_ema = (candles[idx].close * self._k_fast) + (fast_ema * (Decimal("1") - self._k_fast))
            fast_emas.append(fast_ema)

        # 2. Compute Slow EMA starting from index slow_period - 1
        slow_ema = sum(c.close for c in candles[: self._slow_period]) / dec_slow
        slow_emas: list[Decimal] = [slow_ema]
        for idx in range(self._slow_period, len(candles)):
            slow_ema = (candles[idx].close * self._k_slow) + (slow_ema * (Decimal("1") - self._k_slow))
            slow_emas.append(slow_ema)

        # 3. Compute MACD Line = Fast EMA - Slow EMA
        # Note: fast_emas has length len(candles) - fast_period + 1
        # slow_emas has length len(candles) - slow_period + 1
        # An offset connects fast_emas to slow_emas:
        offset = self._slow_period - self._fast_period
        macd_lines: list[Decimal] = []
        for i in range(len(slow_emas)):
            macd_lines.append(fast_emas[i + offset] - slow_emas[i])

        # 4. Compute Signal Line (EMA of MACD Line over signal_period)
        signal_seed = sum(macd_lines[: self._signal_period]) / dec_sig
        current_signal = signal_seed

        results: list[MACDDTO] = []
        first_candle_idx = self._slow_period - 1 + self._signal_period - 1
        first_macd = macd_lines[self._signal_period - 1]
        first_hist = first_macd - current_signal

        results.append(
            MACDDTO(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=candles[first_candle_idx].timestamp,
                feature_name=self._name,
                macd_line=first_macd,
                signal_line=current_signal,
                histogram=first_hist,
                fast_period=self._fast_period,
                slow_period=self._slow_period,
                signal_period=self._signal_period,
            )
        )

        for j in range(self._signal_period, len(macd_lines)):
            candle_idx = self._slow_period - 1 + j
            m_val = macd_lines[j]
            current_signal = (m_val * self._k_signal) + (current_signal * (Decimal("1") - self._k_signal))
            hist = m_val - current_signal
            results.append(
                MACDDTO(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candles[candle_idx].timestamp,
                    feature_name=self._name,
                    macd_line=m_val,
                    signal_line=current_signal,
                    histogram=hist,
                    fast_period=self._fast_period,
                    slow_period=self._slow_period,
                    signal_period=self._signal_period,
                )
            )

        return results
