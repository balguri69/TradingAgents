"""Deterministic confidence calculation module based on feature concordance and evidence completeness."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from tradingagents.dataflows.dto.features import FeatureContributionDTO
from tradingagents.dataflows.features.probability.config import ScoringConfig

PRECISION_TWO = Decimal("0.01")
HUNDRED = Decimal("100.00")
ZERO = Decimal("0.00")
ONE = Decimal("1.00")


class ConfidenceCalculator:
    """Calculates overall directional confidence score (0.00% to 100.00%)."""

    def __init__(self, config: ScoringConfig | None = None) -> None:
        self._config = config or ScoringConfig()

    @property
    def config(self) -> ScoringConfig:
        return self._config

    def calculate(
        self,
        contributions: Sequence[FeatureContributionDTO],
        bullish_score: Decimal,
        bearish_score: Decimal,
    ) -> Decimal:
        """Calculate overall confidence score based on purity, evidence, structure, and trend.

        Returns:
            Confidence score as a Decimal in [0.00, 100.00].
        """
        # Zero evidence -> Zero confidence
        total_score = bullish_score + bearish_score
        if total_score == ZERO:
            return ZERO

        cfg = self._config

        # 1. Directional Purity (absence of conflicting signals)
        purity = abs(bullish_score - bearish_score) / total_score

        # 2. Evidence Breadth (coverage of observed features against target benchmark)
        active_features = [c for c in contributions if c.direction in {"BULLISH", "BEARISH"}]
        n_active = len(active_features)
        target_count = cfg.target_evidence_count
        evidence_coverage = min(ONE, Decimal(str(n_active)) / Decimal(str(target_count)))

        # Evidence dampening for purity: a single isolated feature cannot claim 100% directional certainty
        purity_scale = min(ONE, Decimal(str(n_active)) / Decimal("2.0"))
        effective_purity = purity * purity_scale

        # Determine dominant direction
        dominant = "BULLISH" if bullish_score >= bearish_score else "BEARISH"

        # 3. Structural Concordance (institutional Smart Money confirmation)
        structure_names = {"bos", "choch", "order_block", "liquidity_sweep", "premium_discount", "fvg"}
        struct_concordant = sum(
            1 for c in active_features if c.feature_name in structure_names and c.direction == dominant
        )
        if struct_concordant >= 3:
            struct_factor = ONE
        elif struct_concordant == 2:
            struct_factor = Decimal("0.75")
        elif struct_concordant == 1:
            struct_factor = Decimal("0.40")
        else:
            struct_factor = ZERO

        # 4. Orthogonal Indicator Cluster Concordance (removes collinear indicator inflation)
        trend_cluster = {"ema_alignment", "sma_alignment", "macd"}
        volume_cluster = {"vwap", "volume_profile"}
        oscillator_cluster = {"rsi", "bollinger"}

        has_trend = any(
            c.direction == dominant for c in active_features if c.feature_name in trend_cluster
        )
        has_volume = any(
            c.direction == dominant for c in active_features if c.feature_name in volume_cluster
        )
        has_oscillator = any(
            c.direction == dominant for c in active_features if c.feature_name in oscillator_cluster
        )
        cluster_concordant = sum([has_trend, has_volume, has_oscillator])

        if cluster_concordant >= 3:
            trend_factor = ONE
        elif cluster_concordant == 2:
            trend_factor = Decimal("0.70")
        elif cluster_concordant == 1:
            trend_factor = Decimal("0.40")
        else:
            trend_factor = ZERO

        # Composite weighted confidence
        raw_confidence = (
            (cfg.confidence_weight_purity * effective_purity)
            + (cfg.confidence_weight_evidence * evidence_coverage)
            + (cfg.confidence_weight_structure * struct_factor)
            + (cfg.confidence_weight_trend * trend_factor)
        ) * HUNDRED

        # Clamp within [0.00, 100.00]
        clamped = max(ZERO, min(HUNDRED, raw_confidence))
        return clamped.quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)
