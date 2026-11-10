"""Exception taxonomy for multi-asset dataflows, vendors, and DTO validations."""

from __future__ import annotations

from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorError,
    VendorNotConfiguredError,
    VendorRateLimitError,
    VendorUnavailableError,
)


class TradingAgentsError(Exception):
    """Base domain exception for all platform operations."""


class MarketDataError(TradingAgentsError):
    """Base error for data retrieval failures."""


class DTOValidationError(ValueError, TradingAgentsError):
    """Raised when a financial DTO fails invariant validation (e.g. negative price, non-UTC datetime)."""


__all__ = [
    "TradingAgentsError",
    "MarketDataError",
    "DTOValidationError",
    "VendorError",
    "NoMarketDataError",
    "VendorUnavailableError",
    "VendorRateLimitError",
    "VendorNotConfiguredError",
]
