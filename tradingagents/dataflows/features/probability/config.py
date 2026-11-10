"""Configurable scoring weights and parameters for the deterministic Probability Engine."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ScoringConfig:
    """Institutional scoring weights and parameters for the Probability Engine.
    
    All weights and parameters are strongly typed Decimals and strictly immutable.
    """

    # Market Structure Weights (rebalanced to prioritize institutional footprints)
    weight_fvg: Decimal = Decimal("12.0")           # Empirically 78.6% accurate
    weight_order_block: Decimal = Decimal("12.0")   # Empirically 65.6% accurate
    weight_liquidity_sweep: Decimal = Decimal("7.0")
    weight_premium_discount: Decimal = Decimal("6.0")
    weight_bos: Decimal = Decimal("4.0")            # Demoted from 12.0 (breakouts retest)
    weight_choch: Decimal = Decimal("4.0")          # Demoted from 10.0 (counter-trend churn)

    # Technical Indicator Weights (penalized for collinearity)
    weight_rsi: Decimal = Decimal("5.0")            # Mean-reversion edge
    weight_bollinger: Decimal = Decimal("4.0")      # Mean-reversion edge
    weight_vwap: Decimal = Decimal("4.0")
    weight_ema_alignment: Decimal = Decimal("3.0")  # Reduced from 5.0 (collinearity)
    weight_macd: Decimal = Decimal("3.0")           # Reduced from 5.0 (collinearity)
    weight_sma_alignment: Decimal = Decimal("2.0")  # Reduced from 3.0 (lagging)
    weight_volume_profile: Decimal = Decimal("3.0")
    weight_adx_trend: Decimal = Decimal("4.0")
    weight_atr_expansion: Decimal = Decimal("2.0")

    # Event Feature Decay Parameters (exponential half-life decay)
    event_half_life_bars: int = 5
    event_max_decay_bars: int = 30

    # Cache Capacity
    max_cache_size: int = 10000

    # Normalization & Neutral Distribution Parameters
    neutral_base_weight: Decimal = Decimal("15.0")
    conflict_transfer_ratio: Decimal = Decimal("0.50")

    # Confidence Model Component Weights
    confidence_weight_purity: Decimal = Decimal("0.40")
    confidence_weight_evidence: Decimal = Decimal("0.25")
    confidence_weight_structure: Decimal = Decimal("0.20")
    confidence_weight_trend: Decimal = Decimal("0.15")
    target_evidence_count: int = 6

    # Indicator Boundary Thresholds
    rsi_oversold: Decimal = Decimal("35.0")
    rsi_overbought: Decimal = Decimal("65.0")
    adx_trend_threshold: Decimal = Decimal("25.0")

    def __post_init__(self) -> None:
        """Validate financial and mathematical bounds."""
        for name, val in self.__dict__.items():
            if isinstance(val, Decimal) and val < Decimal("0"):
                raise ValueError(f"Weight/parameter {name} cannot be negative, got {val}")
        if not (Decimal("0") <= self.conflict_transfer_ratio <= Decimal("1.0")):
            raise ValueError(
                f"conflict_transfer_ratio must be in [0.0, 1.0], got {self.conflict_transfer_ratio}"
            )
        if self.target_evidence_count <= 0:
            raise ValueError(f"target_evidence_count must be positive, got {self.target_evidence_count}")
        if self.event_half_life_bars <= 0:
            raise ValueError(f"event_half_life_bars must be positive, got {self.event_half_life_bars}")
        if self.max_cache_size <= 0:
            raise ValueError(f"max_cache_size must be positive, got {self.max_cache_size}")
