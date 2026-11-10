"""Deterministic Probability Agent synthesizing Phase 9 / 9.1 mathematical probability distributions."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping

from tradingagents.dataflows.dto.features import BaseFeatureDTO, ProbabilityDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.features.probability.engine import ProbabilityEngine
from tradingagents.orchestration.agents.base import BaseMarketAgent
from tradingagents.orchestration.dto import (
    ProbabilityAssessmentDTO,
    ProbabilityBreakdownDTO,
)
from tradingagents.orchestration.enums import AgentRole, DirectionalBias


class ProbabilityAgent(BaseMarketAgent):
    """Specialized agent synthesizing mathematical directional probabilities and factor contributions."""

    def __init__(self, probability_engine: ProbabilityEngine | None = None) -> None:
        self._engine = probability_engine or ProbabilityEngine()

    @property
    def role(self) -> AgentRole:
        return AgentRole.PROBABILITY

    def analyze(
        self,
        symbol: str,
        timeframe: Timeframe,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
        as_of: datetime | None = None,
    ) -> ProbabilityAssessmentDTO:
        self._validate_inputs(symbol, timeframe, as_of)

        # Check if pre-computed ProbabilityDTO exists in features
        prob_dto = self._find_feature(features, ProbabilityDTO, "probability", "PROBABILITY")

        # Otherwise compute deterministically via ProbabilityEngine
        if not prob_dto:
            effective_ts = as_of if as_of is not None else datetime.now(timezone.utc)
            prob_dto = self._engine.compute_from_features(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=effective_ts,
                features=features,
                current_price=current_price,
            )

        # Determine directional bias based on probability dominance
        if prob_dto.bullish_probability > prob_dto.bearish_probability and prob_dto.bullish_probability > prob_dto.neutral_probability:
            bias = DirectionalBias.BULLISH
        elif prob_dto.bearish_probability > prob_dto.bullish_probability and prob_dto.bearish_probability > prob_dto.neutral_probability:
            bias = DirectionalBias.BEARISH
        else:
            bias = DirectionalBias.NEUTRAL

        breakdown = ProbabilityBreakdownDTO(
            bullish=prob_dto.bullish_probability,
            bearish=prob_dto.bearish_probability,
            neutral=prob_dto.neutral_probability,
        )

        reasoning = (
            f"Probability Distribution: Bullish {prob_dto.bullish_probability}%, "
            f"Bearish {prob_dto.bearish_probability}%, Neutral {prob_dto.neutral_probability}%. "
            f"Confidence: {prob_dto.confidence}%, Total Score: {prob_dto.total_score:+0.2f}."
        )

        return ProbabilityAssessmentDTO(
            directional_bias=bias,
            breakdown=breakdown,
            total_score=prob_dto.total_score,
            confidence=prob_dto.confidence,
            top_positive_factors=prob_dto.positive_factors[:4],
            top_negative_factors=prob_dto.negative_factors[:4],
            reasoning=reasoning,
        )
