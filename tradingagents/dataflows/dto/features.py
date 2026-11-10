"""Strongly typed, immutable feature data transfer objects for indicators and Smart Money Concepts.

Enforces financial invariants, Decimal precision, and timezone-aware UTC timestamps.
Zero dictionary-based feature blobs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from tradingagents.dataflows.dto.validation import (
    validate_non_negative_decimal,
    validate_positive_decimal,
    validate_utc_datetime,
)
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError


@dataclass(frozen=True)
class BaseFeatureDTO:
    """Base class for all immutable, strongly typed feature observations."""

    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    feature_name: str

    def __post_init__(self) -> None:
        if not self.symbol or not isinstance(self.symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        if not isinstance(self.timeframe, Timeframe):
            raise DTOValidationError(f"timeframe must be an instance of Timeframe, got {type(self.timeframe)}")
        validate_utc_datetime(self.timestamp, "timestamp")
        if not self.feature_name or not isinstance(self.feature_name, str):
            raise DTOValidationError("feature_name must be a non-empty string")


# =====================================================================
# Mathematical & Trend Indicators
# =====================================================================

@dataclass(frozen=True)
class EMADTO(BaseFeatureDTO):
    """Exponential Moving Average observation."""

    period: int = 21
    value: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.period, int) or self.period <= 0:
            raise DTOValidationError(f"period must be a positive integer, got {self.period}")
        validate_positive_decimal(self.value, "value")


@dataclass(frozen=True)
class SMADTO(BaseFeatureDTO):
    """Simple Moving Average observation."""

    period: int = 50
    value: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.period, int) or self.period <= 0:
            raise DTOValidationError(f"period must be a positive integer, got {self.period}")
        validate_positive_decimal(self.value, "value")


@dataclass(frozen=True)
class VWAPDTO(BaseFeatureDTO):
    """Volume-Weighted Average Price observation."""

    vwap: Decimal = Decimal("0")
    volume_sum: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_positive_decimal(self.vwap, "vwap")
        validate_non_negative_decimal(self.volume_sum, "volume_sum")


# =====================================================================
# Momentum & Volatility Indicators
# =====================================================================

@dataclass(frozen=True)
class RSIDTO(BaseFeatureDTO):
    """Relative Strength Index observation (0 to 100)."""

    period: int = 14
    value: Decimal = Decimal("50.0")

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.period, int) or self.period <= 0:
            raise DTOValidationError(f"period must be a positive integer, got {self.period}")
        if not isinstance(self.value, Decimal):
            raise DTOValidationError("RSI value must be a Decimal")
        if not (Decimal("0") <= self.value <= Decimal("100")):
            raise DTOValidationError(f"RSI value must be between 0 and 100, got {self.value}")


@dataclass(frozen=True)
class ATRDTO(BaseFeatureDTO):
    """Average True Range volatility quantification."""

    period: int = 14
    value: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.period, int) or self.period <= 0:
            raise DTOValidationError(f"period must be a positive integer, got {self.period}")
        validate_non_negative_decimal(self.value, "value")


@dataclass(frozen=True)
class MACDDTO(BaseFeatureDTO):
    """Moving Average Convergence Divergence observation."""

    macd_line: Decimal = Decimal("0")
    signal_line: Decimal = Decimal("0")
    histogram: Decimal = Decimal("0")
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.macd_line, Decimal):
            raise DTOValidationError("macd_line must be a Decimal")
        if not isinstance(self.signal_line, Decimal):
            raise DTOValidationError("signal_line must be a Decimal")
        if not isinstance(self.histogram, Decimal):
            raise DTOValidationError("histogram must be a Decimal")
        if self.fast_period >= self.slow_period:
            raise DTOValidationError(f"fast_period ({self.fast_period}) must be < slow_period ({self.slow_period})")


@dataclass(frozen=True)
class BollingerBandsDTO(BaseFeatureDTO):
    """Bollinger Bands volatility and mean-reversion boundaries."""

    middle_band: Decimal = Decimal("0")
    upper_band: Decimal = Decimal("0")
    lower_band: Decimal = Decimal("0")
    bandwidth_bps: Decimal = Decimal("0")
    period: int = 20
    num_std_dev: Decimal = Decimal("2.0")

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_positive_decimal(self.middle_band, "middle_band")
        validate_positive_decimal(self.upper_band, "upper_band")
        validate_positive_decimal(self.lower_band, "lower_band")
        validate_non_negative_decimal(self.bandwidth_bps, "bandwidth_bps")
        if not (self.lower_band <= self.middle_band <= self.upper_band):
            raise DTOValidationError(
                f"Invalid Bollinger Bands: lower ({self.lower_band}) <= middle ({self.middle_band}) <= upper ({self.upper_band})"
            )


@dataclass(frozen=True)
class VolumeProfileDTO(BaseFeatureDTO):
    """Session or rolling Volume Profile distribution."""

    poc: Decimal = Decimal("0")          # Point of Control
    vah: Decimal = Decimal("0")          # Value Area High (70% volume)
    val: Decimal = Decimal("0")          # Value Area Low (70% volume)
    total_volume: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_positive_decimal(self.poc, "poc")
        validate_positive_decimal(self.vah, "vah")
        validate_positive_decimal(self.val, "val")
        validate_non_negative_decimal(self.total_volume, "total_volume")
        if not (self.val <= self.poc <= self.vah):
            raise DTOValidationError(
                f"Volume Profile invariant violated: val ({self.val}) <= poc ({self.poc}) <= vah ({self.vah})"
            )


# =====================================================================
# Derivative Market Metrics
# =====================================================================

@dataclass(frozen=True)
class FundingMetricsDTO(BaseFeatureDTO):
    """Perpetual swap funding rate analytics."""

    current_rate: Decimal = Decimal("0")
    annualized_rate: Decimal = Decimal("0")
    predicted_rate: Decimal | None = None
    mark_price: Decimal | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.current_rate, Decimal):
            raise DTOValidationError("current_rate must be a Decimal")
        if not isinstance(self.annualized_rate, Decimal):
            raise DTOValidationError("annualized_rate must be a Decimal")
        if self.mark_price is not None:
            validate_positive_decimal(self.mark_price, "mark_price")


@dataclass(frozen=True)
class OpenInterestMetricsDTO(BaseFeatureDTO):
    """Aggregate open interest and leverage positioning."""

    open_interest: Decimal = Decimal("0")
    change_24h_pct: Decimal | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_non_negative_decimal(self.open_interest, "open_interest")
        if self.change_24h_pct is not None and not isinstance(self.change_24h_pct, Decimal):
            raise DTOValidationError("change_24h_pct must be a Decimal or None")


# =====================================================================
# Smart Money Concepts (SMC) & Institutional Price Action
# =====================================================================

@dataclass(frozen=True)
class FairValueGapDTO(BaseFeatureDTO):
    """3-candle institutional price imbalance zone."""

    is_bullish: bool = True
    upper_bound: Decimal = Decimal("0")
    lower_bound: Decimal = Decimal("0")
    mitigated: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_positive_decimal(self.upper_bound, "upper_bound")
        validate_positive_decimal(self.lower_bound, "lower_bound")
        if self.lower_bound > self.upper_bound:
            raise DTOValidationError(
                f"FVG lower_bound ({self.lower_bound}) cannot exceed upper_bound ({self.upper_bound})"
            )


@dataclass(frozen=True)
class BreakOfStructureDTO(BaseFeatureDTO):
    """Break of Structure (BOS) confirming trend continuation."""

    is_bullish: bool = True
    broken_level: Decimal = Decimal("0")
    displacement_volume: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_positive_decimal(self.broken_level, "broken_level")
        validate_non_negative_decimal(self.displacement_volume, "displacement_volume")


@dataclass(frozen=True)
class ChangeOfCharacterDTO(BaseFeatureDTO):
    """Change of Character (CHoCH) structural reversal trigger."""

    is_bullish: bool = True
    pivot_level: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_positive_decimal(self.pivot_level, "pivot_level")


@dataclass(frozen=True)
class OrderBlockDTO(BaseFeatureDTO):
    """Institutional Order Block footprint before displacement."""

    is_bullish: bool = True
    top_price: Decimal = Decimal("0")
    bottom_price: Decimal = Decimal("0")
    volume_surge_ratio: Decimal = Decimal("1.0")
    mitigated: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_positive_decimal(self.top_price, "top_price")
        validate_positive_decimal(self.bottom_price, "bottom_price")
        validate_positive_decimal(self.volume_surge_ratio, "volume_surge_ratio")
        if self.bottom_price > self.top_price:
            raise DTOValidationError(
                f"OrderBlock bottom_price ({self.bottom_price}) cannot exceed top_price ({self.top_price})"
            )


@dataclass(frozen=True)
class LiquiditySweepDTO(BaseFeatureDTO):
    """Liquidity pool sweep and aggressive price rejection."""

    is_buy_side: bool = True
    swept_level: Decimal = Decimal("0")
    rejection_price: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_positive_decimal(self.swept_level, "swept_level")
        validate_positive_decimal(self.rejection_price, "rejection_price")


@dataclass(frozen=True)
class SwingPointDTO(BaseFeatureDTO):
    """Structural swing high or swing low pivot."""

    is_high: bool = True
    price: Decimal = Decimal("0")
    is_major: bool = False  # True = External/Major structure, False = Internal/Minor structure

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_positive_decimal(self.price, "price")


@dataclass(frozen=True)
class LiquidityPoolDTO(BaseFeatureDTO):
    """Resting liquidity zone (Equal Highs or Equal Lows - EQH / EQL)."""

    is_high: bool = True  # True = EQH (buy-side), False = EQL (sell-side)
    level: Decimal = Decimal("0")
    touch_count: int = 2
    tolerance_bps: Decimal = Decimal("10.0")
    swept: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_positive_decimal(self.level, "level")
        validate_non_negative_decimal(self.tolerance_bps, "tolerance_bps")
        if self.touch_count < 2:
            raise DTOValidationError(f"touch_count must be at least 2, got {self.touch_count}")


@dataclass(frozen=True)
class PremiumDiscountDTO(BaseFeatureDTO):
    """Institutional Premium vs Discount valuation relative to dealing range."""

    range_high: Decimal = Decimal("0")
    range_low: Decimal = Decimal("0")
    equilibrium: Decimal = Decimal("0")
    current_price: Decimal = Decimal("0")
    zone: str = "EQUILIBRIUM"  # "PREMIUM", "DISCOUNT", "EQUILIBRIUM"
    percentile: Decimal = Decimal("50.0")

    def __post_init__(self) -> None:
        super().__post_init__()
        validate_positive_decimal(self.range_high, "range_high")
        validate_positive_decimal(self.range_low, "range_low")
        validate_positive_decimal(self.equilibrium, "equilibrium")
        validate_positive_decimal(self.current_price, "current_price")
        if self.range_low > self.range_high:
            raise DTOValidationError(
                f"range_low ({self.range_low}) cannot exceed range_high ({self.range_high})"
            )
        if not (self.range_low <= self.equilibrium <= self.range_high):
            raise DTOValidationError(
                f"equilibrium ({self.equilibrium}) must lie within [{self.range_low}, {self.range_high}]"
            )
        if self.zone not in {"PREMIUM", "DISCOUNT", "EQUILIBRIUM"}:
            raise DTOValidationError(f"Invalid zone '{self.zone}', must be PREMIUM, DISCOUNT, or EQUILIBRIUM")


# =====================================================================
# Directional Probability & Explainable Scoring
# =====================================================================

@dataclass(frozen=True)
class FeatureContributionDTO:
    """Individual feature contribution to overall market directional probability."""

    feature_name: str
    weight: Decimal
    score: Decimal
    direction: str  # "BULLISH", "BEARISH", "NEUTRAL"
    description: str

    def __post_init__(self) -> None:
        if not self.feature_name or not isinstance(self.feature_name, str):
            raise DTOValidationError("feature_name must be a non-empty string")
        if not isinstance(self.weight, Decimal):
            raise DTOValidationError(f"weight must be a Decimal, got {type(self.weight)}")
        if not isinstance(self.score, Decimal):
            raise DTOValidationError(f"score must be a Decimal, got {type(self.score)}")
        if self.direction not in {"BULLISH", "BEARISH", "NEUTRAL"}:
            raise DTOValidationError(f"Invalid direction '{self.direction}', must be BULLISH, BEARISH, or NEUTRAL")
        if not isinstance(self.description, str):
            raise DTOValidationError("description must be a string")


@dataclass(frozen=True)
class ProbabilityDTO(BaseFeatureDTO):
    """Deterministic directional probability distribution and confidence score."""

    bullish_probability: Decimal = Decimal("0.00")
    bearish_probability: Decimal = Decimal("0.00")
    neutral_probability: Decimal = Decimal("100.00")
    confidence: Decimal = Decimal("0.00")
    total_score: Decimal = Decimal("0.00")
    bullish_score: Decimal = Decimal("0.00")
    bearish_score: Decimal = Decimal("0.00")
    contributing_features: tuple[FeatureContributionDTO, ...] = field(default_factory=tuple)
    positive_factors: tuple[str, ...] = field(default_factory=tuple)
    negative_factors: tuple[str, ...] = field(default_factory=tuple)
    reasoning: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        for prob_name, val in [
            ("bullish_probability", self.bullish_probability),
            ("bearish_probability", self.bearish_probability),
            ("neutral_probability", self.neutral_probability),
            ("confidence", self.confidence),
        ]:
            if not isinstance(val, Decimal):
                raise DTOValidationError(f"{prob_name} must be a Decimal, got {type(val)}")
            if not (Decimal("0.00") <= val <= Decimal("100.00")):
                raise DTOValidationError(f"{prob_name} must be within [0.00, 100.00], got {val}")

        # Enforce strict financial probability invariant: Bullish + Bearish + Neutral == 100.00%
        prob_sum = self.bullish_probability + self.bearish_probability + self.neutral_probability
        if abs(prob_sum - Decimal("100.00")) > Decimal("0.01"):
            raise DTOValidationError(
                f"Probabilities must sum to 100.00%, got {prob_sum} "
                f"(bullish={self.bullish_probability}, bearish={self.bearish_probability}, neutral={self.neutral_probability})"
            )

        if not isinstance(self.total_score, Decimal):
            raise DTOValidationError(f"total_score must be a Decimal, got {type(self.total_score)}")
        if not isinstance(self.bullish_score, Decimal):
            raise DTOValidationError(f"bullish_score must be a Decimal, got {type(self.bullish_score)}")
        if not isinstance(self.bearish_score, Decimal):
            raise DTOValidationError(f"bearish_score must be a Decimal, got {type(self.bearish_score)}")
        if not isinstance(self.contributing_features, tuple):
            raise DTOValidationError("contributing_features must be a tuple")
        if not isinstance(self.positive_factors, tuple):
            raise DTOValidationError("positive_factors must be a tuple")
        if not isinstance(self.negative_factors, tuple):
            raise DTOValidationError("negative_factors must be a tuple")
        if not isinstance(self.reasoning, str):
            raise DTOValidationError("reasoning must be a string")


