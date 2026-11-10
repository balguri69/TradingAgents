"""Enumerations for Phase 12 Execution Engine."""

from __future__ import annotations

from enum import Enum


class TradeDirection(str, Enum):
    """Institutional directional trading intent."""

    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


class OrderSide(str, Enum):
    """Order transaction side."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order execution classification."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"


class TimeInForce(str, Enum):
    """Order duration and cancellation instruction."""

    GTC = "GTC"  # Good 'Til Cancelled
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill


class OrderState(str, Enum):
    """Lifecycle status of an individual broker order."""

    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ExecutionStatus(str, Enum):
    """High-level outcome of an execution attempt."""

    EXECUTED = "EXECUTED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    GATED_BY_RISK = "GATED_BY_RISK"
    NO_TRADE_SIGNAL = "NO_TRADE_SIGNAL"
    CANCELLED = "CANCELLED"
