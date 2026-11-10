"""Enumerations for multi-asset data provider contracts and telemetry."""

from __future__ import annotations

from enum import Enum


class Timeframe(str, Enum):
    """Supported candlestick aggregation intervals."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class HealthState(str, Enum):
    """Operational status of a data provider."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class CircuitState(str, Enum):
    """Circuit breaker operational state."""

    CLOSED = "closed"        # Normal operation, queries allowed
    OPEN = "open"            # Failing, queries blocked/bypassed
    HALF_OPEN = "half_open"  # Cooldown elapsed, probing recovery
