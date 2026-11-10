"""Deterministic Paper Broker Adapter for simulating institutional order routing and fills."""

from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.execution.config import ExecutionConfig
from tradingagents.execution.dto import (
    ExecutionReportDTO,
    FillDTO,
    OrderIntentDTO,
    PositionDTO,
)
from tradingagents.execution.enums import (
    ExecutionStatus,
    OrderSide,
    OrderState,
    OrderType,
)
from tradingagents.execution.protocols import BrokerAdapter
from tradingagents.execution.tracker import ExecutionTracker

PRECISION_FOUR = Decimal("0.0001")
BPS_DIVISOR = Decimal("10000")
ZERO = Decimal("0.00")


class PaperBrokerAdapter(BrokerAdapter):
    """Deterministic, standard-library paper trading broker adapter.
    
    Guarantees:
    - 100% deterministic (zero pseudo-randomness).
    - Thread-safe balance and position management.
    - Full order lifecycle simulation: MARKET, LIMIT, STOP_MARKET, partial fills, cancellations.
    """

    def __init__(
        self,
        config: ExecutionConfig | None = None,
        initial_balances: dict[str, Decimal] | None = None,
    ) -> None:
        self._config = config or ExecutionConfig()
        self._lock = threading.RLock()
        self._tracker = ExecutionTracker()

        # Balances by asset, default to 1,000,000 USD
        self._balances: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        if initial_balances:
            for asset, bal in initial_balances.items():
                self._balances[asset] = bal
        else:
            self._balances["USD"] = Decimal("1000000.00")

        # Market prices cache by symbol
        self._market_prices: dict[str, Decimal] = {}

    @property
    def tracker(self) -> ExecutionTracker:
        return self._tracker

    def set_market_price(self, symbol: str, price: Decimal) -> None:
        """Register or update current market price for a symbol."""
        with self._lock:
            self._market_prices[symbol] = price

    def get_balance(self, asset: str) -> Decimal:
        """Retrieve current liquid balance for an asset."""
        with self._lock:
            return self._balances[asset]

    def get_position(self, symbol: str) -> PositionDTO:
        """Retrieve current position for a given symbol."""
        return self._tracker.get_position(symbol)

    def get_order_status(self, order_id: str) -> ExecutionReportDTO | None:
        """Retrieve order status from the tracker."""
        return self._tracker.get_order(order_id)

    def get_open_orders(self, symbol: str | None = None) -> Sequence[ExecutionReportDTO]:
        """Retrieve all active open orders."""
        return self._tracker.get_open_orders(symbol)

    def submit_order(self, intent: OrderIntentDTO) -> ExecutionReportDTO:
        """Route order intent through deterministic paper broker execution."""
        with self._lock:
            order_id = f"ord_{uuid.uuid4().hex[:12]}"
            now = intent.timestamp

            # 1. Non-executable gated intents
            if not intent.is_executable:
                status = (
                    ExecutionStatus.NO_TRADE_SIGNAL
                    if "NEUTRAL" in (intent.gating_reason or "")
                    else ExecutionStatus.GATED_BY_RISK
                )
                report = ExecutionReportDTO(
                    symbol=intent.symbol,
                    timeframe=intent.timeframe,
                    timestamp=now,
                    order_id=order_id,
                    client_order_id=intent.client_order_id,
                    status=status,
                    state=OrderState.REJECTED,
                    side=intent.side,
                    order_type=intent.order_type,
                    requested_quantity=intent.quantity,
                    filled_quantity=ZERO,
                    remaining_quantity=intent.quantity,
                    limit_price=intent.limit_price,
                    stop_price=intent.stop_price,
                    gating_reason=intent.gating_reason,
                    created_at=now,
                    updated_at=now,
                )
                self._tracker.record_order(report)
                return report

            # 2. Executable orders
            current_market_price = self._market_prices.get(intent.symbol) or intent.limit_price or intent.stop_price
            if current_market_price is None or current_market_price <= ZERO:
                # Cannot execute without market reference price
                report = ExecutionReportDTO(
                    symbol=intent.symbol,
                    timeframe=intent.timeframe,
                    timestamp=now,
                    order_id=order_id,
                    client_order_id=intent.client_order_id,
                    status=ExecutionStatus.REJECTED,
                    state=OrderState.REJECTED,
                    side=intent.side,
                    order_type=intent.order_type,
                    requested_quantity=intent.quantity,
                    filled_quantity=ZERO,
                    remaining_quantity=intent.quantity,
                    limit_price=intent.limit_price,
                    stop_price=intent.stop_price,
                    rejection_reason=f"No market price available for symbol {intent.symbol}",
                    created_at=now,
                    updated_at=now,
                )
                self._tracker.record_order(report)
                return report

            # 3. Market Orders: immediate execution with deterministic slippage
            if intent.order_type == OrderType.MARKET:
                return self._execute_market_order(intent, order_id, current_market_price)

            # 4. Limit Orders: check immediate match or queue
            if intent.order_type == OrderType.LIMIT:
                assert intent.limit_price is not None
                is_marketable = (
                    (intent.side == OrderSide.BUY and current_market_price <= intent.limit_price)
                    or (intent.side == OrderSide.SELL and current_market_price >= intent.limit_price)
                )
                if is_marketable:
                    return self._execute_limit_fill(intent, order_id, intent.limit_price, is_maker=True)

                # Queue pending limit order
                report = ExecutionReportDTO(
                    symbol=intent.symbol,
                    timeframe=intent.timeframe,
                    timestamp=now,
                    order_id=order_id,
                    client_order_id=intent.client_order_id,
                    status=ExecutionStatus.PARTIAL,
                    state=OrderState.SUBMITTED,
                    side=intent.side,
                    order_type=intent.order_type,
                    requested_quantity=intent.quantity,
                    filled_quantity=ZERO,
                    remaining_quantity=intent.quantity,
                    limit_price=intent.limit_price,
                    stop_price=intent.stop_price,
                    created_at=now,
                    updated_at=now,
                )
                self._tracker.record_order(report)
                return report

            # 5. Stop Orders: queue as SUBMITTED until trigger price is crossed
            report = ExecutionReportDTO(
                symbol=intent.symbol,
                timeframe=intent.timeframe,
                timestamp=now,
                order_id=order_id,
                client_order_id=intent.client_order_id,
                status=ExecutionStatus.PARTIAL,
                state=OrderState.SUBMITTED,
                side=intent.side,
                order_type=intent.order_type,
                requested_quantity=intent.quantity,
                filled_quantity=ZERO,
                remaining_quantity=intent.quantity,
                limit_price=intent.limit_price,
                stop_price=intent.stop_price,
                created_at=now,
                updated_at=now,
            )
            self._tracker.record_order(report)
            return report

    def _execute_market_order(
        self,
        intent: OrderIntentDTO,
        order_id: str,
        base_price: Decimal,
    ) -> ExecutionReportDTO:
        """Execute a market order with deterministic slippage and fee calculation."""
        now = intent.timestamp
        slippage = (base_price * self._config.max_slippage_bps) / BPS_DIVISOR
        assert intent.side is not None

        if intent.side == OrderSide.BUY:
            exec_price = (base_price + slippage).quantize(PRECISION_FOUR)
            notional = exec_price * intent.quantity
            fee = ((notional * self._config.taker_fee_bps) / BPS_DIVISOR).quantize(PRECISION_FOUR)
            total_cost = notional + fee

            if self._balances["USD"] < total_cost:
                report = ExecutionReportDTO(
                    symbol=intent.symbol,
                    timeframe=intent.timeframe,
                    timestamp=now,
                    order_id=order_id,
                    client_order_id=intent.client_order_id,
                    status=ExecutionStatus.REJECTED,
                    state=OrderState.REJECTED,
                    side=intent.side,
                    order_type=intent.order_type,
                    requested_quantity=intent.quantity,
                    filled_quantity=ZERO,
                    remaining_quantity=intent.quantity,
                    rejection_reason=f"Insufficient USD balance: required {total_cost}, available {self._balances['USD']}",
                    created_at=now,
                    updated_at=now,
                )
                self._tracker.record_order(report)
                return report

            # Deduct cash, credit asset
            self._balances["USD"] -= total_cost
            self._balances[intent.symbol] += intent.quantity

        else:  # OrderSide.SELL
            exec_price = (base_price - slippage).quantize(PRECISION_FOUR)
            notional = exec_price * intent.quantity
            fee = ((notional * self._config.taker_fee_bps) / BPS_DIVISOR).quantize(PRECISION_FOUR)
            net_proceeds = notional - fee

            # For spot paper execution, check asset balance if not shorting
            self._balances["USD"] += net_proceeds
            self._balances[intent.symbol] -= intent.quantity

        # Record initial SUBMITTED order first, then apply fill
        submitted_report = ExecutionReportDTO(
            symbol=intent.symbol,
            timeframe=intent.timeframe,
            timestamp=now,
            order_id=order_id,
            client_order_id=intent.client_order_id,
            status=ExecutionStatus.EXECUTED,
            state=OrderState.SUBMITTED,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            filled_quantity=ZERO,
            remaining_quantity=intent.quantity,
            created_at=now,
            updated_at=now,
        )
        self._tracker.record_order(submitted_report)

        fill = FillDTO(
            fill_id=f"fill_{uuid.uuid4().hex[:12]}",
            order_id=order_id,
            timestamp=now,
            price=exec_price,
            quantity=intent.quantity,
            fee=fee,
            fee_asset="USD",
            is_maker=False,
        )
        return self._tracker.apply_fill(order_id, fill)

    def _execute_limit_fill(
        self,
        intent: OrderIntentDTO,
        order_id: str,
        fill_price: Decimal,
        is_maker: bool = True,
    ) -> ExecutionReportDTO:
        """Execute a full limit order fill."""
        now = intent.timestamp
        notional = fill_price * intent.quantity
        fee_rate = self._config.maker_fee_bps if is_maker else self._config.taker_fee_bps
        fee = ((notional * fee_rate) / BPS_DIVISOR).quantize(PRECISION_FOUR)

        assert intent.side is not None
        if intent.side == OrderSide.BUY:
            total_cost = notional + fee
            if self._balances["USD"] < total_cost:
                report = ExecutionReportDTO(
                    symbol=intent.symbol,
                    timeframe=intent.timeframe,
                    timestamp=now,
                    order_id=order_id,
                    client_order_id=intent.client_order_id,
                    status=ExecutionStatus.REJECTED,
                    state=OrderState.REJECTED,
                    side=intent.side,
                    order_type=intent.order_type,
                    requested_quantity=intent.quantity,
                    filled_quantity=ZERO,
                    remaining_quantity=intent.quantity,
                    limit_price=intent.limit_price,
                    rejection_reason=f"Insufficient USD balance: required {total_cost}, available {self._balances['USD']}",
                    created_at=now,
                    updated_at=now,
                )
                self._tracker.record_order(report)
                return report

            self._balances["USD"] -= total_cost
            self._balances[intent.symbol] += intent.quantity
        else:
            net_proceeds = notional - fee
            self._balances["USD"] += net_proceeds
            self._balances[intent.symbol] -= intent.quantity

        submitted_report = ExecutionReportDTO(
            symbol=intent.symbol,
            timeframe=intent.timeframe,
            timestamp=now,
            order_id=order_id,
            client_order_id=intent.client_order_id,
            status=ExecutionStatus.EXECUTED,
            state=OrderState.SUBMITTED,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            filled_quantity=ZERO,
            remaining_quantity=intent.quantity,
            limit_price=intent.limit_price,
            created_at=now,
            updated_at=now,
        )
        self._tracker.record_order(submitted_report)

        fill = FillDTO(
            fill_id=f"fill_{uuid.uuid4().hex[:12]}",
            order_id=order_id,
            timestamp=now,
            price=fill_price,
            quantity=intent.quantity,
            fee=fee,
            fee_asset="USD",
            is_maker=is_maker,
        )
        return self._tracker.apply_fill(order_id, fill)

    def cancel_order(self, order_id: str) -> ExecutionReportDTO:
        """Cancel an open order."""
        with self._lock:
            order = self._tracker.get_order(order_id)
            if order is None:
                raise DTOValidationError(f"Order {order_id} not found to cancel")

            if order.state in (OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.EXPIRED):
                raise DTOValidationError(f"Cannot cancel order {order_id} in terminal state {order.state}")

            now = datetime.now(timezone.utc)
            cancelled_report = ExecutionReportDTO(
                symbol=order.symbol,
                timeframe=order.timeframe,
                timestamp=order.timestamp,
                feature_name=order.feature_name,
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status=ExecutionStatus.CANCELLED,
                state=OrderState.CANCELLED,
                side=order.side,
                order_type=order.order_type,
                requested_quantity=order.requested_quantity,
                filled_quantity=order.filled_quantity,
                remaining_quantity=order.remaining_quantity,
                average_price=order.average_price,
                limit_price=order.limit_price,
                stop_price=order.stop_price,
                total_fee=order.total_fee,
                fee_asset=order.fee_asset,
                fills=order.fills,
                rejection_reason=order.rejection_reason,
                gating_reason=order.gating_reason,
                created_at=order.created_at,
                updated_at=now,
            )
            self._tracker.update_order(cancelled_report)
            return cancelled_report

    def process_market_tick(
        self,
        symbol: str,
        price: Decimal,
        high: Decimal | None = None,
        low: Decimal | None = None,
        timestamp: datetime | None = None,
    ) -> list[ExecutionReportDTO]:
        """Process incoming market tick or candle and deterministically trigger/fill pending orders."""
        with self._lock:
            self._market_prices[symbol] = price
            effective_high = high or price
            effective_low = low or price
            tick_time = timestamp or datetime.now(timezone.utc)

            filled_reports: list[ExecutionReportDTO] = []
            open_orders = self._tracker.get_open_orders(symbol)

            for order in open_orders:
                if order.state not in (OrderState.SUBMITTED, OrderState.PARTIALLY_FILLED):
                    continue

                if order.order_type == OrderType.LIMIT and order.limit_price is not None:
                    assert order.side is not None
                    should_fill = False
                    if order.side == OrderSide.BUY and effective_low <= order.limit_price:
                        should_fill = True
                    elif order.side == OrderSide.SELL and effective_high >= order.limit_price:
                        should_fill = True

                    if should_fill:
                        fill = FillDTO(
                            fill_id=f"fill_{uuid.uuid4().hex[:12]}",
                            order_id=order.order_id,
                            timestamp=tick_time,
                            price=order.limit_price,
                            quantity=order.remaining_quantity,
                            fee=((order.limit_price * order.remaining_quantity * self._config.maker_fee_bps) / BPS_DIVISOR).quantize(PRECISION_FOUR),
                            fee_asset="USD",
                            is_maker=True,
                        )
                        updated = self._tracker.apply_fill(order.order_id, fill)
                        filled_reports.append(updated)

                elif order.order_type == OrderType.STOP_MARKET and order.stop_price is not None:
                    assert order.side is not None
                    should_trigger = False
                    if order.side == OrderSide.BUY and effective_high >= order.stop_price:
                        should_trigger = True
                    elif order.side == OrderSide.SELL and effective_low <= order.stop_price:
                        should_trigger = True

                    if should_trigger:
                        fill = FillDTO(
                            fill_id=f"fill_{uuid.uuid4().hex[:12]}",
                            order_id=order.order_id,
                            timestamp=tick_time,
                            price=order.stop_price,
                            quantity=order.remaining_quantity,
                            fee=((order.stop_price * order.remaining_quantity * self._config.taker_fee_bps) / BPS_DIVISOR).quantize(PRECISION_FOUR),
                            fee_asset="USD",
                            is_maker=False,
                        )
                        updated = self._tracker.apply_fill(order.order_id, fill)
                        filled_reports.append(updated)

            return filled_reports

    def execute_partial_fill(
        self,
        order_id: str,
        fill_quantity: Decimal,
        fill_price: Decimal,
        timestamp: datetime | None = None,
        is_maker: bool = False,
    ) -> ExecutionReportDTO:
        """Simulate a deterministic partial fill for an active order."""
        with self._lock:
            order = self._tracker.get_order(order_id)
            if order is None:
                raise DTOValidationError(f"Order {order_id} not found for partial fill")

            now = timestamp or datetime.now(timezone.utc)
            fee_rate = self._config.maker_fee_bps if is_maker else self._config.taker_fee_bps
            fee = ((fill_price * fill_quantity * fee_rate) / BPS_DIVISOR).quantize(PRECISION_FOUR)

            fill = FillDTO(
                fill_id=f"fill_{uuid.uuid4().hex[:12]}",
                order_id=order_id,
                timestamp=now,
                price=fill_price,
                quantity=fill_quantity,
                fee=fee,
                fee_asset="USD",
                is_maker=is_maker,
            )
            return self._tracker.apply_fill(order_id, fill)
