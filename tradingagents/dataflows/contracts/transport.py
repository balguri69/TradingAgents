"""Transport protocol and timeout configuration for decoupled network communication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from tradingagents.dataflows.dto.telemetry import TransportResponse


@dataclass(frozen=True)
class TimeoutConfig:
    """Explicit connect and read timeout configuration."""

    connect_timeout: float = 3.0
    read_timeout: float = 10.0

    @property
    def total_timeout(self) -> float:
        """Total allowable timeout across connect and read phases."""
        return self.connect_timeout + self.read_timeout


@runtime_checkable
class TransportClient(Protocol):
    """Structural protocol for decoupled network communication.

    Enables REST, WebSocket, FIX, or simulated test doubles to satisfy the transport
    boundary without rigid class inheritance hierarchies.

    Designed for forward compatibility: accepts extensible kwargs so future retry policies,
    cancellation tokens, and async contexts can be introduced without altering call signatures.
    """

    def execute_request(
        self,
        endpoint_url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | TimeoutConfig | tuple[float, float] | None = None,
        **kwargs: Any,
    ) -> TransportResponse:
        """Execute network query and return a TransportResponse."""
        ...
