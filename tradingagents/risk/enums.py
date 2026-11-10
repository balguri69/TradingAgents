"""Enumerations for Phase 11 Risk Engine subsystem."""

from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    """Institutional composite risk classification."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class VolatilityRegime(str, Enum):
    """Market volatility environment classification."""

    COMPRESSED = "COMPRESSED"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    EXPLOSIVE = "EXPLOSIVE"


class InvalidationRisk(str, Enum):
    """Proximity and likelihood of structural thesis invalidation."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    ELEVATED = "ELEVATED"
    CRITICAL = "CRITICAL"


class DrawdownRisk(str, Enum):
    """Adverse excursion and drawdown vulnerability."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


class PositionSuitability(str, Enum):
    """Guidance on capital deployment suitability without execution."""

    FAVORABLE = "FAVORABLE"
    SELECTIVE_REDUCED = "SELECTIVE_REDUCED"
    DEFENSIVE_MINIMAL = "DEFENSIVE_MINIMAL"
    UNSUITABLE_CASH_ONLY = "UNSUITABLE_CASH_ONLY"
