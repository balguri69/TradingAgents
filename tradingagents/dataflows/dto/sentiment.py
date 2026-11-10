"""Crowd and prediction market sentiment data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from tradingagents.dataflows.dto.validation import validate_utc_datetime
from tradingagents.dataflows.exceptions import DTOValidationError


@dataclass(frozen=True)
class SentimentScoreDTO:
    """Aggregated retail/crowd sentiment metric."""

    symbol: str
    timestamp: datetime
    sentiment_index: Decimal
    sample_volume: int
    source_channels: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.symbol:
            raise DTOValidationError("symbol must be non-empty")
        validate_utc_datetime(self.timestamp, "timestamp")
        if not isinstance(self.sentiment_index, Decimal):
            raise DTOValidationError("sentiment_index must be a Decimal")
        if not (Decimal("-1.0") <= self.sentiment_index <= Decimal("1.0")):
            raise DTOValidationError(f"sentiment_index must be within [-1.0, +1.0], got {self.sentiment_index}")
        if self.sample_volume < 0:
            raise DTOValidationError(f"sample_volume cannot be negative, got {self.sample_volume}")
        if not isinstance(self.source_channels, tuple):
            raise DTOValidationError("source_channels must be a tuple")
