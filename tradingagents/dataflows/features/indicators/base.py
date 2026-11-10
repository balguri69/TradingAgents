"""Validation and shared helpers for technical indicator computers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from tradingagents.dataflows.dto.market_data import CandleDTO, OHLCVSeriesDTO
from tradingagents.dataflows.dto.validation import validate_utc_datetime
from tradingagents.dataflows.exceptions import DTOValidationError


def validate_ohlcv_series(series: OHLCVSeriesDTO, min_required: int = 1) -> None:
    """Validate that an OHLCV series satisfies financial and temporal invariants.
    
    Rejects:
    - Non-OHLCVSeriesDTO objects
    - Insufficient candle count (< min_required)
    - Timezone-naive timestamps
    - Non-monotonic / unsorted timestamps
    - Duplicate timestamps
    - NaN or Infinite values
    - Negative or zero price values
    - Violations of low <= open/close <= high
    """
    if not isinstance(series, OHLCVSeriesDTO):
        raise DTOValidationError(f"Expected OHLCVSeriesDTO instance, got {type(series)}")

    candles = series.candles
    if not isinstance(candles, (tuple, list)):
        raise DTOValidationError(f"Candles must be a sequence, got {type(candles)}")

    if len(candles) < min_required:
        raise DTOValidationError(
            f"Insufficient candles for calculation: required at least {min_required}, got {len(candles)}"
        )

    prev_ts: datetime | None = None
    for idx, c in enumerate(candles):
        if not isinstance(c, CandleDTO):
            raise DTOValidationError(f"Element at index {idx} is not CandleDTO: {type(c)}")

        validate_utc_datetime(c.timestamp, f"candle[{idx}].timestamp")

        # Check strictly monotonic ascending timestamps (rejects unsorted & duplicate timestamps)
        if prev_ts is not None and c.timestamp <= prev_ts:
            if c.timestamp == prev_ts:
                raise DTOValidationError(
                    f"Duplicate timestamp detected at candle index {idx}: {c.timestamp}"
                )
            raise DTOValidationError(
                f"Unsorted candle series: candle at index {idx} ({c.timestamp}) is before previous ({prev_ts})"
            )
        prev_ts = c.timestamp

        # Validate numbers: NaN, Infinite, zero/negative
        for field_name, val in (
            ("open", c.open),
            ("high", c.high),
            ("low", c.low),
            ("close", c.close),
            ("volume", c.volume),
        ):
            if not isinstance(val, Decimal):
                raise DTOValidationError(f"Candle[{idx}].{field_name} must be Decimal, got {type(val)}")
            if val.is_nan():
                raise DTOValidationError(f"Candle[{idx}].{field_name} contains NaN")
            if val.is_infinite():
                raise DTOValidationError(f"Candle[{idx}].{field_name} contains Infinite")

        if c.open <= Decimal("0") or c.high <= Decimal("0") or c.low <= Decimal("0") or c.close <= Decimal("0"):
            raise DTOValidationError(f"Candle[{idx}] contains zero or negative price")
        if c.volume < Decimal("0"):
            raise DTOValidationError(f"Candle[{idx}] contains negative volume: {c.volume}")

        if c.low > c.high:
            raise DTOValidationError(f"Candle[{idx}] low ({c.low}) exceeds high ({c.high})")
        if not (c.low <= c.open <= c.high):
            raise DTOValidationError(f"Candle[{idx}] open ({c.open}) outside [low, high]")
        if not (c.low <= c.close <= c.high):
            raise DTOValidationError(f"Candle[{idx}] close ({c.close}) outside [low, high]")
