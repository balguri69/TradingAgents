"""Enumerations for multi-agent institutional market orchestration."""

from __future__ import annotations

from enum import Enum


class DirectionalBias(str, Enum):
    """Institutional directional bias."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class RiskLevel(str, Enum):
    """Execution and regime risk classification."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class MarketPhase(str, Enum):
    """Institutional Smart Money market cycle phase."""

    ACCUMULATION = "ACCUMULATION"
    EXPANSION = "EXPANSION"
    DISTRIBUTION = "DISTRIBUTION"
    RETRACEMENT = "RETRACEMENT"
    CONSOLIDATION = "CONSOLIDATION"


class ConvictionTier(str, Enum):
    """Statistical and structural conviction tier."""

    VERY_HIGH = "VERY_HIGH"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    VERY_LOW = "VERY_LOW"


class AgentRole(str, Enum):
    """Specialized analytical agent responsibilities."""

    TECHNICAL_ANALYSIS = "TECHNICAL_ANALYSIS"
    MARKET_STRUCTURE = "MARKET_STRUCTURE"
    PROBABILITY = "PROBABILITY"
    RISK_CONTEXT = "RISK_CONTEXT"
    CONFIDENCE_EVIDENCE = "CONFIDENCE_EVIDENCE"
    FINAL_SYNTHESIS = "FINAL_SYNTHESIS"
