"""News and catalyst data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from tradingagents.dataflows.dto.validation import validate_utc_datetime
from tradingagents.dataflows.exceptions import DTOValidationError


@dataclass(frozen=True)
class NewsArticleDTO:
    """Individual financial news item or geopolitical event."""

    article_id: str
    headline: str
    source: str
    url: str
    published_at: datetime
    summary: str
    sentiment_hint: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.article_id:
            raise DTOValidationError("article_id must be non-empty")
        if not self.headline:
            raise DTOValidationError("headline must be non-empty")
        validate_utc_datetime(self.published_at, "published_at")
        if self.sentiment_hint is not None and not isinstance(self.sentiment_hint, Decimal):
            raise DTOValidationError("sentiment_hint must be a Decimal or None")
