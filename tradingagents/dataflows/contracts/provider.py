"""Universal data provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Sequence

from tradingagents.dataflows.contracts.capabilities import (
    ProviderCapabilities,
    ProviderMetadata,
)
from tradingagents.dataflows.dto.market_data import (
    ExchangeInfoDTO,
    FundingRateDTO,
    OHLCVSeriesDTO,
    OrderBookDTO,
    QuoteDTO,
    SymbolFilterDTO,
)
from tradingagents.dataflows.dto.telemetry import HealthStatusDTO
from tradingagents.dataflows.enums import Timeframe


class MarketDataProvider(ABC):
    """Universal contract for multi-asset institutional market data ingestion.

    Invariant: Providers strictly fetch, validate, normalize, and return DTOs.
    They contain ZERO trading, technical analysis, or investment heuristics.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier of the data provider (e.g., 'binance', 'coinbase')."""
        ...

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Provider capabilities value object declaring supported features."""
        return ProviderCapabilities(
            quote=True,
            ohlcv=True,
            orderbook=True,
        )

    @property
    def metadata(self) -> ProviderMetadata:
        """Provider operational metadata and future routing parameters."""
        return ProviderMetadata(provider_name=self.provider_name)

    @abstractmethod
    def get_supported_symbols(self) -> Sequence[str]:
        """Return list of canonical symbols supported by this provider."""
        ...

    def supports_feature(self, feature_name: str) -> bool:
        """Query if provider supports feature. Delegates to capabilities value object."""
        return self.capabilities.supports(feature_name)

    @abstractmethod
    def health_check(self) -> HealthStatusDTO:
        """Validate operational availability and return latency metrics."""
        ...

    @abstractmethod
    def get_quote(self, symbol: str, as_of: datetime | None = None) -> QuoteDTO:
        """Fetch quote (real-time if as_of is None, historical point-in-time otherwise)."""
        ...

    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_date: datetime,
        end_date: datetime,
    ) -> OHLCVSeriesDTO:
        """Retrieve continuous historical candlestick series over a time window."""
        ...

    @abstractmethod
    def get_orderbook(
        self, symbol: str, depth: int = 20, as_of: datetime | None = None
    ) -> OrderBookDTO:
        """Retrieve L2 market depth snapshot and spread metrics."""
        ...

    def get_funding_rate(
        self, symbol: str, as_of: datetime | None = None
    ) -> FundingRateDTO:
        """Retrieve derivative perpetual swap funding rate.

        Optional feature: callers should check ``supports_feature('funding_rate')``.
        Providers that do not support this feature raise NotImplementedError.
        """
        raise NotImplementedError(
            f"Provider {self.provider_name!r} does not support perpetual funding rates"
        )


class ExchangeProvider(MarketDataProvider, ABC):
    """Abstract base class for exchange-backed market data providers.

    Specializes MarketDataProvider for centralized and decentralized electronic venues
    (e.g., Binance, Coinbase, Yahoo Finance / COMEX).
    Enforces exchange-specific contract methods:
      - server time synchronization
      - symbol filters & trading precision rules
      - exchange information catalog
    """

    @abstractmethod
    def get_server_time(self) -> datetime:
        """Fetch venue official server time."""
        ...

    @abstractmethod
    def get_symbol_filters(self, symbol: str) -> SymbolFilterDTO:
        """Retrieve tick size, lot step size, and precision rules for an instrument."""
        ...

    @abstractmethod
    def get_exchange_info(self) -> ExchangeInfoDTO:
        """Retrieve full exchange information and trading rules catalog."""
        ...
