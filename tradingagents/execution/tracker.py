"""Execution Tracker: thread-safe lifecycle tracking of orders, fills, and portfolio positions."""

from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.execution.dto import ExecutionReportDTO, FillDTO, PositionDTO
from tradingagents.execution.enums import (
    ExecutionStatus,
    OrderSide,
    OrderState,
    OrderType,
)

PRECISION_FOUR = Decimal("0.0001")
ZERO = Decimal("0.00")

TERMINAL_STATES = {
    OrderState.FILLED,
    OrderState.CANCELLED,
    OrderState.REJECTED,
    OrderState.EXPIRED,
}

VALID_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.PENDING: {
        OrderState.SUBMITTED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
    },
    OrderState.SUBMITTED: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
    },
    OrderState.PARTIALLY_FILLED: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
    },
    OrderState.FILLED: set(),
    OrderState.CANCELLED: set(),
    OrderState.REJECTED: set(),
    OrderState.EXPIRED: set(),
}


class ExecutionTracker:
    """Thread-safe ledger tracking order states, execution fills, and asset positions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._orders: OrderedDict[str, ExecutionReportDTO] = OrderedDict()
        self._client_id_map: dict[str, str] = {}
        self._positions: dict[str, PositionDTO] = {}

    def record_order(self, report: ExecutionReportDTO) -> None:
        """Register a new order report in the tracker."""
        with self._lock:
            if report.order_id in self._orders:
                raise DTOValidationError(f"Order with order_id {report.order_id} already exists")
            self._orders[report.order_id] = report
            self._client_id_map[report.client_order_id] = report.order_id

    def update_order(self, report: ExecutionReportDTO) -> None:
        """Update an existing order with a new state or execution outcome."""
        with self._lock:
            current = self._orders.get(report.order_id)
            if current is None:
                self.record_order(report)
                return

            if current.state in TERMINAL_STATES and report.state != current.state:
                raise DTOValidationError(
                    f"Cannot transition order {report.order_id} from terminal state {current.state} to {report.state}"
                )

            if report.state != current.state and report.state not in VALID_TRANSITIONS.get(current.state, set()):
                raise DTOValidationError(
                    f"Illegal state transition for order {report.order_id}: {current.state} -> {report.state}"
                )

            self._orders[report.order_id] = report

    def apply_fill(self, order_id: str, fill: FillDTO) -> ExecutionReportDTO:
        """Apply a trade fill to an open order and update portfolio positions."""
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                raise DTOValidationError(f"Order {order_id} not found in tracker")

            if order.state in TERMINAL_STATES:
                raise DTOValidationError(f"Cannot apply fill to order {order_id} in terminal state {order.state}")

            new_filled_qty = order.filled_quantity + fill.quantity
            if new_filled_qty > order.requested_quantity:
                raise DTOValidationError(
                    f"Cumulative filled quantity {new_filled_qty} exceeds requested {order.requested_quantity}"
                )

            new_remaining_qty = order.requested_quantity - new_filled_qty
            is_full = new_remaining_qty == Decimal("0.00")

            new_state = OrderState.FILLED if is_full else OrderState.PARTIALLY_FILLED
            new_status = ExecutionStatus.EXECUTED if is_full else ExecutionStatus.PARTIAL

            # Compute new weighted average price
            total_cost_prev = (order.average_price or Decimal("0.00")) * order.filled_quantity
            fill_cost = fill.price * fill.quantity
            new_avg_price = ((total_cost_prev + fill_cost) / new_filled_qty).quantize(PRECISION_FOUR)
            new_total_fee = order.total_fee + fill.fee
            new_fills = order.fills + (fill,)

            updated_report = ExecutionReportDTO(
                symbol=order.symbol,
                timeframe=order.timeframe,
                timestamp=fill.timestamp,
                feature_name=order.feature_name,
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status=new_status,
                state=new_state,
                side=order.side,
                order_type=order.order_type,
                requested_quantity=order.requested_quantity,
                filled_quantity=new_filled_qty,
                remaining_quantity=new_remaining_qty,
                average_price=new_avg_price,
                limit_price=order.limit_price,
                stop_price=order.stop_price,
                total_fee=new_total_fee,
                fee_asset=fill.fee_asset,
                fills=new_fills,
                rejection_reason=order.rejection_reason,
                gating_reason=order.gating_reason,
                created_at=order.created_at,
                updated_at=fill.timestamp,
            )

            self._orders[order_id] = updated_report

            # Update asset position
            if order.side is not None:
                self._update_position(
                    symbol=order.symbol,
                    side=order.side,
                    fill_qty=fill.quantity,
                    fill_price=fill.price,
                    timestamp=fill.timestamp,
                )

            return updated_report

    def _update_position(
        self,
        symbol: str,
        side: OrderSide,
        fill_qty: Decimal,
        fill_price: Decimal,
        timestamp: datetime,
    ) -> None:
        """Update net portfolio position and realized PnL."""
        pos = self._positions.get(
            symbol,
            PositionDTO(
                symbol=symbol,
                quantity=Decimal("0.00"),
                average_entry_price=Decimal("0.00"),
                realized_pnl=Decimal("0.00"),
                unrealized_pnl=Decimal("0.00"),
                updated_at=timestamp,
            ),
        )

        curr_qty = pos.quantity
        curr_entry = pos.average_entry_price
        curr_pnl = pos.realized_pnl

        if side == OrderSide.BUY:
            if curr_qty >= Decimal("0.00"):
                # Adding to long position
                new_qty = curr_qty + fill_qty
                new_entry = (
                    ((curr_qty * curr_entry) + (fill_qty * fill_price)) / new_qty
                ).quantize(PRECISION_FOUR)
                new_pnl = curr_pnl
            else:
                # Covering short position
                short_qty = abs(curr_qty)
                closed_qty = min(short_qty, fill_qty)
                pnl_realized = closed_qty * (curr_entry - fill_price)
                new_pnl = curr_pnl + pnl_realized
                new_qty = curr_qty + fill_qty

                if new_qty < Decimal("0.00"):
                    new_entry = curr_entry
                elif new_qty == Decimal("0.00"):
                    new_entry = Decimal("0.00")
                else:
                    new_entry = fill_price
        else:  # OrderSide.SELL
            if curr_qty <= Decimal("0.00"):
                # Adding to short position
                short_qty = abs(curr_qty)
                new_short = short_qty + fill_qty
                new_entry = (
                    ((short_qty * curr_entry) + (fill_qty * fill_price)) / new_short
                ).quantize(PRECISION_FOUR)
                new_qty = curr_qty - fill_qty
                new_pnl = curr_pnl
            else:
                # Reducing long position
                closed_qty = min(curr_qty, fill_qty)
                pnl_realized = closed_qty * (fill_price - curr_entry)
                new_pnl = curr_pnl + pnl_realized
                new_qty = curr_qty - fill_qty

                if new_qty > Decimal("0.00"):
                    new_entry = curr_entry
                elif new_qty == Decimal("0.00"):
                    new_entry = Decimal("0.00")
                else:
                    new_entry = fill_price

        self._positions[symbol] = PositionDTO(
            symbol=symbol,
            quantity=new_qty,
            average_entry_price=new_entry,
            realized_pnl=new_pnl,
            unrealized_pnl=Decimal("0.00"),
            updated_at=timestamp,
        )

    def get_order(self, order_id: str) -> ExecutionReportDTO | None:
        """Retrieve order by order_id."""
        with self._lock:
            return self._orders.get(order_id)

    def get_order_by_client_id(self, client_order_id: str) -> ExecutionReportDTO | None:
        """Retrieve order by client_order_id."""
        with self._lock:
            order_id = self._client_id_map.get(client_order_id)
            if order_id is None:
                return None
            return self._orders.get(order_id)

    def get_open_orders(self, symbol: str | None = None) -> list[ExecutionReportDTO]:
        """Retrieve all currently active non-terminal orders."""
        with self._lock:
            open_orders: list[ExecutionReportDTO] = []
            for order in self._orders.values():
                if order.state not in TERMINAL_STATES:
                    if symbol is None or order.symbol == symbol:
                        open_orders.append(order)
            return open_orders

    def get_all_orders(self) -> list[ExecutionReportDTO]:
        """Retrieve all orders in the ledger."""
        with self._lock:
            return list(self._orders.values())

    def get_position(self, symbol: str) -> PositionDTO:
        """Retrieve current position for a given symbol."""
        with self._lock:
            return self._positions.get(
                symbol,
                PositionDTO(
                    symbol=symbol,
                    quantity=Decimal("0.00"),
                    average_entry_price=Decimal("0.00"),
                    realized_pnl=Decimal("0.00"),
                    unrealized_pnl=Decimal("0.00"),
                ),
            )

    def get_all_positions(self) -> dict[str, PositionDTO]:
        """Retrieve snapshot of all positions."""
        with self._lock:
            return dict(self._positions)
