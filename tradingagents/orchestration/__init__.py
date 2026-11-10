"""Multi-Agent Orchestration subsystem (Phase 10).

Deterministic, modular orchestration layer synthesizing:
- FeatureStore
- Indicator Engine
- Market Structure Engine
- Probability Engine
"""

from __future__ import annotations

from tradingagents.orchestration.adapters import LLMNarrativeAdapter
from tradingagents.orchestration.agents import (
    BaseMarketAgent,
    ConfidenceEvidenceAgent,
    FinalSynthesisAgent,
    MarketStructureAgent,
    ProbabilityAgent,
    RiskContextAgent,
    TechnicalAnalysisAgent,
)
from tradingagents.orchestration.dto import (
    ConfidenceAssessmentDTO,
    MarketAssessmentDTO,
    MarketStructureAssessmentDTO,
    ProbabilityAssessmentDTO,
    ProbabilityBreakdownDTO,
    RiskContextAssessmentDTO,
    TechnicalAssessmentDTO,
)
from tradingagents.orchestration.enums import (
    AgentRole,
    ConvictionTier,
    DirectionalBias,
    MarketPhase,
    RiskLevel,
)
from tradingagents.orchestration.orchestrator import (
    DEFAULT_MONITORED_FEATURES,
    MultiAgentOrchestrator,
)
from tradingagents.orchestration.protocols import (
    MarketAgent,
    MarketOrchestrator,
)

__all__ = [
    # Enums
    "DirectionalBias",
    "RiskLevel",
    "MarketPhase",
    "ConvictionTier",
    "AgentRole",
    # DTOs
    "ProbabilityBreakdownDTO",
    "TechnicalAssessmentDTO",
    "MarketStructureAssessmentDTO",
    "ProbabilityAssessmentDTO",
    "RiskContextAssessmentDTO",
    "ConfidenceAssessmentDTO",
    "MarketAssessmentDTO",
    # Protocols
    "MarketAgent",
    "MarketOrchestrator",
    # Agents
    "BaseMarketAgent",
    "TechnicalAnalysisAgent",
    "MarketStructureAgent",
    "ProbabilityAgent",
    "RiskContextAgent",
    "ConfidenceEvidenceAgent",
    "FinalSynthesisAgent",
    # Orchestrator
    "MultiAgentOrchestrator",
    "DEFAULT_MONITORED_FEATURES",
    # Optional Adapters
    "LLMNarrativeAdapter",
]
