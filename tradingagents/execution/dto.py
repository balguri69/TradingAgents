"""Strongly typed, immutable Data Transfer Objects for Phase 12 Execution Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from tradingagents.dataflows.dto.features import BaseFeatureDTO
from tradingagents.dataflows.dto.validation import (
    validate_non_negative_decimal,
    validate_positive_decimal,
    validate_utc_datetime,
)
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.execution.enums import (
    ExecutionStatus,
    OrderSide,
    OrderState,
    OrderType,
    TimeInForce,
    TradeDirection,
)
from tradingagents.risk.enums import RiskLevel

PRECISION_TWO = Decimal("0.01")
PRECISION_FOUR = Decimal("0.0001")
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class OrderIntentDTO:
    """Institutional intent to place, route, or gate an order.
    
    Acts as the immutable contract produced by the ExecutionPlanner before
    submission to any broker adapter.
    """

    intent_id: str
    client_order_id: str
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    direction: TradeDirection
    side: OrderSide | None
    order_type: OrderType
    quantity: Decimal
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
    reduce_only: bool = False
    is_executable: bool = True
    gating_reason: str | None = None
    assessment_confidence: Decimal = Decimal("0.00")
    risk_level: RiskLevel | None = None

    def __post_init__(self) -> None:
        if not self.intent_id or not isinstance(self.intent_id, str):
            raise DTOValidationError("intent_id must be a non-empty string")
        if not self.client_order_id or not isinstance(self.client_order_id, str):
            raise DTOValidationError("client_order_id must be a non-empty string")
        if not self.symbol or not isinstance(self.symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        if not isinstance(self.timeframe, Timeframe):
            raise DTOValidationError(f"timeframe must be a Timeframe instance, got {type(self.timeframe)}")
        validate_utc_datetime(self.timestamp, "timestamp")
        if not isinstance(self.direction, TradeDirection):
            raise DTOValidationError(f"direction must be TradeDirection, got {type(self.direction)}")
        if not isinstance(self.order_type, OrderType):
            raise DTOValidationError(f"order_type must be OrderType, got {type(self.order_type)}")
        if not isinstance(self.time_in_force, TimeInForce):
            raise DTOValidationError(f"time_in_force must be TimeInForce, got {type(self.time_in_force)}")

        if self.is_executable:
            if self.direction == TradeDirection.NO_TRADE:
                raise DTOValidationError("is_executable=True cannot have direction NO_TRADE")
            if not isinstance(self.side, OrderSide):
                raise DTOValidationError(f"is_executable=True requires valid OrderSide, got {type(self.side)}")
            validate_positive_decimal(self.quantity, "quantity")
            if self.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
                if self.limit_price is None:
                    raise DTOValidationError(f"limit_price is required for order_type {self.order_type}")
                validate_positive_decimal(self.limit_price, "limit_price")
            if self.order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT):
                if self.stop_price is None:
                    raise DTOValidationError(f"stop_price is required for order_type {self.order_type}")
                validate_positive_decimal(self.stop_price, "stop_price")
        else:
            if self.gating_reason is None or not self.gating_reason.strip():
                raise DTOValidationError("gating_reason is required when is_executable=False")


@dataclass(frozen=True)
class FillDTO:
    """Immutable execution event representing a trade fill (partial or full)."""

    fill_id: str
    order_id: str
    timestamp: datetime
    price: Decimal
    quantity: Decimal
    fee: Decimal = Decimal("0.00")
    fee_asset: str = "USD"
    is_maker: bool = False

    def __post_init__(self) -> None:
        if not self.fill_id or not isinstance(self.fill_id, str):
            raise DTOValidationError("fill_id must be a non-empty string")
        if not self.order_id or not isinstance(self.order_id, str):
            raise DTOValidationError("order_id must be a non-empty string")
        validate_utc_datetime(self.timestamp, "timestamp")
        validate_positive_decimal(self.price, "price")
        validate_positive_decimal(self.quantity, "quantity")
        validate_non_negative_decimal(self.fee, "fee")
        if not self.fee_asset or not isinstance(self.fee_asset, str):
            raise DTOValidationError("fee_asset must be a non-empty string")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ExecutionReportDTO(BaseFeatureDTO):
    """Institutional execution report tracking order status, fills, and ledger state.
    
    Subclasses BaseFeatureDTO to enable direct point-in-time persistence
    into the FeatureStore.
    """

    feature_name: str = "execution_report"
    order_id: str = ""
    client_order_id: str = ""
    status: ExecutionStatus = ExecutionStatus.EXECUTED
    state: OrderState = OrderState.FILLED
    side: OrderSide | None = None
    order_type: OrderType = OrderType.MARKET
    requested_quantity: Decimal = Decimal("0.00")
    filled_quantity: Decimal = Decimal("0.00")
    remaining_quantity: Decimal = Decimal("0.00")
    average_price: Decimal | None = None
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    total_fee: Decimal = Decimal("0.00")
    fee_asset: str = "USD"
    fills: tuple[FillDTO, ...] = ()
    rejection_reason: str | None = None
    gating_reason: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.order_id or not isinstance(self.order_id, str):
            raise DTOValidationError("order_id must be a non-empty string")
        if not self.client_order_id or not isinstance(self.client_order_id, str):
            raise DTOValidationError("client_order_id must be a non-empty string")
        if not isinstance(self.status, ExecutionStatus):
            raise DTOValidationError(f"status must be ExecutionStatus, got {type(self.status)}")
        if not isinstance(self.state, OrderState):
            raise DTOValidationError(f"state must be OrderState, got {type(self.state)}")
        if not isinstance(self.order_type, OrderType):
            raise DTOValidationError(f"order_type must be OrderType, got {type(self.order_type)}")
        validate_non_negative_decimal(self.requested_quantity, "requested_quantity")
        validate_non_negative_decimal(self.filled_quantity, "filled_quantity")
        validate_non_negative_decimal(self.remaining_quantity, "remaining_quantity")
        validate_non_negative_decimal(self.total_fee, "total_fee")
        validate_utc_datetime(self.created_at, "created_at")
        validate_utc_datetime(self.updated_at, "updated_at")

        if self.limit_price is not None:
            validate_positive_decimal(self.limit_price, "limit_price")
        if self.stop_price is not None:
            validate_positive_decimal(self.stop_price, "stop_price")
        if self.average_price is not None:
            validate_positive_decimal(self.average_price, "average_price")


@dataclass(frozen=True)
class PositionDTO:
    """Immutable portfolio position for a traded asset."""

    symbol: str
    quantity: Decimal
    average_entry_price: Decimal
    realized_pnl: Decimal = Decimal("0.00")
    unrealized_pnl: Decimal = Decimal("0.00")
    updated_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.symbol or not isinstance(self.symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        if not isinstance(self.quantity, Decimal):
            raise DTOValidationError("quantity must be Decimal")
        validate_non_negative_decimal(self.average_entry_price, "average_entry_price")
        if not isinstance(self.realized_pnl, Decimal):
            raise DTOValidationError("realized_pnl must be Decimal")
        if not isinstance(self.unrealized_pnl, Decimal):
            raise DTOValidationError("unrealized_pnl must be Decimal")
        validate_utc_datetime(self.updated_at, "updated_at")
