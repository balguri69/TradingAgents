"""Strongly typed, immutable Data Transfer Objects for Phase 11 Risk Engine."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tradingagents.dataflows.dto.features import BaseFeatureDTO
from tradingagents.dataflows.dto.validation import validate_non_negative_decimal
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.risk.enums import (
    DrawdownRisk,
    InvalidationRisk,
    PositionSuitability,
    RiskLevel,
    VolatilityRegime,
)

PRECISION_TWO = Decimal("0.01")
HUNDRED = Decimal("100.00")
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class RiskSubMetricsDTO:
    """Granular quantitative sub-scores for each risk domain (0.00 to 100.00)."""

    volatility_score: Decimal = Decimal("0.00")
    conflict_score: Decimal = Decimal("0.00")
    dealing_range_score: Decimal = Decimal("0.00")
    invalidation_score: Decimal = Decimal("0.00")
    regime_quality_score: Decimal = Decimal("100.00")
    liquidity_reversal_score: Decimal = Decimal("0.00")
    chop_score: Decimal = Decimal("0.00")

    def __post_init__(self) -> None:
        for name, val in self.__dict__.items():
            if not isinstance(val, Decimal):
                raise DTOValidationError(f"{name} must be a Decimal, got {type(val)}")
            if not (ZERO <= val <= HUNDRED):
                raise DTOValidationError(f"{name} must be in [0.00, 100.00], got {val}")


@dataclass(frozen=True)
class RiskAssessmentDTO(BaseFeatureDTO):
    """Institutional risk assessment for a symbol and timeframe as of a point-in-time.
    
    Subclasses BaseFeatureDTO so it integrates seamlessly with FeatureStore for persistence,
    caching, and point-in-time querying.
    """

    feature_name: str = "risk_assessment"
    risk_level: RiskLevel = RiskLevel.LOW
    volatility_regime: VolatilityRegime = VolatilityRegime.NORMAL
    regime_tradeable: bool = True
    invalidation_risk: InvalidationRisk = InvalidationRisk.LOW
    signal_conflict_ratio: Decimal = Decimal("0.00")
    drawdown_risk: DrawdownRisk = DrawdownRisk.LOW
    regime_quality: Decimal = Decimal("100.00")
    position_suitability: PositionSuitability = PositionSuitability.FAVORABLE
    risk_score: Decimal = Decimal("0.00")
    sub_metrics: RiskSubMetricsDTO = RiskSubMetricsDTO()
    risk_factors: tuple[str, ...] = ()
    explanatory_reasoning: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.risk_level, RiskLevel):
            raise DTOValidationError(f"risk_level must be RiskLevel, got {type(self.risk_level)}")
        if not isinstance(self.volatility_regime, VolatilityRegime):
            raise DTOValidationError(f"volatility_regime must be VolatilityRegime, got {type(self.volatility_regime)}")
        if not isinstance(self.invalidation_risk, InvalidationRisk):
            raise DTOValidationError(f"invalidation_risk must be InvalidationRisk, got {type(self.invalidation_risk)}")
        if not isinstance(self.drawdown_risk, DrawdownRisk):
            raise DTOValidationError(f"drawdown_risk must be DrawdownRisk, got {type(self.drawdown_risk)}")
        if not isinstance(self.position_suitability, PositionSuitability):
            raise DTOValidationError(f"position_suitability must be PositionSuitability, got {type(self.position_suitability)}")
        if not isinstance(self.sub_metrics, RiskSubMetricsDTO):
            raise DTOValidationError(f"sub_metrics must be RiskSubMetricsDTO, got {type(self.sub_metrics)}")

        if not (ZERO <= self.signal_conflict_ratio <= Decimal("1.00")):
            raise DTOValidationError(
                f"signal_conflict_ratio must be in [0.00, 1.00], got {self.signal_conflict_ratio}"
            )
        if not (ZERO <= self.regime_quality <= HUNDRED):
            raise DTOValidationError(f"regime_quality must be in [0.00, 100.00], got {self.regime_quality}")
        if not (ZERO <= self.risk_score <= HUNDRED):
            raise DTOValidationError(f"risk_score must be in [0.00, 100.00], got {self.risk_score}")
