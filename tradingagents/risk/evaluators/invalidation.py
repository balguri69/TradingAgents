"""Deterministic quantitative structural invalidation and dealing range risk evaluator."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

from tradingagents.dataflows.dto.features import (
    BaseFeatureDTO,
    BreakOfStructureDTO,
    ChangeOfCharacterDTO,
    OrderBlockDTO,
    PremiumDiscountDTO,
    SwingPointDTO,
)
from tradingagents.risk.config import RiskConfig
from tradingagents.risk.enums import InvalidationRisk

PRECISION_TWO = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")


class InvalidationRiskEvaluator:
    """Evaluates proximity to structural invalidation boundaries and dealing range stretch."""

    def __init__(self, config: RiskConfig) -> None:
        self._config = config

    def evaluate(
        self,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
        directional_intent: str | None = None,
    ) -> tuple[InvalidationRisk, Decimal, Decimal, list[str]]:
        """Evaluate invalidation proximity.
        
        Returns:
            tuple of (invalidation_risk, invalidation_score [0-100], dealing_range_score [0-100], risk_factors)
        """
        cfg = self._config
        risk_factors: list[str] = []
        invalidation_score = Decimal("20.00")
        dealing_range_score = Decimal("20.00")
        risk_level = InvalidationRisk.LOW

        pd = features.get("premium_discount") or features.get("PREMIUM_DISCOUNT") or features.get("PREMIUM_DISCOUNT_20")

        # 1. Dealing Range Location & Overextension Analysis
        if isinstance(pd, PremiumDiscountDTO):
            pct = pd.percentile
            zone = pd.zone

            # If directional intent is specified (BULLISH/BEARISH)
            if directional_intent == "BULLISH":
                if pct >= cfg.premium_exhaustion_percentile:
                    dealing_range_score = Decimal("85.00")
                    invalidation_score = max(invalidation_score, Decimal("80.00"))
                    risk_level = InvalidationRisk.CRITICAL
                    risk_factors.append(
                        f"Overextended Dealing Range: Bullish posture inside deep PREMIUM ({pct:.1f}% >= {cfg.premium_exhaustion_percentile}%)"
                    )
                elif zone == "PREMIUM":
                    dealing_range_score = Decimal("60.00")
                    invalidation_score = max(invalidation_score, Decimal("50.00"))
                    risk_level = InvalidationRisk.ELEVATED
                    risk_factors.append(f"Suboptimal Entry: Buying inside PREMIUM dealing range ({pct:.1f}%)")
                elif zone == "DISCOUNT":
                    dealing_range_score = Decimal("10.00")

            elif directional_intent == "BEARISH":
                if pct <= cfg.discount_exhaustion_percentile:
                    dealing_range_score = Decimal("85.00")
                    invalidation_score = max(invalidation_score, Decimal("80.00"))
                    risk_level = InvalidationRisk.CRITICAL
                    risk_factors.append(
                        f"Overextended Dealing Range: Bearish posture inside deep DISCOUNT ({pct:.1f}% <= {cfg.discount_exhaustion_percentile}%)"
                    )
                elif zone == "DISCOUNT":
                    dealing_range_score = Decimal("60.00")
                    invalidation_score = max(invalidation_score, Decimal("50.00"))
                    risk_level = InvalidationRisk.ELEVATED
                    risk_factors.append(f"Suboptimal Entry: Selling inside DISCOUNT dealing range ({pct:.1f}%)")
                elif zone == "PREMIUM":
                    dealing_range_score = Decimal("10.00")

            else:
                # Neutral or unspecified: extreme zones represent mean-reversion exhaustion risk
                if pct >= cfg.premium_exhaustion_percentile:
                    dealing_range_score = Decimal("75.00")
                    risk_factors.append(f"Range Exhaustion: Price at premium dealing range boundary ({pct:.1f}%)")
                elif pct <= cfg.discount_exhaustion_percentile:
                    dealing_range_score = Decimal("75.00")
                    risk_factors.append(f"Range Exhaustion: Price at discount dealing range boundary ({pct:.1f}%)")

        # 2. Structural Invalidation Proximity
        # Look for opposing OrderBlock boundary or CHoCH pivot
        ref_price = current_price
        if ref_price is None and isinstance(pd, PremiumDiscountDTO):
            ref_price = pd.current_price

        if ref_price is not None and ref_price > ZERO:
            # Check proximity to nearest opposing OB
            ob = features.get("order_block") or features.get("ORDER_BLOCK")
            if isinstance(ob, OrderBlockDTO) and not ob.mitigated:
                boundary = ob.top_price if ob.is_bullish else ob.bottom_price
                dist_pct = abs(ref_price - boundary) / ref_price
                if dist_pct < Decimal("0.005"):  # Within 0.5% of invalidation level
                    invalidation_score = max(invalidation_score, Decimal("90.00"))
                    risk_level = InvalidationRisk.CRITICAL
                    risk_factors.append(
                        f"Critical Invalidation Proximity: Price ({ref_price}) is within {dist_pct*100:.2f}% of Order Block boundary ({boundary})"
                    )
                elif dist_pct < Decimal("0.015"):  # Within 1.5%
                    invalidation_score = max(invalidation_score, Decimal("60.00"))
                    if risk_level not in {InvalidationRisk.CRITICAL}:
                        risk_level = InvalidationRisk.ELEVATED
                    risk_factors.append(
                        f"Elevated Invalidation Proximity: Price is within {dist_pct*100:.2f}% of Order Block level ({boundary})"
                    )

        inv_score = min(HUNDRED, max(ZERO, invalidation_score)).quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)
        dr_score = min(HUNDRED, max(ZERO, dealing_range_score)).quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)
        return risk_level, inv_score, dr_score, risk_factors
