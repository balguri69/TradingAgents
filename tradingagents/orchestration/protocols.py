"""Protocols and interfaces for Phase 10: Multi-Agent Orchestration."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Protocol, runtime_checkable

from tradingagents.dataflows.dto.features import BaseFeatureDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.orchestration.dto import MarketAssessmentDTO
from tradingagents.orchestration.enums import AgentRole


@runtime_checkable
class MarketAgent(Protocol):
    """Protocol satisfied by deterministic specialized analytical agents."""

    @property
    def role(self) -> AgentRole:
        """The specialized single-responsibility role of this agent."""
        ...

    def analyze(
        self,
        symbol: str,
        timeframe: Timeframe,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
        as_of: datetime | None = None,
    ) -> Any:
        """Perform specialized deterministic analysis over point-in-time features."""
        ...


@runtime_checkable
class MarketOrchestrator(Protocol):
    """Protocol satisfied by the institutional multi-agent orchestrator."""

    def assess(
        self,
        symbol: str,
        timeframe: Timeframe,
        as_of: datetime | None = None,
        current_price: Decimal | None = None,
    ) -> MarketAssessmentDTO:
        """Produce an end-to-end unified institutional market assessment."""
        ...

    def assess_from_features(
        self,
        symbol: str,
        timeframe: Timeframe,
        timestamp: datetime,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
    ) -> MarketAssessmentDTO:
        """Assess directly from an in-memory feature mapping."""
        ...
