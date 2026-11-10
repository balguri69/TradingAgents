"""Protocols and interfaces for Phase 12 Execution Engine."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, Sequence, runtime_checkable

from tradingagents.execution.dto import ExecutionReportDTO, OrderIntentDTO, PositionDTO
from tradingagents.orchestration.dto import MarketAssessmentDTO
from tradingagents.risk.dto import RiskAssessmentDTO


@runtime_checkable
class BrokerAdapter(Protocol):
    """Abstract protocol for order routing and broker connectivity."""

    def submit_order(self, intent: OrderIntentDTO) -> ExecutionReportDTO:
        """Submit an order intent to the broker."""
        ...

    def cancel_order(self, order_id: str) -> ExecutionReportDTO:
        """Cancel an open order by broker order ID."""
        ...

    def get_order_status(self, order_id: str) -> ExecutionReportDTO | None:
        """Retrieve point-in-time status report of an order."""
        ...

    def get_balance(self, asset: str) -> Decimal:
        """Retrieve liquid balance for an asset denomination."""
        ...

    def get_open_orders(self, symbol: str | None = None) -> Sequence[ExecutionReportDTO]:
        """Retrieve all currently active open orders."""
        ...

    def get_position(self, symbol: str) -> PositionDTO:
        """Retrieve current position for a given symbol."""
        ...


@runtime_checkable
class ExecutionEngineProtocol(Protocol):
    """Abstract protocol for the institutional execution orchestration engine."""

    def plan(
        self,
        assessment: MarketAssessmentDTO,
        risk: RiskAssessmentDTO,
        current_price: Decimal | None = None,
        quantity: Decimal | None = None,
    ) -> OrderIntentDTO:
        """Evaluate market and risk assessment to produce an OrderIntentDTO."""
        ...

    def execute(self, intent: OrderIntentDTO) -> ExecutionReportDTO:
        """Execute a planned OrderIntentDTO against the configured broker adapter."""
        ...

    def assess_and_execute(
        self,
        assessment: MarketAssessmentDTO,
        risk: RiskAssessmentDTO,
        current_price: Decimal | None = None,
        quantity: Decimal | None = None,
    ) -> ExecutionReportDTO:
        """End-to-end pipeline: plan intent and route to broker."""
        ...
