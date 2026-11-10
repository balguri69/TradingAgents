"""Comprehensive unit tests for BinanceProvider and related DTOs."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import unittest

from tradingagents.dataflows.contracts.provider import MarketDataProvider
from tradingagents.dataflows.contracts.transport import TimeoutConfig, TransportClient
from tradingagents.dataflows.dto.market_data import (
    CandleDTO,
    ExchangeInfoDTO,
    FundingRateDTO,
    MarkPriceDTO,
    OHLCVSeriesDTO,
    OpenInterestDTO,
    OrderBookDTO,
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
    DTOValidationError,
    NoMarketDataError,
    VendorError,
    VendorRateLimitError,
    VendorUnavailableError,
)
from tradingagents.dataflows.providers.binance import BinanceProvider
from tradingagents.dataflows.registry import InMemoryProviderRegistry


class MockTransportClient(TransportClient):
    """Controllable mock transport client for testing provider responses."""

    def __init__(self) -> None:
        self.responses: dict[str, TransportResponse] = {}
        self.handlers: dict[str, Any] = {}
        self.calls: list[dict[str, Any]] = []

    def set_handler(self, url_substr: str, handler: Any) -> None:
        self.handlers[url_substr] = handler

    def set_response(
        self,
        url_substr: str,
        status_code: int = 200,
        body: Any = None,
        latency_ms: Decimal = Decimal("5.0"),
    ) -> None:
        data: Any
        if isinstance(body, (dict, list)):
            data = body
        elif isinstance(body, str):
            try:
                data = json.loads(body)
            except Exception:
                data = body
        else:
            data = body if body is not None else {}

        self.responses[url_substr] = TransportResponse(
            status_code=status_code,
            data=data,
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
        for substr, handler in self.handlers.items():
            if substr in url:
                return handler(url, params or {})
        for substr, resp in self.responses.items():
            if substr in url:
                if resp.status_code == 404:
                    raise NoMarketDataError(f"HTTP 404 on {url}")
                if resp.status_code == 429:
                    raise VendorRateLimitError(f"HTTP 429 on {url}")
                if resp.status_code >= 500:
                    raise VendorUnavailableError(f"HTTP {resp.status_code} on {url}")
                return resp
        # Default empty 200 response
        return TransportResponse(
            status_code=200,
            data={},
            headers={"Content-Type": "application/json"},
            latency_ms=Decimal("1.0"),
        )


class TestBinanceProvider(unittest.TestCase):
    """Test suite for BinanceProvider."""

    def setUp(self) -> None:
        self.mock_transport = MockTransportClient()
        self.provider = BinanceProvider(transport=self.mock_transport)

    def test_protocol_and_contract_conformance(self) -> None:
        """Verify BinanceProvider satisfies MarketDataProvider contract."""
        self.assertIsInstance(self.provider, MarketDataProvider)
        self.assertEqual(self.provider.provider_name, "binance")
        self.assertTrue(self.provider.capabilities.quote)
        self.assertTrue(self.provider.capabilities.ohlcv)
        self.assertTrue(self.provider.capabilities.orderbook)
        self.assertTrue(self.provider.capabilities.funding_rate)
        self.assertTrue(self.provider.capabilities.open_interest)
        self.assertTrue(self.provider.supports_feature("quote"))
        self.assertTrue(self.provider.supports_feature("funding_rate"))
        self.assertFalse(self.provider.supports_feature("macro"))
        self.assertEqual(self.provider.metadata.provider_name, "binance")
        self.assertIn("BTC/USDT", self.provider.get_supported_symbols())

    def test_health_check_healthy(self) -> None:
        """health_check returns HEALTHY when ping succeeds."""
        self.mock_transport.set_response("/api/v3/ping", status_code=200, body={})
        health = self.provider.health_check()
        self.assertEqual(health.state, HealthState.HEALTHY)
        self.assertEqual(health.provider_name, "binance")

    def test_health_check_down_on_failure(self) -> None:
        """health_check returns UNHEALTHY when ping fails."""
        self.mock_transport.set_response(
            "/api/v3/ping", status_code=503, body={"msg": "Service Unavailable"}
        )
        health = self.provider.health_check()
        self.assertEqual(health.state, HealthState.UNHEALTHY)
        self.assertIsNotNone(health.error_message)

    def test_get_server_time(self) -> None:
        """get_server_time returns timezone-aware UTC datetime."""
        epoch_ms = 1731154800000  # 2024-11-09T12:20:00Z
        self.mock_transport.set_response(
            "/api/v3/time", status_code=200, body={"serverTime": epoch_ms}
        )
        server_time = self.provider.get_server_time()
        self.assertEqual(server_time.tzinfo, timezone.utc)
        self.assertEqual(int(server_time.timestamp() * 1000), epoch_ms)

    def test_get_quote_success(self) -> None:
        """get_quote converts Binance ticker/24hr response to QuoteDTO."""
        payload = {
            "symbol": "BTCUSDT",
            "lastPrice": "88500.50",
            "bidPrice": "88500.00",
            "askPrice": "88501.00",
            "bidQty": "1.250",
            "askQty": "0.850",
            "volume": "15420.75",
            "closeTime": 1731154800000,
        }
        self.mock_transport.set_response("/api/v3/ticker/24hr", status_code=200, body=payload)

        quote = self.provider.get_quote("BTC/USDT")
        self.assertIsInstance(quote, QuoteDTO)
        self.assertEqual(quote.symbol, "BTC/USDT")
        self.assertEqual(quote.price, Decimal("88500.50"))
        self.assertEqual(quote.bid, Decimal("88500.00"))
        self.assertEqual(quote.ask, Decimal("88501.00"))
        self.assertEqual(quote.bid_size, Decimal("1.250"))
        self.assertEqual(quote.ask_size, Decimal("0.850"))
        self.assertEqual(quote.volume_24h, Decimal("15420.75"))
        self.assertEqual(quote.provider, "binance")

    def test_get_ohlcv_success(self) -> None:
        """get_ohlcv converts Binance klines to OHLCVSeriesDTO."""
        payload = [
            [1731150000000, "88000.00", "88200.00", "87900.00", "88150.00", "120.5", 1731153599999],
            [1731153600000, "88150.00", "88500.00", "88100.00", "88450.00", "95.2", 1731157199999],
        ]
        self.mock_transport.set_response("/api/v3/klines", status_code=200, body=payload)

        series = self.provider.get_ohlcv(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            start_date=datetime(2024, 11, 9, 10, 0, tzinfo=timezone.utc),
            end_date=datetime(2024, 11, 9, 12, 0, tzinfo=timezone.utc),
        )
        self.assertIsInstance(series, OHLCVSeriesDTO)
        self.assertEqual(series.symbol, "BTC/USDT")
        self.assertEqual(series.timeframe, Timeframe.H1)
        self.assertEqual(len(series.candles), 2)
        self.assertEqual(series.candles[0].open, Decimal("88000.00"))
        self.assertEqual(series.candles[0].high, Decimal("88200.00"))
        self.assertEqual(series.candles[1].close, Decimal("88450.00"))

    def test_get_ohlcv_transparent_pagination(self) -> None:
        """get_ohlcv transparently paginates across 1000-candle page boundaries."""
        base_ms = 1700000000000  # arbitrary epoch
        hour_ms = 3600 * 1000

        # Simulate 2 pages: page 1 has 1,000 candles, page 2 has 200 candles = 1,200 total
        def klines_handler(url: str, params: dict[str, Any]) -> TransportResponse:
            start = int(params["startTime"])
            if start == base_ms:
                # Return full page of 1000 candles
                candles = [
                    [base_ms + i * hour_ms, "80000.00", "80100.00", "79900.00", "80050.00", "10.0"]
                    for i in range(1000)
                ]
            else:
                # Return final page of 200 candles
                candles = [
                    [start + i * hour_ms, "80050.00", "80200.00", "80000.00", "80150.00", "15.0"]
                    for i in range(200)
                ]
            return TransportResponse(
                status_code=200,
                data=candles,
                headers={"Content-Type": "application/json"},
                latency_ms=Decimal("2.0"),
            )

        self.mock_transport.set_handler("/api/v3/klines", klines_handler)

        start_dt = datetime.fromtimestamp(base_ms / 1000.0, tz=timezone.utc)
        end_dt = datetime.fromtimestamp((base_ms + 1200 * hour_ms) / 1000.0, tz=timezone.utc)

        series = self.provider.get_ohlcv("BTC/USDT", Timeframe.H1, start_dt, end_dt)
        self.assertEqual(len(series.candles), 1200)
        # Verify candles are ordered chronologically
        self.assertEqual(series.candles[0].timestamp, start_dt)
        self.assertLess(series.candles[0].timestamp, series.candles[-1].timestamp)

    def test_get_orderbook_success(self) -> None:
        """get_orderbook converts depth snapshot to OrderBookDTO and computes spread_bps."""
        payload = {
            "lastUpdateId": 12345678,
            "bids": [["88000.00", "1.500"], ["87990.00", "2.000"]],
            "asks": [["88010.00", "1.200"], ["88020.00", "3.500"]],
        }
        self.mock_transport.set_response("/api/v3/depth", status_code=200, body=payload)

        book = self.provider.get_orderbook("BTC/USDT", depth=20)
        self.assertIsInstance(book, OrderBookDTO)
        self.assertEqual(len(book.bids), 2)
        self.assertEqual(len(book.asks), 2)
        self.assertEqual(book.bids[0].price, Decimal("88000.00"))
        self.assertEqual(book.asks[0].price, Decimal("88010.00"))
        # spread_bps = ((88010 - 88000) / 88010) * 10000 = ~1.136 bps
        self.assertGreater(book.spread_bps, Decimal("1.0"))
        self.assertLess(book.spread_bps, Decimal("2.0"))

    def test_get_funding_rate_success(self) -> None:
        """get_funding_rate parses perpetual futures premium index."""
        payload = {
            "symbol": "BTCUSDT",
            "markPrice": "88520.10",
            "indexPrice": "88515.00",
            "lastFundingRate": "0.00010000",
            "nextFundingTime": 1731168000000,
            "time": 1731154800000,
        }
        self.mock_transport.set_response("/fapi/v1/premiumIndex", status_code=200, body=payload)

        fr = self.provider.get_funding_rate("BTC/USDT")
        self.assertIsInstance(fr, FundingRateDTO)
        self.assertEqual(fr.symbol, "BTC/USDT")
        self.assertEqual(fr.funding_rate, Decimal("0.00010000"))
        # Annualized = 0.0001 * 3 * 365 = 0.1095 (10.95%)
        self.assertEqual(fr.annualized_rate, Decimal("0.10950000"))
        self.assertEqual(fr.mark_price, Decimal("88520.10"))
        self.assertEqual(fr.exchange, "binance")

    def test_get_open_interest_success(self) -> None:
        """get_open_interest converts openInterest response to OpenInterestDTO."""
        payload = {
            "symbol": "BTCUSDT",
            "openInterest": "28450.125",
            "time": 1731154800000,
        }
        self.mock_transport.set_response("/fapi/v1/openInterest", status_code=200, body=payload)

        oi = self.provider.get_open_interest("BTC/USDT")
        self.assertIsInstance(oi, OpenInterestDTO)
        self.assertEqual(oi.symbol, "BTC/USDT")
        self.assertEqual(oi.open_interest, Decimal("28450.125"))

    def test_get_mark_price_success(self) -> None:
        """get_mark_price converts premiumIndex to MarkPriceDTO."""
        payload = {
            "symbol": "BTCUSDT",
            "markPrice": "88520.10",
            "indexPrice": "88515.00",
            "estimatedSettlePrice": "88518.00",
            "lastFundingRate": "0.00010000",
            "nextFundingTime": 1731168000000,
            "time": 1731154800000,
        }
        self.mock_transport.set_response("/fapi/v1/premiumIndex", status_code=200, body=payload)

        mp = self.provider.get_mark_price("BTC/USDT")
        self.assertIsInstance(mp, MarkPriceDTO)
        self.assertEqual(mp.mark_price, Decimal("88520.10"))
        self.assertEqual(mp.index_price, Decimal("88515.00"))
        self.assertEqual(mp.estimated_settle_price, Decimal("88518.00"))
        self.assertEqual(mp.last_funding_rate, Decimal("0.00010000"))

    def test_get_symbol_filters_success(self) -> None:
        """get_symbol_filters extracts tick size, step size, and precision."""
        payload = {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "quotePrecision": 2,
                    "baseAssetPrecision": 8,
                    "filters": [
                        {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                        {"filterType": "LOT_SIZE", "stepSize": "0.00001", "minQty": "0.00001", "maxQty": "9000.0"},
                        {"filterType": "NOTIONAL", "minNotional": "5.0"},
                    ],
                }
            ]
        }
        self.mock_transport.set_response("/api/v3/exchangeInfo", status_code=200, body=payload)

        filters = self.provider.get_symbol_filters("BTC/USDT")
        self.assertIsInstance(filters, SymbolFilterDTO)
        self.assertEqual(filters.symbol, "BTC/USDT")
        self.assertEqual(filters.base_asset, "BTC")
        self.assertEqual(filters.quote_asset, "USDT")
        self.assertEqual(filters.tick_size, Decimal("0.10"))
        self.assertEqual(filters.step_size, Decimal("0.00001"))
        self.assertEqual(filters.min_notional, Decimal("5.0"))

    def test_get_exchange_info_success(self) -> None:
        """get_exchange_info parses full catalog of symbol filters."""
        payload = {
            "serverTime": 1731154800000,
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "quotePrecision": 2,
                    "baseAssetPrecision": 8,
                    "filters": [
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                        {"filterType": "LOT_SIZE", "stepSize": "0.00001", "minQty": "0.00001", "maxQty": "1000.0"},
                        {"filterType": "MIN_NOTIONAL", "minNotional": "5.0"},
                    ],
                }
            ],
        }
        self.mock_transport.set_response("/api/v3/exchangeInfo", status_code=200, body=payload)

        info = self.provider.get_exchange_info()
        self.assertIsInstance(info, ExchangeInfoDTO)
        self.assertEqual(len(info.symbols), 1)
        self.assertEqual(info.symbols[0].base_asset, "BTC")

    def test_invalid_symbol_raises_no_market_data_error(self) -> None:
        """Binance -1121 error is translated to NoMarketDataError."""
        payload = {"code": -1121, "msg": "Invalid symbol."}
        self.mock_transport.set_response("/api/v3/ticker/24hr", status_code=400, body=payload)

        with self.assertRaises(NoMarketDataError):
            self.provider.get_quote("BTC/USDT")

    def test_non_crypto_symbol_raises_no_market_data_error(self) -> None:
        """Attempting to resolve non-crypto symbol for Binance raises NoMarketDataError."""
        with self.assertRaises(NoMarketDataError):
            self.provider.get_quote("AAPL")

    def test_http_404_raises_no_market_data_error(self) -> None:
        """HTTP 404 raises NoMarketDataError."""
        self.mock_transport.set_response("/api/v3/ticker/24hr", status_code=404, body="Not Found")
        with self.assertRaises(NoMarketDataError):
            self.provider.get_quote("BTC/USDT")

    def test_http_429_raises_vendor_rate_limit_error(self) -> None:
        """HTTP 429 raises VendorRateLimitError."""
        self.mock_transport.set_response("/api/v3/ticker/24hr", status_code=429, body="Rate limit")
        with self.assertRaises(VendorRateLimitError):
            self.provider.get_quote("BTC/USDT")

    def test_http_500_raises_vendor_unavailable_error(self) -> None:
        """HTTP 500 raises VendorUnavailableError."""
        self.mock_transport.set_response("/api/v3/ticker/24hr", status_code=500, body="Server error")
        with self.assertRaises(VendorUnavailableError):
            self.provider.get_quote("BTC/USDT")

    def test_malformed_json_raises_vendor_error(self) -> None:
        """Corrupted JSON body raises VendorError."""
        self.mock_transport.set_response("/api/v3/ticker/24hr", status_code=200, body="INVALID_JSON{")
        with self.assertRaises(VendorError):
            self.provider.get_quote("BTC/USDT")

    def test_integration_with_provider_registry(self) -> None:
        """BinanceProvider integrates into InMemoryProviderRegistry seamlessly."""
        registry = InMemoryProviderRegistry()
        registry.register(self.provider, priority=1)

        # BTC quote should find binance
        candidates = registry.get_candidates("BTC/USDT", "quote")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].provider_name, "binance")

        # BTC funding rate should find binance
        fr_candidates = registry.get_candidates("BTC/USDT", "funding_rate")
        self.assertEqual(len(fr_candidates), 1)
        self.assertEqual(fr_candidates[0].provider_name, "binance")

        # XAUUSD funding rate should NOT find binance
        gold_candidates = registry.get_candidates("XAUUSD", "funding_rate")
        self.assertEqual(len(gold_candidates), 0)


if __name__ == "__main__":
    unittest.main()
