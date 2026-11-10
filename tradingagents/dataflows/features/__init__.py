"""Feature computation and storage subsystem."""

from __future__ import annotations

from tradingagents.dataflows.features.indicators import (
    ATRComputer,
    BollingerBandsComputer,
    EMAComputer,
    IndicatorEngine,
    MACDComputer,
    RSIComputer,
    SMAComputer,
    VolumeProfileComputer,
    VWAPComputer,
    validate_ohlcv_series,
)
from tradingagents.dataflows.features.store import InMemoryFeatureStore
from tradingagents.dataflows.features.structure import (
    BreakOfStructureComputer,
    ChangeOfCharacterComputer,
    FairValueGapComputer,
    LiquidityPoolComputer,
    LiquiditySweepComputer,
    MarketStructureEngine,
    OrderBlockComputer,
    PremiumDiscountComputer,
    SwingComputer,
    detect_swings,
)
from tradingagents.dataflows.features.probability import (
    ConfidenceCalculator,
    DEFAULT_FEATURE_NAMES,
    ExplanationBuilder,
    ProbabilityComputer,
    ProbabilityEngine,
    ProbabilityScorer,
    ScoreNormalizer,
    ScoringConfig,
)

__all__ = [
    # Store
    "InMemoryFeatureStore",
    # Indicator Engine & Computers
    "IndicatorEngine",
    "SMAComputer",
    "EMAComputer",
    "RSIComputer",
    "ATRComputer",
    "MACDComputer",
    "BollingerBandsComputer",
    "VWAPComputer",
    "VolumeProfileComputer",
    "validate_ohlcv_series",
    # Market Structure Engine & Computers
    "MarketStructureEngine",
    "SwingComputer",
    "detect_swings",
    "FairValueGapComputer",
    "BreakOfStructureComputer",
    "ChangeOfCharacterComputer",
    "OrderBlockComputer",
    "LiquidityPoolComputer",
    "LiquiditySweepComputer",
    "PremiumDiscountComputer",
    # Probability Engine & Subsystem
    "ProbabilityEngine",
    "ProbabilityComputer",
    "ProbabilityScorer",
    "ScoreNormalizer",
    "ConfidenceCalculator",
    "ExplanationBuilder",
    "ScoringConfig",
    "DEFAULT_FEATURE_NAMES",
]
