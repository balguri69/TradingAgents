"""Comprehensive unit tests for InMemoryProviderRegistry and Economic Calendar interfaces."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import threading
import unittest

from tradingagents.dataflows.contracts.capabilities import (
    ProviderCapabilities,
    ProviderMetadata,
)
from tradingagents.dataflows.contracts.economic_calendar import EconomicCalendarProvider
from tradingagents.dataflows.contracts.provider import MarketDataProvider
from tradingagents.dataflows.contracts.registry import ProviderRegistry
from tradingagents.dataflows.dto.economic_calendar import (
    EconomicImpact,
    EconomicReleaseDTO,
)
from tradingagents.dataflows.dto.market_data import (
    FundingRateDTO,
    OHLCVSeriesDTO,
    OrderBookDTO,
    QuoteDTO,
)
from tradingagents.dataflows.dto.telemetry import HealthStatusDTO
from tradingagents.dataflows.enums import HealthState, Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.registry import InMemoryProviderRegistry


class DummyProvider(MarketDataProvider):
    """Configurable dummy provider for testing registry mechanics."""

    def __init__(
        self,
        name: str,
        symbols: tuple[str, ...],
        features: tuple[str, ...],
        raises_on_feature: bool = False,
        raises_on_symbols: bool = False,
    ) -> None:
        self._name = name
        self._symbols = symbols
        self._features = frozenset(f.lower() for f in features)
        self._raises_on_feature = raises_on_feature
        self._raises_on_symbols = raises_on_symbols

    @property
    def provider_name(self) -> str:
        return self._name

    def get_supported_symbols(self) -> tuple[str, ...]:
        if self._raises_on_symbols:
            raise RuntimeError("Vendor symbol catalogue error")
        return self._symbols

    @property
    def capabilities(self) -> ProviderCapabilities:
        if self._raises_on_feature:
            raise RuntimeError("Vendor feature matrix failure")
        return ProviderCapabilities(
            quote="quote" in self._features,
            ohlcv="ohlcv" in self._features,
            orderbook="orderbook" in self._features,
            funding_rate="funding_rate" in self._features,
            open_interest="open_interest" in self._features,
            macro="macro" in self._features,
            economic_calendar="economic_calendar" in self._features,
            news="news" in self._features,
        )

    def supports_feature(self, feature_name: str) -> bool:
        if self._raises_on_feature:
            raise RuntimeError("Vendor feature matrix failure")
        return feature_name.lower() in self._features

    def health_check(self) -> HealthStatusDTO:
        return HealthStatusDTO(
            provider_name=self._name,
            state=HealthState.HEALTHY,
            latency_ms=Decimal("1.5"),
            last_successful_query=datetime.now(timezone.utc),
        )

    def get_quote(self, symbol: str, as_of: datetime | None = None) -> QuoteDTO:
        raise NotImplementedError

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_date: datetime,
        end_date: datetime,
    ) -> OHLCVSeriesDTO:
        raise NotImplementedError

    def get_orderbook(
        self, symbol: str, depth: int = 20, as_of: datetime | None = None
    ) -> OrderBookDTO:
        raise NotImplementedError


class TestInMemoryProviderRegistry(unittest.TestCase):
    """Unit tests for ProviderRegistry implementation."""

    def setUp(self) -> None:
        self.registry = InMemoryProviderRegistry()
        self.binance = DummyProvider(
            name="binance",
            symbols=("BTC/USDT", "ETH/USDT", "SOL/USDT"),
            features=("quote", "ohlcv", "orderbook", "funding_rate"),
        )
        self.coinbase = DummyProvider(
            name="coinbase",
            symbols=("BTC-USD", "ETH-USD"),
            features=("quote", "ohlcv", "orderbook"),
        )
        self.yahoo = DummyProvider(
            name="yahoo",
            symbols=("GC=F", "USDJPY=X", "BTC-USD", "SPY"),
            features=("quote", "ohlcv", "news"),
        )
        self.universal = DummyProvider(
            name="universal_macro",
            symbols=("*",),
            features=("macro", "economic_calendar"),
        )

    def test_implements_provider_registry_protocol(self) -> None:
        """Verify registry conforms to runtime checkable Protocol."""
        self.assertIsInstance(self.registry, ProviderRegistry)

    def test_registration_and_retrieval(self) -> None:
        """Registering a valid provider allows retrieval by name."""
        self.registry.register(self.binance, priority=1)
        self.assertEqual(len(self.registry), 1)
        self.assertIn("binance", self.registry)
        self.assertIn("BINANCE", self.registry)  # case-insensitive check

        retrieved = self.registry.get_provider("binance")
        self.assertIs(retrieved, self.binance)
        self.assertEqual(self.registry.get_priority("binance"), 1)

    def test_register_duplicate_raises_without_overwrite(self) -> None:
        """Duplicate registration without overwrite raises ValueError."""
        self.registry.register(self.binance, priority=10)
        with self.assertRaises(ValueError) as ctx:
            self.registry.register(self.binance, priority=5)
        self.assertIn("already registered", str(ctx.exception))

    def test_register_with_overwrite_updates_priority(self) -> None:
        """Registering with overwrite=True successfully updates registration."""
        self.registry.register(self.binance, priority=10)
        self.registry.register(self.binance, priority=2, overwrite=True)
        self.assertEqual(self.registry.get_priority("binance"), 2)

    def test_register_validation_checks(self) -> None:
        """Invalid providers or priorities are rejected."""
        with self.assertRaises(ValueError):
            self.registry.register(None)  # type: ignore

        with self.assertRaises(ValueError):
            self.registry.register(self.binance, priority=0)

        with self.assertRaises(ValueError):
            self.registry.register(self.binance, priority=-5)

        class MissingNameProvider:
            def supports_feature(self, f: str) -> bool:
                return True
            def get_supported_symbols(self) -> tuple[str, ...]:
                return ()

        with self.assertRaises(ValueError):
            self.registry.register(MissingNameProvider())  # type: ignore

        class IncompleteProvider:
            provider_name = "incomplete"

        with self.assertRaises(TypeError):
            self.registry.register(IncompleteProvider())  # type: ignore

    def test_unregistration(self) -> None:
        """Unregister removes provider and returns True; nonexistent returns False."""
        self.registry.register(self.binance, priority=1)
        self.assertTrue(self.registry.unregister("binance"))
        self.assertEqual(len(self.registry), 0)
        self.assertIsNone(self.registry.get_provider("binance"))
        self.assertFalse(self.registry.unregister("nonexistent"))

    def test_list_providers_sorted_by_priority(self) -> None:
        """list_providers orders by priority ascending (1 before 10)."""
        self.registry.register(self.yahoo, priority=5)
        self.registry.register(self.binance, priority=1)
        self.registry.register(self.coinbase, priority=2)

        ordered = self.registry.list_providers()
        self.assertEqual(ordered, ("binance", "coinbase", "yahoo"))

    def test_get_candidates_symbol_and_feature_routing(self) -> None:
        """get_candidates returns providers supporting both symbol and feature in priority order."""
        self.registry.register(self.yahoo, priority=5)
        self.registry.register(self.binance, priority=1)
        self.registry.register(self.coinbase, priority=2)

        # BTC quote: binance (1), coinbase (2), yahoo (5) all support it
        candidates = self.registry.get_candidates("BTC/USDT", "quote")
        candidate_names = [p.provider_name for p in candidates]
        self.assertEqual(candidate_names, ["binance", "coinbase", "yahoo"])

        # Funding rate: only binance supports funding_rate
        fr_candidates = self.registry.get_candidates("BTC/USDT", "funding_rate")
        self.assertEqual(len(fr_candidates), 1)
        self.assertEqual(fr_candidates[0].provider_name, "binance")

        # Gold GC=F: only yahoo supports it
        gold_candidates = self.registry.get_candidates("XAUUSD", "quote")
        self.assertEqual(len(gold_candidates), 1)
        self.assertEqual(gold_candidates[0].provider_name, "yahoo")

    def test_wildcard_symbol_matching(self) -> None:
        """Universal provider with '*' symbol matches any symbol for supported features."""
        self.registry.register(self.universal, priority=1)
        candidates = self.registry.get_candidates("BTC/USDT", "economic_calendar")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].provider_name, "universal_macro")

    def test_provider_exception_isolation_during_discovery(self) -> None:
        """Buggy provider throwing during feature/symbol query does not crash discovery."""
        buggy_feature = DummyProvider("buggy1", ("BTC/USDT",), ("quote",), raises_on_feature=True)
        buggy_symbols = DummyProvider("buggy2", ("BTC/USDT",), ("quote",), raises_on_symbols=True)

        self.registry.register(buggy_feature, priority=1)
        self.registry.register(buggy_symbols, priority=2)
        self.registry.register(self.binance, priority=3)

        # Discovery should isolate buggy providers and still return binance
        candidates = self.registry.get_candidates("BTC/USDT", "quote")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].provider_name, "binance")

    def test_get_providers_for_symbol_and_feature(self) -> None:
        """Test auxiliary lookup methods."""
        self.registry.register(self.binance, priority=1)
        self.registry.register(self.yahoo, priority=2)

        by_sym = self.registry.get_providers_for_symbol("USDJPY")
        self.assertEqual(len(by_sym), 1)
        self.assertEqual(by_sym[0].provider_name, "yahoo")

        by_feat = self.registry.get_providers_for_feature("funding_rate")
        self.assertEqual(len(by_feat), 1)
        self.assertEqual(by_feat[0].provider_name, "binance")

    def test_get_supported_symbols_and_features_all(self) -> None:
        """Aggregated catalogue of symbols and features."""
        self.registry.register(self.binance, priority=1)
        self.registry.register(self.yahoo, priority=2)

        symbols = self.registry.get_supported_symbols_all()
        self.assertIn("BTC/USDT", symbols)
        self.assertIn("GC=F", symbols)

        features = self.registry.get_supported_features_all()
        self.assertIn("quote", features)
        self.assertIn("funding_rate", features)
        self.assertIn("news", features)

    def test_thread_safety_concurrent_access(self) -> None:
        """Test that concurrent registrations and lookups do not deadlock or raise."""
        num_threads = 8
        ops_per_thread = 50
        errors: list[Exception] = []

        def worker(tid: int) -> None:
            try:
                for i in range(ops_per_thread):
                    p = DummyProvider(f"prov_{tid}_{i}", ("BTC/USDT",), ("quote",))
                    self.registry.register(p, priority=tid + 1)
                    _ = self.registry.get_candidates("BTC/USDT", "quote")
                    _ = self.registry.list_providers()
                    self.registry.unregister(f"prov_{tid}_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


class TestEconomicCalendarContract(unittest.TestCase):
    """Unit tests for reserved Economic Calendar DTOs and contracts."""

    def test_valid_economic_release_dto(self) -> None:
        """Valid economic release DTO creation and immutability."""
        release = EconomicReleaseDTO(
            event_id="FOMC-202611",
            title="FOMC Interest Rate Decision",
            country="US",
            currency="USD",
            event_time=datetime(2026, 11, 10, 19, 0, tzinfo=timezone.utc),
            impact=EconomicImpact.HIGH,
            actual=Decimal("4.50"),
            forecast=Decimal("4.50"),
            previous=Decimal("4.75"),
            unit="%",
            source="Federal Reserve",
        )
        self.assertEqual(release.event_id, "FOMC-202611")
        self.assertEqual(release.impact, EconomicImpact.HIGH)
        self.assertEqual(release.actual, Decimal("4.50"))

        with self.assertRaises(Exception):
            release.title = "Altered"  # type: ignore

    def test_economic_release_validation_failures(self) -> None:
        """Validation rules for EconomicReleaseDTO."""
        now_utc = datetime.now(timezone.utc)

        # Empty event_id
        with self.assertRaises(DTOValidationError):
            EconomicReleaseDTO(
                event_id="",
                title="CPI",
                country="US",
                currency="USD",
                event_time=now_utc,
            )

        # Naive datetime
        with self.assertRaises(DTOValidationError):
            EconomicReleaseDTO(
                event_id="CPI-01",
                title="CPI",
                country="US",
                currency="USD",
                event_time=datetime(2026, 11, 10, 12, 0),  # naive
            )

        # Float value instead of Decimal
        with self.assertRaises(DTOValidationError):
            EconomicReleaseDTO(
                event_id="CPI-01",
                title="CPI",
                country="US",
                currency="USD",
                event_time=now_utc,
                actual=3.2,  # type: ignore
            )

    def test_economic_calendar_provider_protocol(self) -> None:
        """Verify EconomicCalendarProvider is runtime checkable."""
        class MockCalendarProvider:
            @property
            def provider_name(self) -> str:
                return "fred_calendar"

            def get_economic_events(
                self,
                start_date: datetime,
                end_date: datetime,
                country: str | None = None,
                min_impact: str | None = None,
            ) -> tuple[EconomicReleaseDTO, ...]:
                return ()

        mock = MockCalendarProvider()
        self.assertIsInstance(mock, EconomicCalendarProvider)


if __name__ == "__main__":
    unittest.main()
