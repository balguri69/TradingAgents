"""Observability and telemetry data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from tradingagents.dataflows.dto.validation import validate_utc_datetime
from tradingagents.dataflows.enums import CircuitState, HealthState
from tradingagents.dataflows.exceptions import DTOValidationError


@dataclass(frozen=True)
class TransportResponse:
    """Standardized response from an abstract TransportClient."""

    status_code: int
    data: Any
    headers: dict[str, str]
    latency_ms: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.status_code, int):
            raise DTOValidationError("status_code must be an integer")
        if not isinstance(self.latency_ms, Decimal):
            raise DTOValidationError("latency_ms must be a Decimal")
        if self.latency_ms < 0:
            raise DTOValidationError("latency_ms cannot be negative")


@dataclass(frozen=True)
class RequestMetricsDTO:
    """Structured telemetry emitted on every data provider query."""

    request_id: str
    symbol: str
    feature_name: str
    provider_name: str
    latency_ms: Decimal
    retries: int
    failovers: int
    cache_hit: bool
    status_code: int
    timestamp: datetime
    error_message: str | None = None

    def __post_init__(self) -> None:
        if not self.request_id:
            raise DTOValidationError("request_id must be non-empty")
        if not isinstance(self.latency_ms, Decimal):
            raise DTOValidationError("latency_ms must be a Decimal")
        if self.retries < 0 or self.failovers < 0:
            raise DTOValidationError("retries and failovers must be non-negative integers")
        validate_utc_datetime(self.timestamp, "timestamp")


@dataclass(frozen=True)
class HealthStatusDTO:
    """Provider diagnostic status."""

    provider_name: str
    state: HealthState
    latency_ms: Decimal
    last_successful_query: datetime | None
    error_message: str | None = None
    circuit_state: CircuitState = CircuitState.CLOSED

    def __post_init__(self) -> None:
        if not self.provider_name:
            raise DTOValidationError("provider_name must be non-empty")
        if not isinstance(self.state, HealthState):
            raise DTOValidationError(f"state must be a HealthState enum, got {type(self.state)}")
        if not isinstance(self.latency_ms, Decimal):
            raise DTOValidationError("latency_ms must be a Decimal")
        if self.last_successful_query is not None:
            validate_utc_datetime(self.last_successful_query, "last_successful_query")
        if not isinstance(self.circuit_state, CircuitState):
            raise DTOValidationError(f"circuit_state must be a CircuitState enum, got {type(self.circuit_state)}")


@dataclass(frozen=True)
class ProviderHealth:
    """Immutable health tracking and circuit telemetry for a managed provider."""

    provider_name: str
    status: HealthState
    latency_ms: Decimal
    success_rate: Decimal
    last_successful_request: datetime | None
    failure_count: int
    circuit_state: CircuitState = CircuitState.CLOSED
    total_requests: int = 0
    total_successes: int = 0

    def __post_init__(self) -> None:
        if not self.provider_name or not isinstance(self.provider_name, str):
            raise DTOValidationError("provider_name must be a non-empty string")
        if not isinstance(self.status, HealthState):
            raise DTOValidationError(f"status must be a HealthState enum, got {type(self.status)}")
        if not isinstance(self.latency_ms, Decimal):
            raise DTOValidationError("latency_ms must be a Decimal")
        if not isinstance(self.success_rate, Decimal):
            raise DTOValidationError("success_rate must be a Decimal")
        if not (Decimal("0") <= self.success_rate <= Decimal("1.0")):
            raise DTOValidationError(f"success_rate must be between 0.0 and 1.0, got {self.success_rate}")
        if self.last_successful_request is not None:
            validate_utc_datetime(self.last_successful_request, "last_successful_request")
        if self.failure_count < 0:
            raise DTOValidationError("failure_count cannot be negative")
        if self.total_requests < 0 or self.total_successes < 0:
            raise DTOValidationError("request counters cannot be negative")
        if not isinstance(self.circuit_state, CircuitState):
            raise DTOValidationError(f"circuit_state must be a CircuitState enum, got {type(self.circuit_state)}")
