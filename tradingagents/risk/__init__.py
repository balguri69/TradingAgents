"""Phase 11: Institutional Risk Engine subsystem.

Deterministic, modular risk analysis synthesizing:
- Volatility state (ATR, Bollinger squeeze/expansion)
- Dealing range overextension & invalidation boundaries
- Cross-discipline signal conflict
- Regime tradeability & quality
"""

from __future__ import annotations

from tradingagents.risk.config import RiskConfig
from tradingagents.risk.dto import RiskAssessmentDTO, RiskSubMetricsDTO
from tradingagents.risk.engine import DEFAULT_MONITORED_FEATURES, RiskComputer, RiskEngine
from tradingagents.risk.enums import (
    DrawdownRisk,
    InvalidationRisk,
    PositionSuitability,
    RiskLevel,
    VolatilityRegime,
)
from tradingagents.risk.evaluators import (
    ConflictRiskEvaluator,
    InvalidationRiskEvaluator,
    RegimeQualityEvaluator,
    VolatilityRiskEvaluator,
)

__all__ = [
    # Enums
    "RiskLevel",
    "VolatilityRegime",
    "InvalidationRisk",
    "DrawdownRisk",
    "PositionSuitability",
    # Config
    "RiskConfig",
    # DTOs
    "RiskSubMetricsDTO",
    "RiskAssessmentDTO",
    # Evaluators
    "VolatilityRiskEvaluator",
    "ConflictRiskEvaluator",
    "InvalidationRiskEvaluator",
    "RegimeQualityEvaluator",
    # Engine & Computer
    "RiskEngine",
    "RiskComputer",
    "DEFAULT_MONITORED_FEATURES",
]
