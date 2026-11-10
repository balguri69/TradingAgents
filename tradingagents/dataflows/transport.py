"""Production-grade REST transport client for multi-asset data providers.

Implements TransportClient Protocol using Python standard library urllib.request to guarantee
zero external package dependencies and consistent single-client networking.

Phase 2 Scope: REST transport, separate connect/read timeout handling, error translation,
and dependency injection.
"""

from __future__ import annotations

import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from typing import Any, Callable

from tradingagents.dataflows.contracts.transport import (
    TimeoutConfig,
    TransportClient,
)
from tradingagents.dataflows.dto.telemetry import TransportResponse
from tradingagents.dataflows.exceptions import (
    NoMarketDataError,
    VendorRateLimitError,
    VendorUnavailableError,
)

logger = logging.getLogger(__name__)

DEFAULT_CONNECT_TIMEOUT_SECONDS: float = 3.0
DEFAULT_READ_TIMEOUT_SECONDS: float = 10.0
DEFAULT_USER_AGENT: str = "TradingAgents/1.0 (Institutional Intelligence Platform)"

# Pluggable low-level transport callable: receives (Request, TimeoutConfig) -> (status_code, body_bytes, headers_dict)
TransportCallable = Callable[
    [urllib.request.Request, TimeoutConfig], tuple[int, bytes, dict[str, str]]
]


def _resolve_timeout(
    timeout: float | TimeoutConfig | tuple[float, float] | None,
    default_config: TimeoutConfig,
) -> TimeoutConfig:
    """Normalize user-supplied timeout into a structured TimeoutConfig."""
    if timeout is None:
        return default_config
    if isinstance(timeout, TimeoutConfig):
        return timeout
    if isinstance(timeout, tuple) and len(timeout) == 2:
        return TimeoutConfig(
            connect_timeout=float(timeout[0]), read_timeout=float(timeout[1])
        )
    if isinstance(timeout, (int, float)):
        # If scalar passed, allocate connection ceiling and full read budget
        return TimeoutConfig(
            connect_timeout=min(float(timeout), 3.0),
            read_timeout=float(timeout),
        )
    raise ValueError(f"Invalid timeout specification: {timeout!r}")


class RestTransportClient(TransportClient):
    """Stateless REST transport client implementing TransportClient with dependency injection.

    Enforces single-client consistency, separate connect/read timeouts, comprehensive
    domain error translation, and forward-compatible signature for future cancellation/async.
    """

    def __init__(
        self,
        default_timeout: TimeoutConfig | float | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        transport_fn: TransportCallable | None = None,
    ):
        """Initialize RestTransportClient.

        Args:
            default_timeout: Default connect/read timeout configuration.
            user_agent: User-Agent header value sent on all HTTP requests.
            transport_fn: Pluggable transport callback for dependency injection and testing.
        """
        if default_timeout is None:
            self.default_timeout = TimeoutConfig(
                connect_timeout=DEFAULT_CONNECT_TIMEOUT_SECONDS,
                read_timeout=DEFAULT_READ_TIMEOUT_SECONDS,
            )
        elif isinstance(default_timeout, TimeoutConfig):
            self.default_timeout = default_timeout
        else:
            self.default_timeout = _resolve_timeout(
                default_timeout,
                TimeoutConfig(DEFAULT_CONNECT_TIMEOUT_SECONDS, DEFAULT_READ_TIMEOUT_SECONDS),
            )

        self.user_agent = user_agent
        self._transport_fn = transport_fn or self._default_urllib_transport

    @staticmethod
    def _default_urllib_transport(
        req: urllib.request.Request, timeout_config: TimeoutConfig
    ) -> tuple[int, bytes, dict[str, str]]:
        """Low-level network execution using standard library urllib.request."""
        # Standard urllib.request.urlopen enforces total socket timeout spanning connect and read
        with urllib.request.urlopen(req, timeout=timeout_config.total_timeout) as response:
            status_code = response.getcode()
            body_bytes = response.read()
            headers = {k: v for k, v in response.headers.items()}
            return status_code, body_bytes, headers

    def execute_request(
        self,
        endpoint_url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | TimeoutConfig | tuple[float, float] | None = None,
        **kwargs: Any,
    ) -> TransportResponse:
        """Execute HTTP GET request and return normalized TransportResponse.

        Args:
            endpoint_url: Target REST endpoint URL.
            params: Optional query parameters dictionary.
            headers: Optional custom HTTP headers dictionary.
            timeout: Optional per-request timeout overriding default_timeout (supports separate connect/read).
            **kwargs: Extensible keyword arguments (for future cancellation tokens, retries, context).

        Returns:
            TransportResponse containing status_code, decoded data, headers, and latency_ms (Decimal).

        Raises:
            VendorRateLimitError: If provider returns HTTP 429.
            NoMarketDataError: If provider returns HTTP 400 or HTTP 404.
            VendorUnavailableError: On HTTP 5xx, socket timeouts, cancellation, or network failures.
        """
        # Forward-compatible cancellation check
        cancellation_token = kwargs.get("cancellation_token")
        if cancellation_token is not None and getattr(cancellation_token, "is_cancelled", False):
            raise VendorUnavailableError(f"Request to {endpoint_url} cancelled by caller")

        effective_timeout = _resolve_timeout(timeout, self.default_timeout)

        # Build complete URL with query string
        if params:
            clean_params = {k: str(v) for k, v in params.items() if v is not None}
            query_string = urllib.parse.urlencode(clean_params)
            delimiter = "&" if "?" in endpoint_url else "?"
            full_url = f"{endpoint_url}{delimiter}{query_string}"
        else:
            full_url = endpoint_url

        # Build request headers
        req_headers: dict[str, str] = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(full_url, headers=req_headers, method="GET")

        start_time = time.monotonic()
        try:
            status_code, body_bytes, resp_headers = self._transport_fn(
                req, effective_timeout
            )
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            latency_decimal = Decimal(f"{elapsed_ms:.2f}")

            # Decode JSON body if possible, fallback to plain text string
            decoded_data: Any = None
            if body_bytes:
                try:
                    decoded_data = json.loads(body_bytes.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    decoded_data = body_bytes.decode("utf-8", errors="replace")

            return TransportResponse(
                status_code=status_code,
                data=decoded_data,
                headers=resp_headers,
                latency_ms=latency_decimal,
            )

        except urllib.error.HTTPError as exc:
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            error_body = ""
            try:
                error_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            logger.warning(
                "HTTP %d error on %s: %s (latency: %.1fms)",
                exc.code,
                endpoint_url,
                error_body[:200],
                elapsed_ms,
            )

            if exc.code == 429:
                raise VendorRateLimitError(
                    f"Rate limit exceeded (HTTP 429) on {endpoint_url}: {error_body}"
                ) from exc
            if exc.code in (400, 404):
                raise NoMarketDataError(
                    symbol=endpoint_url,
                    detail=f"Resource not found or bad request (HTTP {exc.code}): {error_body}",
                ) from exc
            if exc.code >= 500:
                raise VendorUnavailableError(
                    f"Remote provider error (HTTP {exc.code}) on {endpoint_url}: {error_body}"
                ) from exc
            raise VendorUnavailableError(
                f"Unexpected HTTP {exc.code} on {endpoint_url}: {error_body}"
            ) from exc

        except (urllib.error.URLError, TimeoutError, OSError, socket.timeout) as exc:
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            logger.warning(
                "Network transport failure on %s: %s (latency: %.1fms)",
                endpoint_url,
                str(exc),
                elapsed_ms,
            )
            raise VendorUnavailableError(
                f"Network transport failure reaching {endpoint_url}: {exc}"
            ) from exc
