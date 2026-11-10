"""Unit tests for Refactored Provider Contracts, Protocols, DTOs, and Validations."""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts import (
    MarketDataProvider,
    MarketDataProviderManager,
    ProviderRegistry,
    TransportClient,
)
from tradingagents.dataflows.dto import (
    CandleDTO,
    FundingRateDTO,
    HealthStatusDTO,
    MacroDataPointDTO,
    MacroSeriesDTO,
    NewsArticleDTO,
    OHLCVSeriesDTO,
    OrderBookDTO,
    OrderBookLevelDTO,
    QuoteDTO,
    RequestMetricsDTO,
    SentimentScoreDTO,
    TransportResponse,
)
from tradingagents.dataflows.enums import CircuitState, HealthState, Timeframe
from tradingagents.dataflows.exceptions import (
    DTOValidationError,
    NoMarketDataError,
    TradingAgentsError,
    VendorError,
    VendorRateLimitError,
    VendorUnavailableError,
)


class TestEnums(unittest.TestCase):
    """Test standard data provider enums."""

    def test_timeframe_values(self):
        self.assertEqual(Timeframe.M1.value, "1m")
        self.assertEqual(Timeframe.M5.value, "5m")
        self.assertEqual(Timeframe.M15.value, "15m")
        self.assertEqual(Timeframe.H1.value, "1h")
        self.assertEqual(Timeframe.H4.value, "4h")
        self.assertEqual(Timeframe.D1.value, "1d")
        self.assertEqual(Timeframe.W1.value, "1w")

    def test_health_state_values(self):
        self.assertEqual(HealthState.HEALTHY.value, "healthy")
        self.assertEqual(HealthState.DEGRADED.value, "degraded")
        self.assertEqual(HealthState.UNHEALTHY.value, "unhealthy")

    def test_circuit_state_values(self):
        self.assertEqual(CircuitState.CLOSED.value, "closed")
        self.assertEqual(CircuitState.OPEN.value, "open")
        self.assertEqual(CircuitState.HALF_OPEN.value, "half_open")


class TestDTOImmutability(unittest.TestCase):
    """Verify that all DTOs enforce frozen immutability."""

    def setUp(self):
        self.now_utc = datetime.now(timezone.utc)

    def test_quote_dto_immutability(self):
        quote = QuoteDTO(
            symbol="BTC-USD",
            price=Decimal("68000.50"),
            bid=Decimal("67990.00"),
            ask=Decimal("68010.00"),
            bid_size=Decimal("1.5"),
            ask_size=Decimal("2.0"),
            volume_24h=Decimal("1200000000"),
            timestamp=self.now_utc,
            provider="binance",
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            quote.price = Decimal("70000.00")  # type: ignore

    def test_candle_dto_immutability(self):
        candle = CandleDTO(
            timestamp=self.now_utc,
            open=Decimal("100.0"),
            high=Decimal("105.0"),
            low=Decimal("99.0"),
            close=Decimal("104.0"),
            volume=Decimal("500.0"),
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            candle.close = Decimal("106.0")  # type: ignore

    def test_funding_rate_dto_immutability(self):
        fr = FundingRateDTO(
            symbol="BTCUSDT",
            funding_rate=Decimal("0.0001"),
            annualized_rate=Decimal("0.1095"),
            funding_time=self.now_utc,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            fr.funding_rate = Decimal("0.0002")  # type: ignore


class TestDTOEquality(unittest.TestCase):
    """Verify equality semantics across domain DTOs."""

    def setUp(self):
        self.now_utc = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)

    def test_quote_dto_equality(self):
        q1 = QuoteDTO(
            symbol="BTC-USD",
            price=Decimal("68000.00"),
            bid=Decimal("67995.00"),
            ask=Decimal("68005.00"),
            bid_size=Decimal("1.0"),
            ask_size=Decimal("1.0"),
            volume_24h=Decimal("5000000"),
            timestamp=self.now_utc,
            provider="binance",
        )
        q2 = QuoteDTO(
            symbol="BTC-USD",
            price=Decimal("68000.00"),
            bid=Decimal("67995.00"),
            ask=Decimal("68005.00"),
            bid_size=Decimal("1.0"),
            ask_size=Decimal("1.0"),
            volume_24h=Decimal("5000000"),
            timestamp=self.now_utc,
            provider="binance",
        )
        q3 = QuoteDTO(
            symbol="BTC-USD",
            price=Decimal("68001.00"),  # Different price
            bid=Decimal("67995.00"),
            ask=Decimal("68005.00"),
            bid_size=Decimal("1.0"),
            ask_size=Decimal("1.0"),
            volume_24h=Decimal("5000000"),
            timestamp=self.now_utc,
            provider="binance",
        )
        self.assertEqual(q1, q2)
        self.assertNotEqual(q1, q3)

    def test_candle_dto_equality(self):
        c1 = CandleDTO(self.now_utc, Decimal("100"), Decimal("110"), Decimal("90"), Decimal("105"), Decimal("1000"))
        c2 = CandleDTO(self.now_utc, Decimal("100"), Decimal("110"), Decimal("90"), Decimal("105"), Decimal("1000"))
        c3 = CandleDTO(self.now_utc, Decimal("100"), Decimal("110"), Decimal("90"), Decimal("106"), Decimal("1000"))
        self.assertEqual(c1, c2)
        self.assertNotEqual(c1, c3)


class TestDTOHashing(unittest.TestCase):
    """Verify that frozen DTOs can be hashed and stored in sets/dicts."""

    def test_dtos_in_set(self):
        now_utc = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
        c1 = CandleDTO(now_utc, Decimal("100"), Decimal("110"), Decimal("90"), Decimal("105"), Decimal("1000"))
        c2 = CandleDTO(now_utc, Decimal("100"), Decimal("110"), Decimal("90"), Decimal("105"), Decimal("1000"))
        c3 = CandleDTO(now_utc, Decimal("101"), Decimal("110"), Decimal("90"), Decimal("105"), Decimal("1000"))

        candle_set = {c1, c2, c3}
        self.assertEqual(len(candle_set), 2)  # c1 and c2 are identical, deduplicated
        self.assertIn(c1, candle_set)

    def test_quote_as_dict_key(self):
        now_utc = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
        q1 = QuoteDTO("BTC-USD", Decimal("68000"), Decimal("67990"), Decimal("68010"), Decimal("1"), Decimal("1"), Decimal("100"), now_utc)
        d = {q1: "cached_snapshot"}
        self.assertEqual(d[q1], "cached_snapshot")


class TestDTOSerialization(unittest.TestCase):
    """Verify dictionary serialization of DTOs."""

    def test_asdict_serialization(self):
        now_utc = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
        level = OrderBookLevelDTO(price=Decimal("68000.00"), quantity=Decimal("2.5"))
        ob = OrderBookDTO(
            symbol="BTC-USD",
            timestamp=now_utc,
            bids=(level,),
            asks=(level,),
            spread_bps=Decimal("1.5"),
            provider="coinbase",
        )
        as_dict = dataclasses.asdict(ob)
        self.assertEqual(as_dict["symbol"], "BTC-USD")
        self.assertEqual(as_dict["spread_bps"], Decimal("1.5"))
        self.assertEqual(len(as_dict["bids"]), 1)
        self.assertEqual(as_dict["bids"][0]["price"], Decimal("68000.00"))


class TestDTOValidationAndFinancialInvariants(unittest.TestCase):
    """Verify that financial domain invariants and timezone awareness are enforced."""

    def setUp(self):
        self.now_utc = datetime.now(timezone.utc)
        self.now_naive = datetime.now()  # Naive datetime (missing tzinfo)

    def test_quote_rejects_naive_datetime(self):
        with self.assertRaises(DTOValidationError) as ctx:
            QuoteDTO(
                symbol="BTC-USD",
                price=Decimal("68000"),
                bid=Decimal("67990"),
                ask=Decimal("68010"),
                bid_size=Decimal("1"),
                ask_size=Decimal("1"),
                volume_24h=Decimal("100"),
                timestamp=self.now_naive,
            )
        self.assertIn("must be timezone-aware", str(ctx.exception))

    def test_quote_rejects_non_decimal_price(self):
        with self.assertRaises(DTOValidationError) as ctx:
            QuoteDTO(
                symbol="BTC-USD",
                price=68000.50,  # type: ignore (float passed instead of Decimal)
                bid=Decimal("67990"),
                ask=Decimal("68010"),
                bid_size=Decimal("1"),
                ask_size=Decimal("1"),
                volume_24h=Decimal("100"),
                timestamp=self.now_utc,
            )
        self.assertIn("must be a Decimal", str(ctx.exception))

    def test_quote_rejects_negative_or_zero_price(self):
        for bad_price in (Decimal("0"), Decimal("-100")):
            with self.subTest(bad_price=bad_price):
                with self.assertRaises(DTOValidationError):
                    QuoteDTO("BTC-USD", bad_price, Decimal("0"), Decimal("10"), Decimal("1"), Decimal("1"), Decimal("10"), self.now_utc)

    def test_quote_rejects_crossed_bid_exceeding_ask(self):
        with self.assertRaises(DTOValidationError) as ctx:
            QuoteDTO(
                symbol="BTC-USD",
                price=Decimal("100"),
                bid=Decimal("105"),  # Bid higher than ask!
                ask=Decimal("95"),
                bid_size=Decimal("1"),
                ask_size=Decimal("1"),
                volume_24h=Decimal("100"),
                timestamp=self.now_utc,
            )
        self.assertIn("cannot exceed ask", str(ctx.exception))

    def test_candle_rejects_invalid_bounds(self):
        # low > high
        with self.assertRaises(DTOValidationError) as ctx:
            CandleDTO(self.now_utc, Decimal("100"), Decimal("95"), Decimal("105"), Decimal("100"), Decimal("10"))
        self.assertIn("low (105) cannot exceed high (95)", str(ctx.exception))

        # open > high
        with self.assertRaises(DTOValidationError) as ctx:
            CandleDTO(self.now_utc, Decimal("110"), Decimal("105"), Decimal("95"), Decimal("100"), Decimal("10"))
        self.assertIn("open (110) must be within", str(ctx.exception))

        # close < low
        with self.assertRaises(DTOValidationError) as ctx:
            CandleDTO(self.now_utc, Decimal("100"), Decimal("105"), Decimal("95"), Decimal("90"), Decimal("10"))
        self.assertIn("close (90) must be within", str(ctx.exception))

        # negative volume
        with self.assertRaises(DTOValidationError):
            CandleDTO(self.now_utc, Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100"), Decimal("-5"))

    def test_sentiment_score_bounds(self):
        # Out of bounds (< -1.0)
        with self.assertRaises(DTOValidationError):
            SentimentScoreDTO("BTC", self.now_utc, Decimal("-1.5"), 100, ("reddit",))

        # Out of bounds (> +1.0)
        with self.assertRaises(DTOValidationError):
            SentimentScoreDTO("BTC", self.now_utc, Decimal("1.2"), 100, ("reddit",))

        # Valid bounds
        valid = SentimentScoreDTO("BTC", self.now_utc, Decimal("0.75"), 500, ("stocktwits", "reddit"))
        self.assertEqual(valid.sentiment_index, Decimal("0.75"))


class TestProtocolsAndABCs(unittest.TestCase):
    """Verify structural subtyping (typing.Protocol) and ABC behavior."""

    def test_mock_transport_conforms_to_transport_client_protocol(self):
        class MockTransport:
            def execute_request(self, endpoint_url: str, params=None, headers=None, timeout=10.0):
                return TransportResponse(200, {}, {}, Decimal("12.5"))

        mock = MockTransport()
        self.assertIsInstance(mock, TransportClient)

    def test_mock_registry_conforms_to_provider_registry_protocol(self):
        class MockRegistry:
            def register(self, provider, priority=100) -> None: pass
            def get_provider(self, provider_name: str): return None
            def get_candidates(self, symbol: str, feature_name: str): return ()
            def list_providers(self): return ()

        mock = MockRegistry()
        self.assertIsInstance(mock, ProviderRegistry)

    def test_mock_manager_conforms_to_provider_manager_protocol(self):
        class MockManager:
            def get_quote(self, symbol, as_of=None): pass
            def get_ohlcv(self, symbol, timeframe, start_date, end_date): pass
            def get_orderbook(self, symbol, depth=20, as_of=None): pass
            def get_funding_rate(self, symbol, as_of=None): pass
            def health_check(self): return ()

        mock = MockManager()
        self.assertIsInstance(mock, MarketDataProviderManager)


class ConcreteProvider(MarketDataProvider):
    """Concrete provider for testing MarketDataProvider ABC."""

    @property
    def provider_name(self) -> str:
        return "concrete_test"

    def get_supported_symbols(self) -> Sequence[str]:
        return ["BTC-USD"]

    def supports_feature(self, feature_name: str) -> bool:
        return feature_name == "quote"

    def health_check(self) -> HealthStatusDTO:
        return HealthStatusDTO("concrete_test", HealthState.HEALTHY, Decimal("5.0"), datetime.now(timezone.utc))

    def get_quote(self, symbol: str, as_of=None) -> QuoteDTO:
        now_utc = datetime.now(timezone.utc)
        return QuoteDTO(symbol, Decimal("100"), Decimal("99"), Decimal("101"), Decimal("1"), Decimal("1"), Decimal("10"), now_utc)

    def get_ohlcv(self, symbol: str, timeframe, start_date, end_date) -> OHLCVSeriesDTO:
        return OHLCVSeriesDTO(symbol, timeframe, ())

    def get_orderbook(self, symbol: str, depth=20, as_of=None) -> OrderBookDTO:
        return OrderBookDTO(symbol, datetime.now(timezone.utc), (), (), Decimal("0"))


class TestProviderContractBehavior(unittest.TestCase):
    """Test concrete provider and default funding rate behavior."""

    def test_default_funding_rate_raises_not_implemented(self):
        provider = ConcreteProvider()
        with self.assertRaises(NotImplementedError) as ctx:
            provider.get_funding_rate("BTC-USD")
        self.assertIn("does not support perpetual funding rates", str(ctx.exception))


class TestExceptionHierarchy(unittest.TestCase):
    """Verify dataflow exceptions hierarchy."""

    def test_dto_validation_error_hierarchy(self):
        err = DTOValidationError("Invalid price")
        self.assertIsInstance(err, ValueError)
        self.assertIsInstance(err, TradingAgentsError)

    def test_vendor_rate_limit_error_hierarchy(self):
        err = VendorRateLimitError("Rate limit exceeded")
        self.assertIsInstance(err, VendorUnavailableError)
        self.assertIsInstance(err, VendorError)


if __name__ == "__main__":
    unittest.main()
