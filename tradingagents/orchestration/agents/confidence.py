"""Deterministic Confidence & Evidence Agent synthesizing multi-agent agreement and evidence breadth."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping

from tradingagents.dataflows.dto.features import BaseFeatureDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.orchestration.agents.base import BaseMarketAgent
from tradingagents.orchestration.dto import (
    ConfidenceAssessmentDTO,
    MarketStructureAssessmentDTO,
    ProbabilityAssessmentDTO,
    RiskContextAssessmentDTO,
    TechnicalAssessmentDTO,
)
from tradingagents.orchestration.enums import (
    AgentRole,
    ConvictionTier,
    DirectionalBias,
)

PRECISION_TWO = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")
ONE = Decimal("1.00")


class ConfidenceEvidenceAgent(BaseMarketAgent):
    """Specialized agent synthesizing cross-agent agreement, evidence completeness, and conviction tiers."""

    @property
    def role(self) -> AgentRole:
        return AgentRole.CONFIDENCE_EVIDENCE

    def analyze(
        self,
        symbol: str,
        timeframe: Timeframe,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
        as_of: datetime | None = None,
        technical_assessment: TechnicalAssessmentDTO | None = None,
        structure_assessment: MarketStructureAssessmentDTO | None = None,
        probability_assessment: ProbabilityAssessmentDTO | None = None,
        risk_assessment: RiskContextAssessmentDTO | None = None,
    ) -> ConfidenceAssessmentDTO:
        self._validate_inputs(symbol, timeframe, as_of)

        # 1. Cross-Agent Directional Agreement Ratio
        biases: list[DirectionalBias] = []
        if technical_assessment:
            biases.append(technical_assessment.bias)
        if structure_assessment:
            biases.append(structure_assessment.bias)
        if probability_assessment:
            biases.append(probability_assessment.directional_bias)

        if not biases:
            agreement_ratio = ZERO
            dominant_bias = DirectionalBias.NEUTRAL
        else:
            bull_votes = sum(1 for b in biases if b == DirectionalBias.BULLISH)
            bear_votes = sum(1 for b in biases if b == DirectionalBias.BEARISH)
            neutral_votes = sum(1 for b in biases if b == DirectionalBias.NEUTRAL)

            max_votes = max(bull_votes, bear_votes, neutral_votes)
            agreement_ratio = (Decimal(str(max_votes)) / Decimal(str(len(biases)))).quantize(
                PRECISION_TWO, rounding=ROUND_HALF_UP
            )

        # 2. Evidence Breadth Score (Core feature categories observed vs target benchmark of 6)
        core_categories = {"ema", "sma", "rsi", "macd", "vwap", "bollinger", "order_block", "fvg", "bos", "choch", "sweep", "premium_discount"}
        observed_categories = set()
        for k, v in features.items():
            name = getattr(v, "feature_name", k).lower()
            for cat in core_categories:
                if cat in name:
                    observed_categories.add(cat)

        target_count = Decimal("6.0")
        breadth_ratio = min(ONE, (Decimal(str(len(observed_categories))) / target_count)).quantize(
            PRECISION_TWO, rounding=ROUND_HALF_UP
        )

        # Zero evidence -> Zero confidence
        if breadth_ratio == ZERO:
            return ConfidenceAssessmentDTO(
                composite_confidence=ZERO,
                conviction_tier=ConvictionTier.VERY_LOW,
                agent_agreement_ratio=ZERO,
                evidence_breadth_score=ZERO,
                conflict_penalty=ZERO,
                reasoning="Confidence zero: No active market features observed in store.",
            )

        # 3. Base Confidence from Probability Agent
        base_confidence = probability_assessment.confidence if probability_assessment else Decimal("50.0")

        # 4. Conflict Penalty from Risk Agent
        conflict_ratio = risk_assessment.signal_conflict_ratio if risk_assessment else ZERO
        conflict_penalty = (conflict_ratio * Decimal("35.0")).quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)

        # Composite Confidence Formula:
        # 40% Base Probability Engine Confidence
        # 35% Cross-Agent Agreement
        # 25% Evidence Breadth
        # Less Conflict Penalty
        raw_confidence = (
            (base_confidence * Decimal("0.40"))
            + (agreement_ratio * HUNDRED * Decimal("0.35"))
            + (breadth_ratio * HUNDRED * Decimal("0.25"))
            - conflict_penalty
        )
        composite = max(ZERO, min(HUNDRED, raw_confidence)).quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)

        # 5. Conviction Tier Classification
        if composite >= Decimal("80.00"):
            conviction_tier = ConvictionTier.VERY_HIGH
        elif composite >= Decimal("65.00"):
            conviction_tier = ConvictionTier.HIGH
        elif composite >= Decimal("50.00"):
            conviction_tier = ConvictionTier.MODERATE
        elif composite >= Decimal("35.00"):
            conviction_tier = ConvictionTier.LOW
        else:
            conviction_tier = ConvictionTier.VERY_LOW

        reasoning = (
            f"Confidence Synthesis: {composite}% ({conviction_tier.value} Conviction). "
            f"Agent Agreement: {agreement_ratio * HUNDRED:.0f}%, "
            f"Evidence Breadth: {breadth_ratio * HUNDRED:.0f}% ({len(observed_categories)}/6 categories), "
            f"Conflict Penalty: -{conflict_penalty}%."
        )

        return ConfidenceAssessmentDTO(
            composite_confidence=composite,
            conviction_tier=conviction_tier,
            agent_agreement_ratio=agreement_ratio,
            evidence_breadth_score=breadth_ratio,
            conflict_penalty=conflict_penalty,
            reasoning=reasoning,
        )
