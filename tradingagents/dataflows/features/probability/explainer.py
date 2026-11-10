"""Human-readable explanation and reasoning builder for quantitative probabilities."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from tradingagents.dataflows.dto.features import FeatureContributionDTO


class ExplanationBuilder:
    """Constructs institutional-grade markdown and text explanations for probability outputs."""

    def build_reasoning(
        self,
        bullish_prob: Decimal,
        bearish_prob: Decimal,
        neutral_prob: Decimal,
        confidence: Decimal,
        total_score: Decimal,
        bullish_score: Decimal,
        bearish_score: Decimal,
        positive_factors: Sequence[str],
        negative_factors: Sequence[str],
        contributions: Sequence[FeatureContributionDTO],
    ) -> str:
        """Format complete human-readable reasoning narrative."""
        lines: list[str] = []

        # Header summary
        lines.append(
            f"Bullish Probability: {bullish_prob:.1f}% | "
            f"Bearish Probability: {bearish_prob:.1f}% | "
            f"Neutral Probability: {neutral_prob:.1f}%"
        )
        lines.append(f"Confidence: {confidence:.1f}%")
        lines.append(
            f"Net Score: {total_score:+.1f} (Bullish: +{bullish_score:.1f}, Bearish: -{bearish_score:.1f})"
        )
        lines.append("")

        # Positive factors
        if positive_factors:
            lines.append("Positive Factors (Bullish Evidence):")
            for factor in positive_factors:
                lines.append(f"  {factor}")
        else:
            lines.append("Positive Factors: None observed")

        lines.append("")

        # Negative factors
        if negative_factors:
            lines.append("Negative Factors (Bearish Resistance/Risk):")
            for factor in negative_factors:
                lines.append(f"  {factor}")
        else:
            lines.append("Negative Factors: None observed")

        # Contributing feature breakdown
        active_contribs = [c for c in contributions if c.score != Decimal("0.0")]
        if active_contribs:
            lines.append("")
            lines.append("Detailed Feature Breakdown:")
            for c in active_contribs:
                sign = "+" if c.score > Decimal("0") else ""
                lines.append(f"  - [{c.feature_name.upper()}] {c.direction}: {sign}{c.score:.1f} (weight: {c.weight:.1f}) | {c.description}")

        return "\n".join(lines)
