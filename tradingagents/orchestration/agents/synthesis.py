"""Deterministic Final Synthesis Agent unifying specialized agent outputs into MarketAssessmentDTO."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping

from tradingagents.dataflows.dto.features import BaseFeatureDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.orchestration.agents.base import BaseMarketAgent
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
    DirectionalBias,
    RiskLevel,
)


class FinalSynthesisAgent(BaseMarketAgent):
    """Specialized agent synthesizing evidence, resolving conflict, and building the final MarketAssessmentDTO."""

    @property
    def role(self) -> AgentRole:
        return AgentRole.FINAL_SYNTHESIS

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
        confidence_assessment: ConfidenceAssessmentDTO | None = None,
    ) -> MarketAssessmentDTO:
        self._validate_inputs(symbol, timeframe, as_of)

        effective_ts = as_of if as_of is not None else datetime.now(timezone.utc)

        # 1. Resolve Directional Bias
        t_bias = technical_assessment.bias if technical_assessment else DirectionalBias.NEUTRAL
        s_bias = structure_assessment.bias if structure_assessment else DirectionalBias.NEUTRAL
        p_bias = probability_assessment.directional_bias if probability_assessment else DirectionalBias.NEUTRAL
        risk_lvl = risk_assessment.risk_level if risk_assessment else RiskLevel.LOW

        # If risk is extreme or conflict is high, bias degrades to NEUTRAL
        if risk_lvl == RiskLevel.EXTREME or (risk_assessment and not risk_assessment.is_tradeable_regime):
            final_bias = DirectionalBias.NEUTRAL
        elif s_bias == t_bias and s_bias != DirectionalBias.NEUTRAL:
            # High institutional conviction: Structure and Technical agree
            final_bias = s_bias
        elif s_bias != DirectionalBias.NEUTRAL and t_bias == DirectionalBias.NEUTRAL:
            # Structure leads, technical is waiting
            final_bias = s_bias
        elif t_bias != DirectionalBias.NEUTRAL and s_bias == DirectionalBias.NEUTRAL:
            # Technical leads, structure consolidating
            final_bias = t_bias
        elif s_bias != t_bias and s_bias != DirectionalBias.NEUTRAL and t_bias != DirectionalBias.NEUTRAL:
            # Direct conflict -> Neutralize
            final_bias = DirectionalBias.NEUTRAL
        else:
            final_bias = p_bias

        # 2. Partition Supporting vs Conflicting Evidence
        supporting_features: list[str] = []
        conflicting_features: list[str] = []
        evidence_summary: list[str] = []

        if final_bias == DirectionalBias.BULLISH:
            if structure_assessment and structure_assessment.bias == DirectionalBias.BULLISH:
                supporting_features.append(f"Market Structure Bullish: {structure_assessment.market_phase.value} phase")
            elif structure_assessment and structure_assessment.bias == DirectionalBias.BEARISH:
                conflicting_features.append("Opposing Market Structure: Bearish phase active")

            if technical_assessment and technical_assessment.bias == DirectionalBias.BULLISH:
                supporting_features.extend(technical_assessment.signals[:2])
            elif technical_assessment and technical_assessment.bias == DirectionalBias.BEARISH:
                conflicting_features.extend(technical_assessment.signals[:2])

            if probability_assessment:
                supporting_features.extend(probability_assessment.top_positive_factors[:2])
                conflicting_features.extend(probability_assessment.top_negative_factors[:2])

        elif final_bias == DirectionalBias.BEARISH:
            if structure_assessment and structure_assessment.bias == DirectionalBias.BEARISH:
                supporting_features.append(f"Market Structure Bearish: {structure_assessment.market_phase.value} phase")
            elif structure_assessment and structure_assessment.bias == DirectionalBias.BULLISH:
                conflicting_features.append("Opposing Market Structure: Bullish phase active")

            if technical_assessment and technical_assessment.bias == DirectionalBias.BEARISH:
                supporting_features.extend(technical_assessment.signals[:2])
            elif technical_assessment and technical_assessment.bias == DirectionalBias.BULLISH:
                conflicting_features.extend(technical_assessment.signals[:2])

            if probability_assessment:
                supporting_features.extend(probability_assessment.top_negative_factors[:2])
                conflicting_features.extend(probability_assessment.top_positive_factors[:2])

        else:  # NEUTRAL
            supporting_features.append("Balanced or conflicting directional signals prevent strong directional edge")
            if structure_assessment:
                conflicting_features.append(f"Structure Phase: {structure_assessment.market_phase.value}")
            if technical_assessment:
                conflicting_features.append(f"Technical Regime: {technical_assessment.trend_regime}")

        # Assemble Evidence Summary (Top 3-4 key bullets)
        if structure_assessment:
            evidence_summary.append(f"Structure: {structure_assessment.market_phase.value} ({structure_assessment.dealing_range_zone})")
        if technical_assessment:
            evidence_summary.append(f"Technical: {technical_assessment.trend_regime} ({technical_assessment.momentum_state})")
        if probability_assessment:
            evidence_summary.append(
                f"Probabilities: {probability_assessment.breakdown.bullish}% Bull / "
                f"{probability_assessment.breakdown.bearish}% Bear / "
                f"{probability_assessment.breakdown.neutral}% Neutral"
            )
        if risk_assessment:
            evidence_summary.append(f"Risk: {risk_assessment.risk_level.value} (Conflict: {risk_assessment.signal_conflict_ratio:.2f})")

        # 3. Construct Final Executive Institutional Reasoning
        confidence_val = confidence_assessment.composite_confidence if confidence_assessment else Decimal("50.0")
        conviction_str = confidence_assessment.conviction_tier.value if confidence_assessment else "MODERATE"
        tradeable_str = "Tradeable" if (risk_assessment and risk_assessment.is_tradeable_regime) else "Non-Tradeable / High Friction"

        final_reasoning = (
            f"=== INSTITUTIONAL MARKET ASSESSMENT: {symbol} [{timeframe.value}] ===\n"
            f"Directional Thesis: {final_bias.value} | Conviction: {conviction_str} ({confidence_val}%)\n"
            f"Regime Status: {tradeable_str} (Risk: {risk_lvl.value})\n\n"
            f"1. Executive Synthesis:\n"
            f"   The market exhibits a {final_bias.value.lower()} posture supported by {len(supporting_features)} primary factors, "
            f"   with {len(conflicting_features)} counter-trend/frictional friction points noted.\n\n"
            f"2. Analytical Disciplines:\n"
            f"   - {structure_assessment.reasoning if structure_assessment else 'Structure: No data'}\n"
            f"   - {technical_assessment.reasoning if technical_assessment else 'Technical: No data'}\n"
            f"   - {probability_assessment.reasoning if probability_assessment else 'Probability: No data'}\n"
            f"   - {risk_assessment.reasoning if risk_assessment else 'Risk: No data'}\n"
            f"   - {confidence_assessment.reasoning if confidence_assessment else 'Confidence: No data'}\n\n"
            f"3. Key Drivers & Invalidation:\n"
            f"   - Primary Supports: {'; '.join(supporting_features[:3])}\n"
            f"   - Watch Invalidation: {'; '.join(conflicting_features[:2]) if conflicting_features else 'None detected'}"
        )

        # 4. Actionability
        is_actionable = (
            final_bias != DirectionalBias.NEUTRAL
            and confidence_val >= Decimal("50.00")
            and (risk_assessment is None or risk_assessment.is_tradeable_regime)
        )

        return MarketAssessmentDTO(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=effective_ts,
            directional_bias=final_bias,
            confidence=confidence_val,
            probability_breakdown=probability_assessment.breakdown if probability_assessment else ProbabilityBreakdownDTO(),
            evidence_summary=tuple(evidence_summary),
            supporting_features=tuple(supporting_features),
            conflicting_features=tuple(conflicting_features),
            final_reasoning=final_reasoning,
            technical_assessment=technical_assessment,
            structure_assessment=structure_assessment,
            probability_assessment=probability_assessment,
            risk_assessment=risk_assessment,
            confidence_assessment=confidence_assessment,
            is_actionable=is_actionable,
        )
