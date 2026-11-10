"""Economic calendar and central bank events provider protocol."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence, runtime_checkable

from tradingagents.dataflows.dto.economic_calendar import EconomicReleaseDTO


@runtime_checkable
class EconomicCalendarProvider(Protocol):
    """Protocol for macroeconomic and central bank release discovery.

    Accommodates FOMC, CPI, PPI, NFP, PCE, GDP, Retail Sales, BOJ Meetings,
    Federal Reserve Events, and Treasury Auctions.
    """

    @property
    def provider_name(self) -> str:
        """Unique provider identifier."""
        ...

    def get_economic_events(
        self,
        start_date: datetime,
        end_date: datetime,
        country: str | None = None,
        min_impact: str | None = None,
    ) -> Sequence[EconomicReleaseDTO]:
        """Fetch scheduled or released economic events within the specified time window."""
        ...
