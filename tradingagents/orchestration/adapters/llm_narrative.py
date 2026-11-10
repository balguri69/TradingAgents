"""Isolated presentation adapter formatting MarketAssessmentDTO into institutional narratives."""

from __future__ import annotations

from typing import Any, Callable

from tradingagents.orchestration.dto import MarketAssessmentDTO


class LLMNarrativeAdapter:
    """Optional presentation adapter converting deterministic MarketAssessmentDTO into desk notes.
    
    This adapter is strictly decoupled from the core decision engine:
    - Never called in the core quantitative path.
    - Zero impact on directional bias, probabilities, or confidence scores.
    """

    def __init__(self, llm_callable: Callable[[str], str] | None = None) -> None:
        self._llm_callable = llm_callable

    def format_morning_briefing(self, assessment: MarketAssessmentDTO) -> str:
        """Format assessment into an institutional morning note."""
        lines = [
            f"# Institutional Desk Briefing: {assessment.symbol} [{assessment.timeframe.value}]",
            f"**Timestamp**: {assessment.timestamp.isoformat()}",
            f"**Directional Thesis**: {assessment.directional_bias.value} (Conviction: {assessment.confidence_assessment.conviction_tier.value} / {assessment.confidence}%)",
            f"**Regime Risk**: {assessment.risk_assessment.risk_level.value} (Conflict Ratio: {assessment.risk_assessment.signal_conflict_ratio:.2f})",
            f"**Tradeable Status**: {'Actionable' if assessment.is_actionable else 'Caution / Neutral Watch'}",
            "",
            "## 1. Probability Distribution",
            f"- **Bullish**: {assessment.probability_breakdown.bullish}%",
            f"- **Bearish**: {assessment.probability_breakdown.bearish}%",
            f"- **Neutral**: {assessment.probability_breakdown.neutral}%",
            "",
            "## 2. Evidence Synthesis",
        ]
        for ev in assessment.evidence_summary:
            lines.append(f"- {ev}")

        lines.extend([
            "",
            "## 3. Supporting Footprints",
        ])
        for supp in assessment.supporting_features:
            lines.append(f"- ✓ {supp}")

        lines.extend([
            "",
            "## 4. Counter-Trend & Invalidation Risks",
        ])
        for conf in assessment.conflicting_features:
            lines.append(f"- ⚠ {conf}")

        lines.extend([
            "",
            "## 5. Discipline Details",
            f"- **Structure**: {assessment.structure_assessment.reasoning}",
            f"- **Technicals**: {assessment.technical_assessment.reasoning}",
            f"- **Risk & Invalidation**: {assessment.risk_assessment.reasoning}",
            f"- **Confidence**: {assessment.confidence_assessment.reasoning}",
        ])

        raw_briefing = "\n".join(lines)

        # If an optional LLM callable was provided, invoke it purely for stylistic prose polishing
        if self._llm_callable is not None:
            try:
                return self._llm_callable(raw_briefing)
            except Exception:
                return raw_briefing

        return raw_briefing
