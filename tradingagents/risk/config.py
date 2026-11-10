"""Configurable parameters, boundaries, and weights for the deterministic Risk Engine."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RiskConfig:
    """Configurable quantitative thresholds and risk model parameters."""

    # Volatility Boundaries
    bollinger_squeeze_pct: Decimal = Decimal("0.025")       # Bandwidth < 2.5% = Squeeze
    bollinger_expansion_pct: Decimal = Decimal("0.080")     # Bandwidth > 8.0% = Elevated Volatility
    bollinger_explosive_pct: Decimal = Decimal("0.150")     # Bandwidth > 15.0% = Explosive Volatility
    atr_extreme_ratio: Decimal = Decimal("0.050")           # ATR > 5% of price = High Volatility

    # Dealing Range Overextension Boundaries
    discount_exhaustion_percentile: Decimal = Decimal("15.0")  # < 15% percentile = deep discount
    premium_exhaustion_percentile: Decimal = Decimal("85.0")   # > 85% percentile = deep premium

    # Conflict and Agreement Weights
    conflict_weight_disciplines: Decimal = Decimal("0.40")
    conflict_weight_multi_agent: Decimal = Decimal("0.35")
    conflict_weight_range_divergence: Decimal = Decimal("0.25")

    # Risk Score Component Weights (Total = 1.00)
    weight_volatility_risk: Decimal = Decimal("0.25")
    weight_conflict_risk: Decimal = Decimal("0.25")
    weight_invalidation_risk: Decimal = Decimal("0.20")
    weight_regime_quality: Decimal = Decimal("0.15")
    weight_liquidity_reversal_risk: Decimal = Decimal("0.15")

    # Composite Risk Level Thresholds
    risk_threshold_low: Decimal = Decimal("30.00")
    risk_threshold_moderate: Decimal = Decimal("55.00")
    risk_threshold_high: Decimal = Decimal("75.00")

    # Regime Tradeability Thresholds
    max_tradeable_conflict_ratio: Decimal = Decimal("0.65")
    max_tradeable_risk_score: Decimal = Decimal("80.00")

    # Cache Capacity
    max_cache_size: int = 10000

    def __post_init__(self) -> None:
        """Validate parameter boundaries."""
        for name, val in self.__dict__.items():
            if isinstance(val, Decimal) and val < Decimal("0"):
                raise ValueError(f"Parameter {name} cannot be negative, got {val}")
        if self.max_cache_size <= 0:
            raise ValueError(f"max_cache_size must be positive, got {self.max_cache_size}")
