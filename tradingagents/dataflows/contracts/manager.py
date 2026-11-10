"""Universal market data provider manager protocol."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence, runtime_checkable

from tradingagents.dataflows.dto.market_data import (
    FundingRateDTO,
    OHLCVSeriesDTO,
    OrderBookDTO,
    QuoteDTO,
)
from tradingagents.dataflows.dto.telemetry import HealthStatusDTO
from tradingagents.dataflows.enums import Timeframe


@runtime_checkable
class MarketDataProviderManager(Protocol):
    """Structural protocol for universal multi-asset market data orchestration."""

    def get_quote(self, symbol: str, as_of: datetime | None = None) -> QuoteDTO:
        """Fetch quote via managed discovery and failover."""
        ...

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_date: datetime,
        end_date: datetime,
    ) -> OHLCVSeriesDTO:
        """Fetch continuous OHLCV candles via managed discovery and failover."""
        ...

    def get_orderbook(
        self, symbol: str, depth: int = 20, as_of: datetime | None = None
    ) -> OrderBookDTO:
        """Fetch order book snapshot via managed discovery and failover."""
        ...

    def get_funding_rate(
        self, symbol: str, as_of: datetime | None = None
    ) -> FundingRateDTO:
        """Fetch perpetual funding rate via managed capability routing."""
        ...

    def health_check(self) -> Sequence[HealthStatusDTO]:
        """Execute diagnostic health checks across all managed providers."""
        ...
