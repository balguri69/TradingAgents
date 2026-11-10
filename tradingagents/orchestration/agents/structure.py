"""Deterministic Market Structure Agent synthesizing Smart Money Concepts (SMC)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping

from tradingagents.dataflows.dto.features import (
    BaseFeatureDTO,
    BreakOfStructureDTO,
    ChangeOfCharacterDTO,
    FairValueGapDTO,
    LiquidityPoolDTO,
    LiquiditySweepDTO,
    OrderBlockDTO,
    PremiumDiscountDTO,
    SwingPointDTO,
)
from tradingagents.dataflows.enums import Timeframe
from tradingagents.orchestration.agents.base import BaseMarketAgent
from tradingagents.orchestration.dto import MarketStructureAssessmentDTO
from tradingagents.orchestration.enums import AgentRole, DirectionalBias, MarketPhase

PRECISION_TWO = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")


class MarketStructureAgent(BaseMarketAgent):
    """Specialized agent synthesizing institutional SMC footprints, dealing ranges, and market phases."""

    @property
    def role(self) -> AgentRole:
        return AgentRole.MARKET_STRUCTURE

    def analyze(
        self,
        symbol: str,
        timeframe: Timeframe,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
        as_of: datetime | None = None,
    ) -> MarketStructureAssessmentDTO:
        self._validate_inputs(symbol, timeframe, as_of)

        bull_points = Decimal("0.0")
        bear_points = Decimal("0.0")
        sweeps_detected: list[str] = []
        key_levels: list[Decimal] = []
        signals: list[str] = []

        active_ob_count = 0
        unmitigated_fvg_count = 0
        dealing_range_zone = "UNDEFINED"

        # 1. Fair Value Gap (FVG)
        fvg = self._find_feature(features, FairValueGapDTO, "fvg", "FVG")
        if fvg and not fvg.mitigated:
            unmitigated_fvg_count += 1
            if fvg.is_bullish:
                bull_points += Decimal("25.0")
                signals.append(f"Bullish FVG [{fvg.lower_bound} - {fvg.upper_bound}] active")
                key_levels.append(fvg.lower_bound)
            else:
                bear_points += Decimal("25.0")
                signals.append(f"Bearish FVG [{fvg.lower_bound} - {fvg.upper_bound}] active")
                key_levels.append(fvg.upper_bound)

        # 2. Order Block (OB)
        ob = self._find_feature(features, OrderBlockDTO, "order_block", "ORDER_BLOCK")
        if ob and not ob.mitigated:
            active_ob_count += 1
            if ob.is_bullish:
                bull_points += Decimal("25.0")
                signals.append(f"Bullish Order Block [{ob.bottom_price} - {ob.top_price}] active")
                key_levels.append(ob.bottom_price)
            else:
                bear_points += Decimal("25.0")
                signals.append(f"Bearish Order Block [{ob.bottom_price} - {ob.top_price}] active")
                key_levels.append(ob.top_price)

        # 3. Liquidity Sweep
        sweep = self._find_feature(features, LiquiditySweepDTO, "liquidity_sweep", "LIQUIDITY_SWEEP")
        has_bullish_sweep = False
        has_bearish_sweep = False
        if sweep:
            if not sweep.is_buy_side:  # Swept sell-side lows -> Bullish reversal
                bull_points += Decimal("20.0")
                msg = f"Bullish Sweep: Sell-side liquidity purged below {sweep.swept_level}"
                signals.append(msg)
                sweeps_detected.append(msg)
                key_levels.append(sweep.swept_level)
                has_bullish_sweep = True
            else:  # Swept buy-side highs -> Bearish reversal
                bear_points += Decimal("20.0")
                msg = f"Bearish Sweep: Buy-side liquidity purged above {sweep.swept_level}"
                signals.append(msg)
                sweeps_detected.append(msg)
                key_levels.append(sweep.swept_level)
                has_bearish_sweep = True

        # 4. Premium / Discount Dealing Range
        pd = self._find_feature(features, PremiumDiscountDTO, "premium_discount", "PREMIUM_DISCOUNT", "PREMIUM_DISCOUNT_20")
        if pd:
            dealing_range_zone = pd.zone
            key_levels.append(pd.equilibrium)
            if pd.zone == "DISCOUNT":
                bull_points += Decimal("15.0")
                signals.append(f"Dealing range in DISCOUNT zone ({pd.percentile:.1f}%)")
            elif pd.zone == "PREMIUM":
                bear_points += Decimal("15.0")
                signals.append(f"Dealing range in PREMIUM zone ({pd.percentile:.1f}%)")
            else:
                signals.append("Dealing range in EQUILIBRIUM fair value zone")

        # 5. Break of Structure (BOS)
        bos = self._find_feature(features, BreakOfStructureDTO, "bos", "BOS")
        has_bos = False
        if bos:
            has_bos = True
            key_levels.append(bos.broken_level)
            if bos.is_bullish:
                bull_points += Decimal("10.0")
                signals.append(f"Bullish BOS confirmed at {bos.broken_level}")
            else:
                bear_points += Decimal("10.0")
                signals.append(f"Bearish BOS confirmed at {bos.broken_level}")

        # 6. Change of Character (CHoCH)
        choch = self._find_feature(features, ChangeOfCharacterDTO, "choch", "CHOCH")
        has_choch = False
        if choch:
            has_choch = True
            key_levels.append(choch.pivot_level)
            if choch.is_bullish:
                bull_points += Decimal("10.0")
                signals.append(f"Bullish CHoCH reversal above {choch.pivot_level}")
            else:
                bear_points += Decimal("10.0")
                signals.append(f"Bearish CHoCH reversal below {choch.pivot_level}")

        # 7. Structural Phase Classification
        if dealing_range_zone == "DISCOUNT" and (has_bullish_sweep or (ob and ob.is_bullish)):
            market_phase = MarketPhase.ACCUMULATION
        elif dealing_range_zone == "PREMIUM" and (has_bearish_sweep or (ob and not ob.is_bullish)):
            market_phase = MarketPhase.DISTRIBUTION
        elif has_bos:
            market_phase = MarketPhase.EXPANSION
        elif has_choch or dealing_range_zone == "EQUILIBRIUM":
            market_phase = MarketPhase.RETRACEMENT
        else:
            market_phase = MarketPhase.CONSOLIDATION

        # Calculate Net Score (-100.00 to +100.00)
        raw_diff = bull_points - bear_points
        net_score = max(-HUNDRED, min(HUNDRED, raw_diff)).quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)

        # Directional Bias
        if net_score >= Decimal("15.00"):
            bias = DirectionalBias.BULLISH
        elif net_score <= Decimal("-15.00"):
            bias = DirectionalBias.BEARISH
        else:
            bias = DirectionalBias.NEUTRAL

        # Explainable Reasoning Synthesis
        if not signals:
            reasoning = "Market structure neutral: no Smart Money Concept footprints present in store."
        else:
            reasoning = (
                f"Market Structure: {bias.value} bias (Score: {net_score:+0.2f}). "
                f"Phase: {market_phase.value}, Dealing Range: {dealing_range_zone}. "
                f"Active Footprints: {active_ob_count} OBs, {unmitigated_fvg_count} FVGs. "
                f"Key drivers: {'; '.join(signals[:3])}."
            )

        return MarketStructureAssessmentDTO(
            bias=bias,
            score=net_score,
            market_phase=market_phase,
            dealing_range_zone=dealing_range_zone,
            active_order_blocks_count=active_ob_count,
            unmitigated_fvgs_count=unmitigated_fvg_count,
            sweeps_detected=tuple(sweeps_detected),
            key_levels=tuple(sorted(list(set(key_levels)))),
            reasoning=reasoning,
        )
