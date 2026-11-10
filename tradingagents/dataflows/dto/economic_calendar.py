"""Economic calendar and central bank release data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from tradingagents.dataflows.dto.validation import validate_utc_datetime
from tradingagents.dataflows.exceptions import DTOValidationError


class EconomicImpact(Enum):
    """Impact classification for economic calendar events."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


@dataclass(frozen=True)
class EconomicReleaseDTO:
    """Standardized representation of a macroeconomic or central bank release.

    Accommodates FOMC, CPI, PPI, NFP, PCE, GDP, Retail Sales, BOJ Meetings,
    Treasury Auctions, and high-impact macro catalysts.
    """

    event_id: str
    title: str
    country: str  # e.g., "US", "JP", "EU", "GB"
    currency: str  # e.g., "USD", "JPY", "EUR", "GBP"
    event_time: datetime  # Mandatory UTC timestamp
    impact: EconomicImpact = EconomicImpact.HIGH
    actual: Decimal | None = None
    forecast: Decimal | None = None
    previous: Decimal | None = None
    unit: str = "%"
    source: str = ""

    def __post_init__(self) -> None:
        if not self.event_id or not self.event_id.strip():
            raise DTOValidationError("event_id must be non-empty")
        if not self.title or not self.title.strip():
            raise DTOValidationError("title must be non-empty")
        if not self.country or not self.country.strip():
            raise DTOValidationError("country must be non-empty")
        validate_utc_datetime(self.event_time, "event_time")
        for field_name, val in [
            ("actual", self.actual),
            ("forecast", self.forecast),
            ("previous", self.previous),
        ]:
            if val is not None and not isinstance(val, Decimal):
                raise DTOValidationError(
                    f"{field_name} must be a Decimal or None, got {type(val).__name__}"
                )
