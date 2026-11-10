"""Comprehensive unit tests for DefaultMarketDataProviderManager."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import unittest

from tradingagents.dataflows.contracts.manager import MarketDataProviderManager
from tradingagents.dataflows.contracts.provider import ExchangeProvider, MarketDataProvider
from tradingagents.dataflows.dto.market_data import (
    CandleDTO,
    ExchangeInfoDTO,
    FundingRateDTO,
    MarkPriceDTO,
    OHLCVSeriesDTO,
    OpenInterestDTO,
    OrderBookDTO,
    OrderBookLevelDTO,
    QuoteDTO,
    SymbolFilterDTO,
)
from tradingagents.dataflows.dto.telemetry import (
    HealthStatusDTO,
    ProviderHealth,
)
from tradingagents.dataflows.enums import CircuitState, HealthState, Timeframe
from tradingagents.dataflows.exceptions import (
    DTOValidationError,
    NoMarketDataError,
    VendorUnavailableError,
)
from tradingagents.dataflows.manager import DefaultMarketDataProviderManager
from tradingagents.dataflows.registry import InMemoryProviderRegistry


class MockExchangeProvider(ExchangeProvider):
    """Controllable mock exchange provider for manager orchestration tests."""

    def __init__(
        self,
        name: str,
        symbols: tuple[str, ...] = ("BTC/USDT", "ETH/USDT"),
        should_fail: bool = False,
        fail_error: Exception | None = None,
    ) -> None:
        self._name = name
        self._symbols = symbols
        self.should_fail = should_fail
        self.fail_error = fail_error or VendorUnavailableError(f"Provider {name} unavailable")
        self.call_counts: dict[str, int] = {
            "get_quote": 0,
            "get_ohlcv": 0,
            "get_orderbook": 0,
            "get_funding_rate": 0,
            "get_symbol_filters": 0,
            "get_exchange_info": 0,
            "health_check": 0,
        }

    @property
    def provider_name(self) -> str:
        return self._name

    def get_supported_symbols(self) -> tuple[str, ...]:
        return self._symbols

    def supports_feature(self, feature_name: str) -> bool:
        return feature_name.lower() in (
            "quote",
            "ohlcv",
            "orderbook",
            "funding_rate",
            "open_interest",
            "mark_price",
        )

    def health_check(self) -> HealthStatusDTO:
        self.call_counts["health_check"] += 1
        if self.should_fail:
            return HealthStatusDTO(
                provider_name=self._name,
                state=HealthState.UNHEALTHY,
                latency_ms=Decimal("0.0"),
                last_successful_query=None,
                error_message="Health check failed",
            )
        return HealthStatusDTO(
            provider_name=self._name,
            state=HealthState.HEALTHY,
            latency_ms=Decimal("5.0"),
            last_successful_query=datetime.now(timezone.utc),
        )

    def get_server_time(self) -> datetime:
        return datetime.now(timezone.utc)

    def get_quote(self, symbol: str, as_of: datetime | None = None) -> QuoteDTO:
        self.call_counts["get_quote"] += 1
        if self.should_fail:
            raise self.fail_error
        return QuoteDTO(
            symbol=symbol,
            price=Decimal("88000.00"),
            bid=Decimal("87995.00"),
            ask=Decimal("88005.00"),
            bid_size=Decimal("1.5"),
            ask_size=Decimal("2.0"),
            volume_24h=Decimal("15000.0"),
            timestamp=datetime.now(timezone.utc),
            provider=self._name,
        )

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_date: datetime,
        end_date: datetime,
    ) -> OHLCVSeriesDTO:
        self.call_counts["get_ohlcv"] += 1
        if self.should_fail:
            raise self.fail_error
        candle = CandleDTO(
            timestamp=start_date,
            open=Decimal("88000.00"),
            high=Decimal("88500.00"),
            low=Decimal("87900.00"),
            close=Decimal("88400.00"),
            volume=Decimal("100.0"),
        )
        return OHLCVSeriesDTO(
            symbol=symbol,
            timeframe=timeframe,
            candles=(candle,),
            provider=self._name,
        )

    def get_orderbook(
        self, symbol: str, depth: int = 20, as_of: datetime | None = None
    ) -> OrderBookDTO:
        self.call_counts["get_orderbook"] += 1
        if self.should_fail:
            raise self.fail_error
        bids = (OrderBookLevelDTO(price=Decimal("88000.00"), quantity=Decimal("1.0")),)
        asks = (OrderBookLevelDTO(price=Decimal("88005.00"), quantity=Decimal("1.0")),)
        return OrderBookDTO(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            bids=bids,
            asks=asks,
            spread_bps=Decimal("0.56"),
            provider=self._name,
        )

    def get_funding_rate(
        self, symbol: str, as_of: datetime | None = None
    ) -> FundingRateDTO:
        self.call_counts["get_funding_rate"] += 1
        if self.should_fail:
            raise self.fail_error
        return FundingRateDTO(
            symbol=symbol,
            funding_rate=Decimal("0.0001"),
            annualized_rate=Decimal("0.1095"),
            funding_time=datetime.now(timezone.utc),
            mark_price=Decimal("88000.00"),
            exchange=self._name,
        )

    def get_open_interest(self, symbol: str) -> OpenInterestDTO:
        if self.should_fail:
            raise self.fail_error
        return OpenInterestDTO(
            symbol=symbol,
            open_interest=Decimal("25000.0"),
            open_interest_usd=None,
            timestamp=datetime.now(timezone.utc),
            exchange=self._name,
        )

    def get_mark_price(self, symbol: str) -> MarkPriceDTO:
        if self.should_fail:
            raise self.fail_error
        return MarkPriceDTO(
            symbol=symbol,
            mark_price=Decimal("88000.00"),
            index_price=Decimal("87998.00"),
            timestamp=datetime.now(timezone.utc),
            exchange=self._name,
        )

    def _make_symbol_filter(self, symbol: str) -> SymbolFilterDTO:
        return SymbolFilterDTO(
            symbol=symbol,
            base_asset="BTC",
            quote_asset="USDT",
            price_precision=2,
            quantity_precision=6,
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.00001"),
            min_quantity=Decimal("0.00001"),
            max_quantity=Decimal("9000.0"),
            min_notional=Decimal("5.0"),
            exchange=self._name,
        )

    def get_symbol_filters(self, symbol: str) -> SymbolFilterDTO:
        self.call_counts["get_symbol_filters"] += 1
        if self.should_fail:
            raise self.fail_error
        return self._make_symbol_filter(symbol)

    def get_exchange_info(self) -> ExchangeInfoDTO:
        self.call_counts["get_exchange_info"] += 1
        if self.should_fail:
            raise self.fail_error
        f = self._make_symbol_filter("BTC/USDT")
        return ExchangeInfoDTO(
            exchange=self._name,
            server_time=datetime.now(timezone.utc),
            symbols=(f,),
        )


class TestMarketDataProviderManager(unittest.TestCase):
    """Unit tests for MarketDataProviderManager."""

    def setUp(self) -> None:
        self.registry = InMemoryProviderRegistry()
        self.primary = MockExchangeProvider(name="primary_binance")
        self.secondary = MockExchangeProvider(name="secondary_coinbase")
        self.registry.register(self.primary, priority=1)
        self.registry.register(self.secondary, priority=2)

        self.manager = DefaultMarketDataProviderManager(
            registry=self.registry,
            metadata_cache_ttl_seconds=3600,
            circuit_failure_threshold=3,
            circuit_cooldown_seconds=0.1,  # Short cooldown for test efficiency
        )

    def test_protocol_conformance(self) -> None:
        """Verify DefaultMarketDataProviderManager implements protocol."""
        self.assertIsInstance(self.manager, MarketDataProviderManager)

    def test_get_quote_routes_to_primary_provider(self) -> None:
        """get_quote invokes highest priority provider and returns QuoteDTO."""
        quote = self.manager.get_quote("BTC/USDT")
        self.assertIsInstance(quote, QuoteDTO)
        self.assertEqual(quote.price, Decimal("88000.00"))
        self.assertEqual(quote.provider, "primary_binance")
        self.assertEqual(self.primary.call_counts["get_quote"], 1)
        self.assertEqual(self.secondary.call_counts["get_quote"], 0)

    def test_get_ohlcv_routes_successfully(self) -> None:
        """get_ohlcv fetches valid series with UTC validation."""
        start = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
        end = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        series = self.manager.get_ohlcv("BTC/USDT", Timeframe.H1, start, end)
        self.assertIsInstance(series, OHLCVSeriesDTO)
        self.assertEqual(len(series.candles), 1)
        self.assertEqual(self.primary.call_counts["get_ohlcv"], 1)

    def test_get_ohlcv_rejects_naive_or_reversed_dates(self) -> None:
        """Date validations for OHLCV queries."""
        start_naive = datetime(2026, 11, 9, 10, 0)
        end_utc = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            self.manager.get_ohlcv("BTC/USDT", Timeframe.H1, start_naive, end_utc)

        start_late = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
        end_early = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            self.manager.get_ohlcv("BTC/USDT", Timeframe.H1, start_late, end_early)

    def test_get_orderbook_and_funding_rate(self) -> None:
        """Orderbook and funding rate routing."""
        book = self.manager.get_orderbook("BTC/USDT", depth=10)
        self.assertIsInstance(book, OrderBookDTO)
        self.assertEqual(self.primary.call_counts["get_orderbook"], 1)

        fr = self.manager.get_funding_rate("BTC/USDT")
        self.assertIsInstance(fr, FundingRateDTO)
        self.assertEqual(self.primary.call_counts["get_funding_rate"], 1)

    def test_static_exchange_metadata_caching(self) -> None:
        """Symbol filters and exchange info are cached; live data is not cached."""
        # 1. First call queries provider
        f1 = self.manager.get_symbol_filters("BTC/USDT")
        self.assertEqual(self.primary.call_counts["get_symbol_filters"], 1)

        # 2. Second call returns cached filter without querying provider again
        f2 = self.manager.get_symbol_filters("BTC/USDT")
        self.assertEqual(self.primary.call_counts["get_symbol_filters"], 1)
        self.assertEqual(f1, f2)

        # 3. Exchange info is also cached
        info1 = self.manager.get_exchange_info("primary_binance")
        self.assertEqual(self.primary.call_counts["get_exchange_info"], 1)
        info2 = self.manager.get_exchange_info("primary_binance")
        self.assertEqual(self.primary.call_counts["get_exchange_info"], 1)

        # 4. clear_metadata_cache evicts cached items
        self.manager.clear_metadata_cache()
        _ = self.manager.get_symbol_filters("BTC/USDT")
        self.assertEqual(self.primary.call_counts["get_symbol_filters"], 2)

        # 5. Live market data is NEVER cached
        _ = self.manager.get_quote("BTC/USDT")
        _ = self.manager.get_quote("BTC/USDT")
        self.assertEqual(self.primary.call_counts["get_quote"], 2)

    def test_automatic_failover_when_primary_fails(self) -> None:
        """Manager fails over to secondary candidate when primary raises error."""
        self.primary.should_fail = True

        quote = self.manager.get_quote("BTC/USDT")
        self.assertEqual(quote.provider, "secondary_coinbase")
        self.assertEqual(self.primary.call_counts["get_quote"], 1)
        self.assertEqual(self.secondary.call_counts["get_quote"], 1)

        # Health tracking should reflect failure on primary and success on secondary
        primary_health = self.manager.get_provider_health("primary_binance")
        self.assertIsNotNone(primary_health)
        self.assertEqual(primary_health.failure_count, 1)

        secondary_health = self.manager.get_provider_health("secondary_coinbase")
        self.assertIsNotNone(secondary_health)
        self.assertEqual(secondary_health.total_successes, 1)

    def test_circuit_breaker_trips_to_open_after_consecutive_failures(self) -> None:
        """Circuit breaker opens after reaching failure threshold."""
        self.primary.should_fail = True

        # Cause 3 failures on primary
        for _ in range(3):
            _ = self.manager.get_quote("BTC/USDT")

        health = self.manager.get_provider_health("primary_binance")
        self.assertIsNotNone(health)
        self.assertEqual(health.circuit_state, CircuitState.OPEN)
        self.assertEqual(health.status, HealthState.UNHEALTHY)

        # On next call, primary should be skipped immediately without calling it
        count_before = self.primary.call_counts["get_quote"]
        _ = self.manager.get_quote("BTC/USDT")
        self.assertEqual(self.primary.call_counts["get_quote"], count_before)

    def test_diagnostic_health_check(self) -> None:
        """health_check audits all registered providers."""
        statuses = self.manager.health_check()
        self.assertEqual(len(statuses), 2)
        names = [s.provider_name for s in statuses]
        self.assertIn("primary_binance", names)
        self.assertIn("secondary_coinbase", names)

    def test_all_candidates_failed_raises_no_market_data_error(self) -> None:
        """When all candidate providers fail, NoMarketDataError is raised."""
        self.primary.should_fail = True
        self.secondary.should_fail = True

        with self.assertRaises(NoMarketDataError):
            self.manager.get_quote("BTC/USDT")


if __name__ == "__main__":
    unittest.main()
