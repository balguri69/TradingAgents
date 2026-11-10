"""Order Intent Builder for constructing immutable OrderIntentDTO instances."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from tradingagents.dataflows.enums import Timeframe
from tradingagents.execution.dto import OrderIntentDTO
from tradingagents.execution.enums import (
    OrderSide,
    OrderType,
    TimeInForce,
    TradeDirection,
)
from tradingagents.risk.enums import RiskLevel


class OrderIntentBuilder:
    """Builder class for assembling validated, immutable OrderIntentDTOs."""

    def __init__(self) -> None:
        self._intent_id: str = f"intent_{uuid.uuid4().hex[:12]}"
        self._client_order_id: str = f"co_{uuid.uuid4().hex[:12]}"
        self._symbol: str = ""
        self._timeframe: Timeframe = Timeframe.H1
        self._timestamp: datetime = datetime.now(timezone.utc)
        self._direction: TradeDirection = TradeDirection.NO_TRADE
        self._side: OrderSide | None = None
        self._order_type: OrderType = OrderType.MARKET
        self._quantity: Decimal = Decimal("1.0")
        self._limit_price: Decimal | None = None
        self._stop_price: Decimal | None = None
        self._time_in_force: TimeInForce = TimeInForce.GTC
        self._reduce_only: bool = False
        self._is_executable: bool = True
        self._gating_reason: str | None = None
        self._assessment_confidence: Decimal = Decimal("0.00")
        self._risk_level: RiskLevel | None = None

    def with_intent_id(self, intent_id: str) -> OrderIntentBuilder:
        self._intent_id = intent_id
        return self

    def with_client_order_id(self, client_order_id: str) -> OrderIntentBuilder:
        self._client_order_id = client_order_id
        return self

    def with_symbol(self, symbol: str) -> OrderIntentBuilder:
        self._symbol = symbol
        return self

    def with_timeframe(self, timeframe: Timeframe) -> OrderIntentBuilder:
        self._timeframe = timeframe
        return self

    def with_timestamp(self, timestamp: datetime) -> OrderIntentBuilder:
        self._timestamp = timestamp
        return self

    def with_direction(self, direction: TradeDirection) -> OrderIntentBuilder:
        self._direction = direction
        return self

    def with_side(self, side: OrderSide | None) -> OrderIntentBuilder:
        self._side = side
        return self

    def with_order_type(self, order_type: OrderType) -> OrderIntentBuilder:
        self._order_type = order_type
        return self

    def with_quantity(self, quantity: Decimal) -> OrderIntentBuilder:
        self._quantity = quantity
        return self

    def with_limit_price(self, limit_price: Decimal | None) -> OrderIntentBuilder:
        self._limit_price = limit_price
        return self

    def with_stop_price(self, stop_price: Decimal | None) -> OrderIntentBuilder:
        self._stop_price = stop_price
        return self

    def with_time_in_force(self, tif: TimeInForce) -> OrderIntentBuilder:
        self._time_in_force = tif
        return self

    def with_reduce_only(self, reduce_only: bool) -> OrderIntentBuilder:
        self._reduce_only = reduce_only
        return self

    def with_is_executable(self, is_executable: bool) -> OrderIntentBuilder:
        self._is_executable = is_executable
        return self

    def with_gating_reason(self, gating_reason: str | None) -> OrderIntentBuilder:
        self._gating_reason = gating_reason
        return self

    def with_confidence(self, confidence: Decimal) -> OrderIntentBuilder:
        self._assessment_confidence = confidence
        return self

    def with_risk_level(self, risk_level: RiskLevel | None) -> OrderIntentBuilder:
        self._risk_level = risk_level
        return self

    def gate(self, reason: str) -> OrderIntentBuilder:
        """Convenience method to set non-executable with a specific reason."""
        self._is_executable = False
        self._gating_reason = reason
        self._direction = TradeDirection.NO_TRADE
        self._side = None
        return self

    def build(self) -> OrderIntentDTO:
        """Construct immutable OrderIntentDTO with validation."""
        return OrderIntentDTO(
            intent_id=self._intent_id,
            client_order_id=self._client_order_id,
            symbol=self._symbol,
            timeframe=self._timeframe,
            timestamp=self._timestamp,
            direction=self._direction,
            side=self._side,
            order_type=self._order_type,
            quantity=self._quantity,
            limit_price=self._limit_price,
            stop_price=self._stop_price,
            time_in_force=self._time_in_force,
            reduce_only=self._reduce_only,
            is_executable=self._is_executable,
            gating_reason=self._gating_reason,
            assessment_confidence=self._assessment_confidence,
            risk_level=self._risk_level,
        )
