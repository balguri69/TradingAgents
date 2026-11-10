"""Strongly typed, immutable Data Transfer Objects for Phase 10: Multi-Agent Orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from tradingagents.dataflows.dto.validation import (
    validate_non_negative_decimal,
    validate_utc_datetime,
)
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.orchestration.enums import (
    ConvictionTier,
    DirectionalBias,
    MarketPhase,
    RiskLevel,
)

PRECISION_TWO = Decimal("0.01")
HUNDRED = Decimal("100.00")
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ProbabilityBreakdownDTO:
    """Mathematical probability distribution across directional states."""

    bullish: Decimal = Decimal("33.33")
    bearish: Decimal = Decimal("33.33")
    neutral: Decimal = Decimal("33.34")

    def __post_init__(self) -> None:
        validate_non_negative_decimal(self.bullish, "bullish")
        validate_non_negative_decimal(self.bearish, "bearish")
        validate_non_negative_decimal(self.neutral, "neutral")
        total = self.bullish + self.bearish + self.neutral
        # Allow tiny epsilon for floating precision before quantize
        if abs(total - HUNDRED) > Decimal("0.05"):
            raise DTOValidationError(
                f"Probabilities must sum to 100.00, got {total} (bullish={self.bullish}, bearish={self.bearish}, neutral={self.neutral})"
            )


@dataclass(frozen=True)
class TechnicalAssessmentDTO:
    """Specialized evaluation from the Technical Analysis Agent."""

    bias: DirectionalBias
    score: Decimal
    trend_regime: str
    volatility_regime: str
    momentum_state: str
    signals: tuple[str, ...]
    contributing_indicators: tuple[str, ...]
    reasoning: str

    def __post_init__(self) -> None:
        if not isinstance(self.bias, DirectionalBias):
            raise DTOValidationError(f"bias must be DirectionalBias, got {type(self.bias)}")
        if not isinstance(self.score, Decimal):
            raise DTOValidationError(f"score must be Decimal, got {type(self.score)}")
        if not (-HUNDRED <= self.score <= HUNDRED):
            raise DTOValidationError(f"score must be between -100.00 and 100.00, got {self.score}")


@dataclass(frozen=True)
class MarketStructureAssessmentDTO:
    """Specialized evaluation from the Market Structure Agent."""

    bias: DirectionalBias
    score: Decimal
    market_phase: MarketPhase
    dealing_range_zone: str
    active_order_blocks_count: int
    unmitigated_fvgs_count: int
    sweeps_detected: tuple[str, ...]
    key_levels: tuple[Decimal, ...]
    reasoning: str

    def __post_init__(self) -> None:
        if not isinstance(self.bias, DirectionalBias):
            raise DTOValidationError(f"bias must be DirectionalBias, got {type(self.bias)}")
        if not isinstance(self.score, Decimal):
            raise DTOValidationError(f"score must be Decimal, got {type(self.score)}")
        if not (-HUNDRED <= self.score <= HUNDRED):
            raise DTOValidationError(f"score must be between -100.00 and 100.00, got {self.score}")
        if not isinstance(self.market_phase, MarketPhase):
            raise DTOValidationError(f"market_phase must be MarketPhase, got {type(self.market_phase)}")


@dataclass(frozen=True)
class ProbabilityAssessmentDTO:
    """Specialized evaluation from the Probability Agent."""

    directional_bias: DirectionalBias
    breakdown: ProbabilityBreakdownDTO
    total_score: Decimal
    confidence: Decimal
    top_positive_factors: tuple[str, ...]
    top_negative_factors: tuple[str, ...]
    reasoning: str

    def __post_init__(self) -> None:
        if not isinstance(self.directional_bias, DirectionalBias):
            raise DTOValidationError(f"directional_bias must be DirectionalBias, got {type(self.directional_bias)}")
        if not isinstance(self.breakdown, ProbabilityBreakdownDTO):
            raise DTOValidationError(f"breakdown must be ProbabilityBreakdownDTO, got {type(self.breakdown)}")
        if not (ZERO <= self.confidence <= HUNDRED):
            raise DTOValidationError(f"confidence must be between 0.00 and 100.00, got {self.confidence}")


@dataclass(frozen=True)
class RiskContextAssessmentDTO:
    """Specialized evaluation from the Risk Context Agent."""

    risk_level: RiskLevel
    volatility_state: str
    signal_conflict_ratio: Decimal
    invalidation_risk: str
    is_tradeable_regime: bool
    risk_factors: tuple[str, ...]
    reasoning: str

    def __post_init__(self) -> None:
        if not isinstance(self.risk_level, RiskLevel):
            raise DTOValidationError(f"risk_level must be RiskLevel, got {type(self.risk_level)}")
        if not (ZERO <= self.signal_conflict_ratio <= Decimal("1.00")):
            raise DTOValidationError(
                f"signal_conflict_ratio must be in [0.00, 1.00], got {self.signal_conflict_ratio}"
            )


@dataclass(frozen=True)
class ConfidenceAssessmentDTO:
    """Specialized evaluation from the Confidence & Evidence Agent."""

    composite_confidence: Decimal
    conviction_tier: ConvictionTier
    agent_agreement_ratio: Decimal
    evidence_breadth_score: Decimal
    conflict_penalty: Decimal
    reasoning: str

    def __post_init__(self) -> None:
        if not (ZERO <= self.composite_confidence <= HUNDRED):
            raise DTOValidationError(f"composite_confidence must be in [0, 100], got {self.composite_confidence}")
        if not isinstance(self.conviction_tier, ConvictionTier):
            raise DTOValidationError(f"conviction_tier must be ConvictionTier, got {type(self.conviction_tier)}")
        if not (ZERO <= self.agent_agreement_ratio <= Decimal("1.00")):
            raise DTOValidationError(
                f"agent_agreement_ratio must be in [0.00, 1.00], got {self.agent_agreement_ratio}"
            )
        if not (ZERO <= self.evidence_breadth_score <= Decimal("1.00")):
            raise DTOValidationError(
                f"evidence_breadth_score must be in [0.00, 1.00], got {self.evidence_breadth_score}"
            )


@dataclass(frozen=True)
class MarketAssessmentDTO:
    """Final unified institutional market assessment produced by Phase 10 orchestration.
    
    This immutable DTO adheres strictly to all Phase 10 requirements:
    - Zero execution/order/trade artifacts.
    - Pure point-in-time analytical synthesis.
    """

    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    directional_bias: DirectionalBias
    confidence: Decimal
    probability_breakdown: ProbabilityBreakdownDTO
    evidence_summary: tuple[str, ...]
    supporting_features: tuple[str, ...]
    conflicting_features: tuple[str, ...]
    final_reasoning: str

    # Deep Agent Sub-Assessments
    technical_assessment: TechnicalAssessmentDTO
    structure_assessment: MarketStructureAssessmentDTO
    probability_assessment: ProbabilityAssessmentDTO
    risk_assessment: RiskContextAssessmentDTO
    confidence_assessment: ConfidenceAssessmentDTO
    is_actionable: bool = False

    def __post_init__(self) -> None:
        if not self.symbol or not isinstance(self.symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        if not isinstance(self.timeframe, Timeframe):
            raise DTOValidationError(f"timeframe must be a Timeframe instance, got {type(self.timeframe)}")
        validate_utc_datetime(self.timestamp, "timestamp")
        if not isinstance(self.directional_bias, DirectionalBias):
            raise DTOValidationError(f"directional_bias must be DirectionalBias, got {type(self.directional_bias)}")
        if not (ZERO <= self.confidence <= HUNDRED):
            raise DTOValidationError(f"confidence must be in [0, 100], got {self.confidence}")
        if not isinstance(self.probability_breakdown, ProbabilityBreakdownDTO):
            raise DTOValidationError("probability_breakdown must be ProbabilityBreakdownDTO")
