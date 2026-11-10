"""Unit tests for Phase 2 RestTransportClient."""

from __future__ import annotations

import json
import socket
import unittest
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any

from tradingagents.dataflows.contracts.transport import (
    TimeoutConfig,
    TransportClient,
)
from tradingagents.dataflows.dto.telemetry import TransportResponse
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorRateLimitError,
    VendorUnavailableError,
)
from tradingagents.dataflows.transport import RestTransportClient


class TestRestTransportClientInstantiation(unittest.TestCase):
    """Test instantiation, configuration, and interface conformance."""

    def test_implements_transport_client_protocol(self):
        client = RestTransportClient()
        self.assertIsInstance(client, TransportClient)

    def test_default_timeout_configuration(self):
        client = RestTransportClient()
        self.assertEqual(client.default_timeout.connect_timeout, 3.0)
        self.assertEqual(client.default_timeout.read_timeout, 10.0)
        self.assertEqual(client.default_timeout.total_timeout, 13.0)

    def test_custom_timeout_configuration(self):
        cfg = TimeoutConfig(connect_timeout=1.5, read_timeout=5.0)
        client = RestTransportClient(default_timeout=cfg, user_agent="CustomAgent/2.0")
        self.assertEqual(client.default_timeout.connect_timeout, 1.5)
        self.assertEqual(client.default_timeout.read_timeout, 5.0)
        self.assertEqual(client.user_agent, "CustomAgent/2.0")


class TestRestTransportTimeoutHandling(unittest.TestCase):
    """Test separate connect and read timeout resolution."""

    def test_per_request_tuple_timeout(self):
        recorded_timeout: list[TimeoutConfig] = []

        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            recorded_timeout.append(timeout_cfg)
            return 200, b"{}", {}

        client = RestTransportClient(transport_fn=mock_transport)
        client.execute_request("https://api.example.com", timeout=(2.0, 8.0))

        self.assertEqual(len(recorded_timeout), 1)
        self.assertEqual(recorded_timeout[0].connect_timeout, 2.0)
        self.assertEqual(recorded_timeout[0].read_timeout, 8.0)
        self.assertEqual(recorded_timeout[0].total_timeout, 10.0)

    def test_per_request_timeout_config_object(self):
        recorded_timeout: list[TimeoutConfig] = []

        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            recorded_timeout.append(timeout_cfg)
            return 200, b"{}", {}

        client = RestTransportClient(transport_fn=mock_transport)
        custom_cfg = TimeoutConfig(connect_timeout=0.5, read_timeout=2.5)
        client.execute_request("https://api.example.com", timeout=custom_cfg)

        self.assertEqual(recorded_timeout[0], custom_cfg)

    def test_scalar_float_timeout(self):
        recorded_timeout: list[TimeoutConfig] = []

        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            recorded_timeout.append(timeout_cfg)
            return 200, b"{}", {}

        client = RestTransportClient(transport_fn=mock_transport)
        client.execute_request("https://api.example.com", timeout=15.0)

        self.assertEqual(recorded_timeout[0].connect_timeout, 3.0)
        self.assertEqual(recorded_timeout[0].read_timeout, 15.0)


class TestRestTransportSuccessCases(unittest.TestCase):
    """Test successful REST execution with dependency-injected transport."""

    def test_successful_json_get(self):
        recorded_req: list[urllib.request.Request] = []

        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            recorded_req.append(req)
            data = json.dumps({"symbol": "BTCUSDT", "price": "68000.50"}).encode("utf-8")
            return 200, data, {"Content-Type": "application/json"}

        client = RestTransportClient(transport_fn=mock_transport)
        resp = client.execute_request(
            endpoint_url="https://api.binance.com/api/v3/ticker/price",
            params={"symbol": "BTCUSDT", "ignored": None},
            headers={"X-Custom-Header": "TestVal"},
            timeout=(2.0, 5.0),
        )

        self.assertIsInstance(resp, TransportResponse)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"symbol": "BTCUSDT", "price": "68000.50"})
        self.assertIsInstance(resp.latency_ms, Decimal)
        self.assertGreaterEqual(resp.latency_ms, Decimal("0.0"))

        # Verify recorded request
        self.assertEqual(len(recorded_req), 1)
        req = recorded_req[0]
        self.assertEqual(
            req.full_url,
            "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        )
        self.assertEqual(req.headers.get("X-custom-header"), "TestVal")

    def test_url_with_existing_query_delimiter(self):
        recorded_req: list[urllib.request.Request] = []

        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            recorded_req.append(req)
            return 200, b"[]", {}

        client = RestTransportClient(transport_fn=mock_transport)
        client.execute_request(
            endpoint_url="https://api.binance.com/api/v3/klines?symbol=BTCUSDT",
            params={"interval": "1h"},
        )

        self.assertEqual(
            recorded_req[0].full_url,
            "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h",
        )

    def test_non_json_response_decoded_as_string(self):
        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            return 200, b"plain text response", {"Content-Type": "text/plain"}

        client = RestTransportClient(transport_fn=mock_transport)
        resp = client.execute_request("https://api.example.com/status")
        self.assertEqual(resp.data, "plain text response")

    def test_empty_response_body_returns_none(self):
        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            return 204, b"", {}

        client = RestTransportClient(transport_fn=mock_transport)
        resp = client.execute_request("https://api.example.com/empty")
        self.assertIsNone(resp.data)


class TestRestTransportTimeoutAndErrors(unittest.TestCase):
    """Test timeout enforcement and domain error translation."""

    def test_socket_timeout_raises_vendor_unavailable_error(self):
        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            raise socket.timeout("timed out")

        client = RestTransportClient(transport_fn=mock_transport)
        with self.assertRaises(VendorUnavailableError) as ctx:
            client.execute_request("https://api.binance.com/api/v3/ticker")
        self.assertIn("Network transport failure", str(ctx.exception))

    def test_url_error_raises_vendor_unavailable_error(self):
        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            raise urllib.error.URLError("Connection refused")

        client = RestTransportClient(transport_fn=mock_transport)
        with self.assertRaises(VendorUnavailableError):
            client.execute_request("https://api.binance.com/api/v3/ticker")

    def test_http_429_raises_vendor_rate_limit_error(self):
        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=429,
                msg="Too Many Requests",
                hdrs={},
                fp=None,
            )

        client = RestTransportClient(transport_fn=mock_transport)
        with self.assertRaises(VendorRateLimitError):
            client.execute_request("https://api.binance.com/api/v3/ticker")

    def test_http_404_raises_no_market_data_error(self):
        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=404,
                msg="Not Found",
                hdrs={},
                fp=None,
            )

        client = RestTransportClient(transport_fn=mock_transport)
        with self.assertRaises(NoMarketDataError):
            client.execute_request("https://api.binance.com/api/v3/bad_endpoint")

    def test_http_400_raises_no_market_data_error(self):
        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=400,
                msg="Bad Request (Invalid Symbol)",
                hdrs={},
                fp=None,
            )

        client = RestTransportClient(transport_fn=mock_transport)
        with self.assertRaises(NoMarketDataError):
            client.execute_request("https://api.binance.com/api/v3/ticker?symbol=INVALID")

    def test_http_500_raises_vendor_unavailable_error(self):
        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=None,
            )

        client = RestTransportClient(transport_fn=mock_transport)
        with self.assertRaises(VendorUnavailableError) as ctx:
            client.execute_request("https://api.binance.com/api/v3/ticker")
        self.assertIn("Remote provider error (HTTP 500)", str(ctx.exception))

    def test_http_503_raises_vendor_unavailable_error(self):
        def mock_transport(req: urllib.request.Request, timeout_cfg: TimeoutConfig):
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=503,
                msg="Service Unavailable",
                hdrs={},
                fp=None,
            )

        client = RestTransportClient(transport_fn=mock_transport)
        with self.assertRaises(VendorUnavailableError):
            client.execute_request("https://api.binance.com/api/v3/ticker")


class TestRestTransportForwardCompatibility(unittest.TestCase):
    """Test forward compatibility with future cancellation tokens and kwargs."""

    def test_cancellation_token_raises_vendor_unavailable(self):
        class MockCancellationToken:
            is_cancelled = True

        client = RestTransportClient()
        with self.assertRaises(VendorUnavailableError) as ctx:
            client.execute_request("https://api.example.com", cancellation_token=MockCancellationToken())
        self.assertIn("cancelled by caller", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
