"""Phase 13: Dashboard & CLI subsystem for institutional market monitoring."""

from tradingagents.dashboard.cli import run_cli
from tradingagents.dashboard.exporter import DashboardExporter
from tradingagents.dashboard.formatter import DashboardFormatter
from tradingagents.dashboard.models import (
    DashboardSnapshotDTO,
    ExecutionViewDTO,
    IndicatorViewDTO,
    OrderSummaryDTO,
    ProbabilityViewDTO,
    RiskViewDTO,
    StructureViewDTO,
    SynthesisViewDTO,
)
from tradingagents.dashboard.service import DashboardService

__all__ = [
    # Models
    "IndicatorViewDTO",
    "StructureViewDTO",
    "ProbabilityViewDTO",
    "RiskViewDTO",
    "SynthesisViewDTO",
    "OrderSummaryDTO",
    "ExecutionViewDTO",
    "DashboardSnapshotDTO",
    # Service
    "DashboardService",
    # Presenters
    "DashboardFormatter",
    "DashboardExporter",
    # CLI
    "run_cli",
]
