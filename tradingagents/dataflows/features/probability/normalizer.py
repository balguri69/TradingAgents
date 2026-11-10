"""Deterministic probability normalization ensuring Bullish + Bearish + Neutral == 100.00%."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from tradingagents.dataflows.features.probability.config import ScoringConfig

PRECISION_TWO = Decimal("0.01")
HUNDRED = Decimal("100.00")
ZERO = Decimal("0.00")


class ScoreNormalizer:
    """Normalizes raw directional scores into a 100.00% probability distribution."""

    def __init__(self, config: ScoringConfig | None = None) -> None:
        self._config = config or ScoringConfig()

    @property
    def config(self) -> ScoringConfig:
        return self._config

    def normalize(
        self,
        bullish_score: Decimal,
        bearish_score: Decimal,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Convert directional scores into normalized probabilities summing to exactly 100.00%.

        Returns:
            Tuple of (bullish_probability, bearish_probability, neutral_probability).
        """
        if bullish_score < ZERO or bearish_score < ZERO:
            raise ValueError(
                f"Scores cannot be negative: bullish={bullish_score}, bearish={bearish_score}"
            )

        # Edge Case: No directional evidence observed (empty store or pure neutral)
        if bullish_score == ZERO and bearish_score == ZERO:
            return ZERO, ZERO, HUNDRED

        cfg = self._config
        k_neutral = cfg.neutral_base_weight
        r_conflict = cfg.conflict_transfer_ratio

        # Quantify conflicting scores between opposing sides
        s_conflict = min(bullish_score, bearish_score)

        # Dampen effective directional scores by the conflict factor
        effective_bull = max(ZERO, bullish_score - (s_conflict * r_conflict))
        effective_bear = max(ZERO, bearish_score - (s_conflict * r_conflict))

        # Conflicted score expands the neutral conviction
        effective_neutral = k_neutral + (Decimal("2.0") * s_conflict * r_conflict)

        total_effective = effective_bull + effective_bear + effective_neutral

        # Compute raw percentage shares
        raw_bull = (effective_bull / total_effective) * HUNDRED
        raw_bear = (effective_bear / total_effective) * HUNDRED

        # Quantize to 2 decimal places using institutional standard ROUND_HALF_UP
        prob_bull = raw_bull.quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)
        prob_bear = raw_bear.quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)

        # Exact reconciliation: Neutral absorbs residual fraction so sum is identically 100.00%
        prob_neutral = HUNDRED - prob_bull - prob_bear

        # Boundary safety clamp
        if prob_neutral < ZERO:
            # In extreme edge case where rounding pushes sum > 100.00
            diff = abs(prob_neutral)
            if prob_bull >= prob_bear:
                prob_bull -= diff
            else:
                prob_bear -= diff
            prob_neutral = ZERO

        return prob_bull, prob_bear, prob_neutral
