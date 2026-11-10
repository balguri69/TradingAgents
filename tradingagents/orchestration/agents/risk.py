"""Deterministic Risk Context Agent evaluating market volatility, conflict, and regime safety."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping

from tradingagents.dataflows.dto.features import (
    ATRDTO,
    BaseFeatureDTO,
    BollingerBandsDTO,
    PremiumDiscountDTO,
)
from tradingagents.dataflows.enums import Timeframe
from tradingagents.orchestration.agents.base import BaseMarketAgent
from tradingagents.orchestration.dto import (
    MarketStructureAssessmentDTO,
    RiskContextAssessmentDTO,
    TechnicalAssessmentDTO,
)
from tradingagents.orchestration.enums import AgentRole, DirectionalBias, RiskLevel

PRECISION_TWO = Decimal("0.01")
ZERO = Decimal("0.00")
ONE = Decimal("1.00")


class RiskContextAgent(BaseMarketAgent):
    """Specialized agent quantifying volatility conditions, signal divergence, and regime tradeability."""

    @property
    def role(self) -> AgentRole:
        return AgentRole.RISK_CONTEXT

    def analyze(
        self,
        symbol: str,
        timeframe: Timeframe,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
        as_of: datetime | None = None,
        technical_assessment: TechnicalAssessmentDTO | None = None,
        structure_assessment: MarketStructureAssessmentDTO | None = None,
    ) -> RiskContextAssessmentDTO:
        self._validate_inputs(symbol, timeframe, as_of)

        risk_factors: list[str] = []
        conflict_points = Decimal("0.0")
        total_eval_points = Decimal("0.0")

        # 1. Technical vs Market Structure Alignment Conflict
        if technical_assessment and structure_assessment:
            total_eval_points += Decimal("40.0")
            t_bias = technical_assessment.bias
            s_bias = structure_assessment.bias
            if (t_bias == DirectionalBias.BULLISH and s_bias == DirectionalBias.BEARISH) or (
                t_bias == DirectionalBias.BEARISH and s_bias == DirectionalBias.BULLISH
            ):
                conflict_points += Decimal("40.0")
                risk_factors.append(
                    f"Severe Cross-Discipline Conflict: Technical={t_bias.value} vs Market Structure={s_bias.value}"
                )
            elif (t_bias != DirectionalBias.NEUTRAL and s_bias == DirectionalBias.NEUTRAL) or (
                t_bias == DirectionalBias.NEUTRAL and s_bias != DirectionalBias.NEUTRAL
            ):
                conflict_points += Decimal("15.0")
                risk_factors.append("Partial Confirmation: One discipline neutral while other is directional")

        # 2. Dealing Range Location Invalidation Risk
        pd = self._find_feature(features, PremiumDiscountDTO, "premium_discount", "PREMIUM_DISCOUNT", "PREMIUM_DISCOUNT_20")
        invalidation_risk = "MODERATE"
        if pd:
            total_eval_points += Decimal("30.0")
            if structure_assessment:
                s_bias = structure_assessment.bias
                if s_bias == DirectionalBias.BULLISH and pd.zone == "PREMIUM":
                    conflict_points += Decimal("25.0")
                    invalidation_risk = "ELEVATED"
                    risk_factors.append(f"Bullish bias initiated inside deep PREMIUM zone ({pd.percentile:.1f}%)")
                elif s_bias == DirectionalBias.BEARISH and pd.zone == "DISCOUNT":
                    conflict_points += Decimal("25.0")
                    invalidation_risk = "ELEVATED"
                    risk_factors.append(f"Bearish bias initiated inside deep DISCOUNT zone ({pd.percentile:.1f}%)")
                elif (s_bias == DirectionalBias.BULLISH and pd.zone == "DISCOUNT") or (
                    s_bias == DirectionalBias.BEARISH and pd.zone == "PREMIUM"
                ):
                    invalidation_risk = "LOW"

        # 3. Volatility State Quantification
        boll = self._find_feature(features, BollingerBandsDTO, "bollinger", "BOLLINGER", "BB_20_2.0")
        atr = self._find_feature(features, ATRDTO, "atr_14", "ATR_14", "atr", "ATR")
        volatility_state = "NORMAL"

        if boll:
            bandwidth = boll.upper_band - boll.lower_band
            if boll.middle_band > ZERO:
                bw_pct = bandwidth / boll.middle_band
                if bw_pct < Decimal("0.02"):
                    volatility_state = "COMPRESSED"
                    risk_factors.append("Volatility squeeze: Bollinger bandwidth < 2% (Impending breakout)")
                elif bw_pct > Decimal("0.08"):
                    volatility_state = "EXPANDING"
                    risk_factors.append("Elevated volatility: Bollinger bandwidth wide (> 8%)")

        # Calculate Signal Conflict Ratio [0.00, 1.00]
        if total_eval_points > ZERO:
            conflict_ratio = (conflict_points / total_eval_points).quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)
        else:
            conflict_ratio = ZERO

        # Classify Risk Level
        if conflict_ratio >= Decimal("0.70"):
            risk_level = RiskLevel.EXTREME
            invalidation_risk = "IMMEDIATE"
        elif conflict_ratio >= Decimal("0.45") or volatility_state == "EXTREME":
            risk_level = RiskLevel.HIGH
        elif conflict_ratio >= Decimal("0.20") or volatility_state in {"EXPANDING", "COMPRESSED"}:
            risk_level = RiskLevel.MODERATE
        else:
            risk_level = RiskLevel.LOW

        # Tradeable Regime Determination:
        # A market regime is NOT tradeable if risk is EXTREME or conflict >= 0.70
        is_tradeable_regime = (risk_level != RiskLevel.EXTREME) and (conflict_ratio < Decimal("0.70"))

        if not risk_factors:
            risk_factors.append("Low friction: Orderly price discovery and aligned analytical signals")
            reasoning = f"Risk Context: LOW risk (Conflict Ratio: {conflict_ratio}). Market conditions favorable."
        else:
            reasoning = (
                f"Risk Context: {risk_level.value} risk (Conflict Ratio: {conflict_ratio:.2f}, Volatility: {volatility_state}). "
                f"Tradeable: {is_tradeable_regime}. Invalidation: {invalidation_risk}. "
                f"Key risks: {'; '.join(risk_factors[:2])}."
            )

        return RiskContextAssessmentDTO(
            risk_level=risk_level,
            volatility_state=volatility_state,
            signal_conflict_ratio=conflict_ratio,
            invalidation_risk=invalidation_risk,
            is_tradeable_regime=is_tradeable_regime,
            risk_factors=tuple(risk_factors),
            reasoning=reasoning,
        )
