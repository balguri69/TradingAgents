"""Comprehensive unit tests for YahooFinanceProvider and multi-asset routing."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import unittest

from tradingagents.dataflows.contracts.provider import ExchangeProvider, MarketDataProvider
from tradingagents.dataflows.contracts.transport import TimeoutConfig, TransportClient
from tradingagents.dataflows.dto.market_data import (
    CandleDTO,
    ExchangeInfoDTO,
    OHLCVSeriesDTO,
    QuoteDTO,
    SymbolFilterDTO,
)
from tradingagents.dataflows.dto.telemetry import (
    HealthStatusDTO,
    RequestMetricsDTO,
    TransportResponse,
)
from tradingagents.dataflows.enums import HealthState, Timeframe
from tradingagents.dataflows.exceptions import (
    NoMarketDataError,
    VendorError,
    VendorRateLimitError,
    VendorUnavailableError,
)
from tradingagents.dataflows.manager import DefaultMarketDataProviderManager
from tradingagents.dataflows.providers.binance import BinanceProvider
from tradingagents.dataflows.providers.yahoo import YahooFinanceProvider
from tradingagents.dataflows.registry import InMemoryProviderRegistry


class MockTransportClient(TransportClient):
    """Controllable mock transport client for Yahoo Finance endpoint testing."""

    def __init__(self) -> None:
        self.responses: dict[str, TransportResponse] = {}
        self.calls: list[dict[str, Any]] = []

    def set_response(
        self,
        url_substr: str,
        status_code: int = 200,
        data: Any = None,
        latency_ms: Decimal = Decimal("4.5"),
    ) -> None:
        self.responses[url_substr] = TransportResponse(
            status_code=status_code,
            data=data if data is not None else {},
            headers={"Content-Type": "application/json"},
            latency_ms=latency_ms,
        )

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: TimeoutConfig | tuple[float, float] | float | None = None,
        **kwargs: Any,
    ) -> TransportResponse:
        self.calls.append({"url": url, "params": params, "headers": headers})
        for substr, resp in self.responses.items():
            if substr in url:
                if resp.status_code == 404:
                    raise NoMarketDataError(f"HTTP 404 on {url}")
                if resp.status_code == 429:
                    raise VendorRateLimitError(f"HTTP 429 on {url}")
                if resp.status_code >= 500:
                    raise VendorUnavailableError(f"HTTP {resp.status_code} on {url}")
                return resp
        return TransportResponse(
            status_code=200,
            data={},
            headers={"Content-Type": "application/json"},
            latency_ms=Decimal("1.0"),
        )


class TestYahooFinanceProvider(unittest.TestCase):
    """Unit tests for YahooFinanceProvider."""

    def setUp(self) -> None:
        self.mock_transport = MockTransportClient()
        self.provider = YahooFinanceProvider(transport=self.mock_transport)

    def test_protocol_and_contract_conformance(self) -> None:
        """Verify YahooFinanceProvider satisfies ExchangeProvider contract."""
        self.assertIsInstance(self.provider, ExchangeProvider)
        self.assertIsInstance(self.provider, MarketDataProvider)
        self.assertEqual(self.provider.provider_name, "yahoo")
        self.assertTrue(self.provider.capabilities.quote)
        self.assertTrue(self.provider.capabilities.ohlcv)
        self.assertFalse(self.provider.capabilities.orderbook)
        self.assertFalse(self.provider.capabilities.funding_rate)
        self.assertTrue(self.provider.supports_feature("quote"))
        self.assertTrue(self.provider.supports_feature("ohlcv"))
        self.assertFalse(self.provider.supports_feature("funding_rate"))
        self.assertIn("XAU/USD", self.provider.get_supported_symbols())
        self.assertIn("USD/JPY", self.provider.get_supported_symbols())

    def test_health_check_healthy(self) -> None:
        """health_check returns HEALTHY when chart probe succeeds."""
        payload = {"chart": {"result": [{"meta": {"regularMarketPrice": 5900.0}}]}}
        self.mock_transport.set_response("/v8/finance/chart/%5EGSPC", status_code=200, data=payload)
        health = self.provider.health_check()
        self.assertEqual(health.state, HealthState.HEALTHY)
        self.assertEqual(health.provider_name, "yahoo")

    def test_health_check_unhealthy(self) -> None:
        """health_check returns UNHEALTHY when transport fails."""
        self.mock_transport.set_response(
            "/v8/finance/chart/%5EGSPC", status_code=503, data={"error": "Service unavailable"}
        )
        health = self.provider.health_check()
        self.assertEqual(health.state, HealthState.UNHEALTHY)
        self.assertIsNotNone(health.error_message)

    def test_get_quote_gold_success(self) -> None:
        """get_quote fetches and converts Gold COMEX quote (GC=F)."""
        payload = {
            "quoteResponse": {
                "result": [
                    {
                        "symbol": "GC=F",
                        "regularMarketPrice": 2685.50,
                        "bid": 2685.40,
                        "ask": 2685.60,
                        "bidSize": 10,
                        "askSize": 15,
                        "regularMarketVolume": 145000,
                        "regularMarketTime": 1731154800,
                    }
                ]
            }
        }
        self.mock_transport.set_response("/v7/finance/quote", status_code=200, data=payload)

        quote = self.provider.get_quote("XAUUSD")
        self.assertIsInstance(quote, QuoteDTO)
        self.assertEqual(quote.symbol, "XAU/USD")
        self.assertEqual(quote.price, Decimal("2685.50"))
        self.assertEqual(quote.bid, Decimal("2685.40"))
        self.assertEqual(quote.ask, Decimal("2685.60"))
        self.assertEqual(quote.volume_24h, Decimal("145000"))
        self.assertEqual(quote.provider, "yahoo")

    def test_get_quote_forex_usdjpy_success(self) -> None:
        """get_quote fetches and converts USD/JPY forex quote."""
        payload = {
            "quoteResponse": {
                "result": [
                    {
                        "symbol": "USDJPY=X",
                        "regularMarketPrice": 152.85,
                        "bid": 152.84,
                        "ask": 152.86,
                        "regularMarketTime": 1731154800,
                    }
                ]
            }
        }
        self.mock_transport.set_response("/v7/finance/quote", status_code=200, data=payload)

        quote = self.provider.get_quote("USDJPY")
        self.assertEqual(quote.symbol, "USD/JPY")
        self.assertEqual(quote.price, Decimal("152.85"))
        self.assertEqual(quote.bid, Decimal("152.84"))
        self.assertEqual(quote.ask, Decimal("152.86"))

    def test_get_quote_stocks_and_indices(self) -> None:
        """get_quote fetches equity (AAPL) and index (^GSPC) quotes."""
        payload = {
            "quoteResponse": {
                "result": [
                    {
                        "symbol": "AAPL",
                        "regularMarketPrice": 225.50,
                        "bid": 225.45,
                        "ask": 225.55,
                        "regularMarketVolume": 45000000,
                        "regularMarketTime": 1731154800,
                    }
                ]
            }
        }
        self.mock_transport.set_response("/v7/finance/quote", status_code=200, data=payload)

        quote = self.provider.get_quote("AAPL")
        self.assertEqual(quote.symbol, "AAPL")
        self.assertEqual(quote.price, Decimal("225.50"))

    def test_get_quote_chart_fallback_when_quote_empty(self) -> None:
        """get_quote falls back to chart meta block if quote endpoint has empty result."""
        empty_quote_payload = {"quoteResponse": {"result": []}}
        chart_payload = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": "GC=F",
                            "regularMarketPrice": 2680.00,
                            "regularMarketTime": 1731154800,
                            "regularMarketVolume": 10000,
                        }
                    }
                ]
            }
        }
        self.mock_transport.set_response("/v7/finance/quote", status_code=200, data=empty_quote_payload)
        self.mock_transport.set_response("/v8/finance/chart/GC%3DF", status_code=200, data=chart_payload)

        quote = self.provider.get_quote("XAUUSD")
        self.assertEqual(quote.price, Decimal("2680.00"))
        self.assertEqual(quote.symbol, "XAU/USD")

    def test_get_ohlcv_gold_success(self) -> None:
        """get_ohlcv parses candlesticks and skips null bars."""
        payload = {
            "chart": {
                "result": [
                    {
                        "timestamp": [1731150000, 1731153600, 1731157200],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [2680.0, None, 2684.0],
                                    "high": [2688.0, None, 2692.0],
                                    "low": [2678.0, None, 2682.0],
                                    "close": [2685.0, None, 2690.0],
                                    "volume": [1200, None, 1800],
                                }
                            ]
                        },
                    }
                ]
            }
        }
        self.mock_transport.set_response("/v8/finance/chart/GC%3DF", status_code=200, data=payload)

        start = datetime(2024, 11, 9, 10, 0, tzinfo=timezone.utc)
        end = datetime(2024, 11, 9, 13, 0, tzinfo=timezone.utc)
        series = self.provider.get_ohlcv("XAUUSD", Timeframe.H1, start, end)

        self.assertIsInstance(series, OHLCVSeriesDTO)
        self.assertEqual(series.symbol, "XAU/USD")
        # Middle bar was null and should be skipped
        self.assertEqual(len(series.candles), 2)
        self.assertEqual(series.candles[0].open, Decimal("2680.0"))
        self.assertEqual(series.candles[0].close, Decimal("2685.0"))
        self.assertEqual(series.candles[1].open, Decimal("2684.0"))

    def test_get_symbol_filters_tradfi(self) -> None:
        """get_symbol_filters returns instrument specific tick sizes and precisions."""
        gold_filter = self.provider.get_symbol_filters("XAUUSD")
        self.assertEqual(gold_filter.tick_size, Decimal("0.10"))
        self.assertEqual(gold_filter.price_precision, 2)

        jpy_filter = self.provider.get_symbol_filters("USDJPY")
        self.assertEqual(jpy_filter.tick_size, Decimal("0.001"))
        self.assertEqual(jpy_filter.price_precision, 3)

        eur_filter = self.provider.get_symbol_filters("EURUSD")
        self.assertEqual(eur_filter.tick_size, Decimal("0.0001"))
        self.assertEqual(eur_filter.price_precision, 5)

        stock_filter = self.provider.get_symbol_filters("AAPL")
        self.assertEqual(stock_filter.tick_size, Decimal("0.01"))
        self.assertEqual(stock_filter.price_precision, 2)

    def test_get_exchange_info(self) -> None:
        """get_exchange_info returns standard TradFi catalog."""
        info = self.provider.get_exchange_info()
        self.assertIsInstance(info, ExchangeInfoDTO)
        self.assertEqual(info.exchange, "yahoo")
        self.assertGreater(len(info.symbols), 3)

    def test_get_orderbook_raises_not_implemented(self) -> None:
        """Yahoo does not offer L2 books and raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.provider.get_orderbook("XAUUSD")

    def test_error_translation_http_statuses(self) -> None:
        """HTTP errors are translated into domain exceptions."""
        self.mock_transport.set_response("/v7/finance/quote", status_code=404, data={})
        with self.assertRaises(NoMarketDataError):
            self.provider.get_quote("XAUUSD")

        self.mock_transport.set_response("/v7/finance/quote", status_code=429, data={})
        with self.assertRaises(VendorRateLimitError):
            self.provider.get_quote("XAUUSD")

        self.mock_transport.set_response("/v7/finance/quote", status_code=500, data={})
        with self.assertRaises(VendorUnavailableError):
            self.provider.get_quote("XAUUSD")


class TestMultiAssetOrchestrationIntegration(unittest.TestCase):
    """Integration test verifying MarketDataProviderManager routes across Binance and Yahoo."""

    def setUp(self) -> None:
        self.registry = InMemoryProviderRegistry()

        # In-memory mock transport for Binance
        self.binance_transport = MockTransportClient()
        self.binance_provider = BinanceProvider(transport=self.binance_transport)
        self.registry.register(self.binance_provider, priority=1)

        # In-memory mock transport for Yahoo
        self.yahoo_transport = MockTransportClient()
        self.yahoo_provider = YahooFinanceProvider(transport=self.yahoo_transport)
        self.registry.register(self.yahoo_provider, priority=2)

        self.manager = DefaultMarketDataProviderManager(registry=self.registry)

    def test_routing_crypto_to_binance(self) -> None:
        """BTC/USDT routes to Binance (priority 1)."""
        payload = {
            "symbol": "BTCUSDT",
            "lastPrice": "88000.00",
            "bidPrice": "87999.00",
            "askPrice": "88001.00",
            "bidQty": "1.0",
            "askQty": "1.0",
            "volume": "1000.0",
            "closeTime": 1731154800000,
        }
        self.binance_transport.set_response("/api/v3/ticker/24hr", status_code=200, data=payload)

        quote = self.manager.get_quote("BTC/USDT")
        self.assertEqual(quote.provider, "binance")
        self.assertEqual(quote.price, Decimal("88000.00"))

    def test_routing_gold_and_forex_to_yahoo(self) -> None:
        """Gold (XAUUSD) and Forex (USDJPY) route to Yahoo Finance."""
        gold_payload = {
            "quoteResponse": {
                "result": [
                    {
                        "symbol": "GC=F",
                        "regularMarketPrice": 2685.00,
                        "bid": 2684.90,
                        "ask": 2685.10,
                        "regularMarketTime": 1731154800,
                    }
                ]
            }
        }
        self.yahoo_transport.set_response("/v7/finance/quote", status_code=200, data=gold_payload)

        quote = self.manager.get_quote("XAUUSD")
        self.assertEqual(quote.provider, "yahoo")
        self.assertEqual(quote.symbol, "XAU/USD")
        self.assertEqual(quote.price, Decimal("2685.00"))

    def test_capability_routing_funding_rate_only_to_binance(self) -> None:
        """Funding rate queries route exclusively to providers supporting funding_rate."""
        fr_payload = {
            "symbol": "BTCUSDT",
            "lastFundingRate": "0.0001",
            "markPrice": "88000.00",
            "nextFundingTime": 1731168000000,
        }
        self.binance_transport.set_response("/fapi/v1/premiumIndex", status_code=200, data=fr_payload)

        fr = self.manager.get_funding_rate("BTC/USDT")
        self.assertEqual(fr.exchange, "binance")

        # Querying funding rate for Gold should raise NoMarketDataError (no candidate supports it)
        with self.assertRaises(NoMarketDataError):
            self.manager.get_funding_rate("XAUUSD")


if __name__ == "__main__":
    unittest.main()
