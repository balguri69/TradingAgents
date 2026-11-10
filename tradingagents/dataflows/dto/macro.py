"""Macroeconomic data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from tradingagents.dataflows.dto.validation import validate_utc_datetime
from tradingagents.dataflows.exceptions import DTOValidationError


@dataclass(frozen=True)
class MacroDataPointDTO:
    """Single observation of a macroeconomic indicator."""

    date: datetime
    value: Decimal

    def __post_init__(self) -> None:
        validate_utc_datetime(self.date, "date")
        if not isinstance(self.value, Decimal):
            raise DTOValidationError(f"value must be a Decimal, got {type(self.value).__name__}")


@dataclass(frozen=True)
class MacroSeriesDTO:
    """Macroeconomic indicator timeseries."""

    series_id: str
    name: str
    frequency: str
    units: str
    observations: tuple[MacroDataPointDTO, ...]

    def __post_init__(self) -> None:
        if not self.series_id:
            raise DTOValidationError("series_id must be non-empty")
        if not isinstance(self.observations, tuple):
            raise DTOValidationError("observations must be a tuple")
