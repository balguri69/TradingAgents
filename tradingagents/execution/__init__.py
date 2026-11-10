"""Phase 12: Execution Engine subsystem.

Transforms institutional market assessments and risk safeguards into
deterministic order intents, broker instructions, and execution state tracking.
"""

from tradingagents.execution.adapters import PaperBrokerAdapter
from tradingagents.execution.builder import OrderIntentBuilder
from tradingagents.execution.config import ExecutionConfig
from tradingagents.execution.dto import (
    ExecutionReportDTO,
    FillDTO,
    OrderIntentDTO,
    PositionDTO,
)
from tradingagents.execution.engine import ExecutionEngine
from tradingagents.execution.enums import (
    ExecutionStatus,
    OrderSide,
    OrderState,
    OrderType,
    TimeInForce,
    TradeDirection,
)
from tradingagents.execution.planner import ExecutionPlanner
from tradingagents.execution.protocols import BrokerAdapter, ExecutionEngineProtocol

__all__ = [
    # Enums
    "TradeDirection",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "OrderState",
    "ExecutionStatus",
    # Config
    "ExecutionConfig",
    # DTOs
    "OrderIntentDTO",
    "FillDTO",
    "ExecutionReportDTO",
    "PositionDTO",
    # Protocols
    "BrokerAdapter",
    "ExecutionEngineProtocol",
    # Components
    "OrderIntentBuilder",
    "ExecutionPlanner",
    "PaperBrokerAdapter",
    "ExecutionEngine",
]
