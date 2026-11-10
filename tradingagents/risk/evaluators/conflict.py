"""Deterministic quantitative signal conflict and cross-discipline divergence evaluator."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

from tradingagents.dataflows.dto.features import (
    BaseFeatureDTO,
    BreakOfStructureDTO,
    ChangeOfCharacterDTO,
    EMADTO,
    MACDDTO,
    OrderBlockDTO,
    ProbabilityDTO,
    RSIDTO,
    SMADTO,
)
from tradingagents.risk.config import RiskConfig

PRECISION_TWO = Decimal("0.01")
ZERO = Decimal("0.00")
ONE = Decimal("1.00")
HUNDRED = Decimal("100.00")


class ConflictRiskEvaluator:
    """Evaluates cross-discipline conflict, indicator divergence, and analytical opposition."""

    def __init__(self, config: RiskConfig) -> None:
        self._config = config

    def evaluate(
        self,
        features: Mapping[str, BaseFeatureDTO],
        upstream_assessment: Any | None = None,
    ) -> tuple[Decimal, Decimal, list[str]]:
        """Evaluate signal conflict and return (conflict_ratio [0-1], conflict_score [0-100], risk_factors)."""
        risk_factors: list[str] = []
        conflict_points = Decimal("0.0")
        total_eval_points = Decimal("0.0")

        # 1. Inspect upstream assessment if provided (from MultiAgentOrchestrator)
        if upstream_assessment is not None:
            total_eval_points += Decimal("50.0")
            tech_bias = getattr(getattr(upstream_assessment, "technical_assessment", None), "bias", None)
            struct_bias = getattr(getattr(upstream_assessment, "structure_assessment", None), "bias", None)

            if tech_bias and struct_bias:
                t_val = getattr(tech_bias, "value", str(tech_bias))
                s_val = getattr(struct_bias, "value", str(struct_bias))
                if (t_val == "BULLISH" and s_val == "BEARISH") or (t_val == "BEARISH" and s_val == "BULLISH"):
                    conflict_points += Decimal("50.0")
                    risk_factors.append(
                        f"Direct Cross-Discipline Contradiction: Technical Analysis is {t_val} vs Market Structure {s_val}"
                    )
                elif (t_val != "NEUTRAL" and s_val == "NEUTRAL") or (t_val == "NEUTRAL" and s_val != "NEUTRAL"):
                    conflict_points += Decimal("15.0")
                    risk_factors.append(
                        f"Discipline Divergence: One discipline active ({t_val or s_val}) while other is neutral"
                    )

        # 2. Moving Average Conflict (EMA 9/21 vs SMA 20/50)
        ema9 = features.get("ema_9") or features.get("EMA_9")
        ema21 = features.get("ema_21") or features.get("EMA_21")
        sma20 = features.get("sma_20") or features.get("SMA_20")
        sma50 = features.get("sma_50") or features.get("SMA_50")

        if isinstance(ema9, EMADTO) and isinstance(ema21, EMADTO) and isinstance(sma20, SMADTO) and isinstance(sma50, SMADTO):
            total_eval_points += Decimal("25.0")
            ema_bull = ema9.value > ema21.value
            sma_bull = sma20.value > sma50.value
            if ema_bull != sma_bull:
                conflict_points += Decimal("25.0")
                risk_factors.append(
                    f"Timeframe Trend Contradiction: Short-term EMA ({'Bullish' if ema_bull else 'Bearish'}) contradicts Medium-term SMA ({'Bullish' if sma_bull else 'Bearish'})"
                )

        # 3. Market Structure Conflict (BOS vs CHoCH / OB)
        bos = features.get("bos") or features.get("BOS")
        choch = features.get("choch") or features.get("CHOCH")
        ob = features.get("order_block") or features.get("ORDER_BLOCK")

        if isinstance(bos, BreakOfStructureDTO) and isinstance(choch, ChangeOfCharacterDTO):
            total_eval_points += Decimal("25.0")
            if bos.is_bullish != choch.is_bullish:
                conflict_points += Decimal("25.0")
                risk_factors.append(
                    f"Structural Reversal Clash: BOS is {'Bullish' if bos.is_bullish else 'Bearish'} while CHoCH is {'Bullish' if choch.is_bullish else 'Bearish'}"
                )
        elif isinstance(bos, BreakOfStructureDTO) and isinstance(ob, OrderBlockDTO) and not ob.mitigated:
            total_eval_points += Decimal("20.0")
            if bos.is_bullish != ob.is_bullish:
                conflict_points += Decimal("20.0")
                risk_factors.append(
                    f"Structure vs Footprint Conflict: Trend BOS opposes active Order Block footprint"
                )

        # 4. Probability Engine Transfer Conflict
        prob = features.get("probability") or features.get("PROBABILITY")
        if isinstance(prob, ProbabilityDTO):
            total_eval_points += Decimal("20.0")
            if prob.neutral_probability >= Decimal("45.0"):
                conflict_points += Decimal("15.0")
                risk_factors.append(
                    f"Elevated Probability Indecision: Neutral distribution dominates ({prob.neutral_probability}%)"
                )

        # Calculate Conflict Ratio [0.00, 1.00]
        if total_eval_points > ZERO:
            conflict_ratio = min(ONE, conflict_points / total_eval_points).quantize(
                PRECISION_TWO, rounding=ROUND_HALF_UP
            )
        else:
            conflict_ratio = ZERO

        conflict_score = (conflict_ratio * HUNDRED).quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)
        return conflict_ratio, conflict_score, risk_factors
