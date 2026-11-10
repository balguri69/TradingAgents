"""Abstract contracts, protocols, and configuration for multi-asset dataflows."""

from __future__ import annotations

from tradingagents.dataflows.contracts.capabilities import (
    ProviderCapabilities,
    ProviderMetadata,
)
from tradingagents.dataflows.contracts.economic_calendar import (
    EconomicCalendarProvider,
)
from tradingagents.dataflows.contracts.features import (
    FeatureComputer,
    FeatureStore,
)
from tradingagents.dataflows.contracts.manager import MarketDataProviderManager
from tradingagents.dataflows.contracts.provider import (
    ExchangeProvider,
    MarketDataProvider,
)
from tradingagents.dataflows.contracts.registry import ProviderRegistry
from tradingagents.dataflows.contracts.transport import (
    TimeoutConfig,
    TransportClient,
)

__all__ = [
    "TimeoutConfig",
    "TransportClient",
    "MarketDataProvider",
    "ExchangeProvider",
    "ProviderCapabilities",
    "ProviderMetadata",
    "EconomicCalendarProvider",
    "ProviderRegistry",
    "MarketDataProviderManager",
    "FeatureComputer",
    "FeatureStore",
]
