"""Deterministic quantitative regime quality, chop detection, and liquidity reversal evaluator."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping

from tradingagents.dataflows.dto.features import (
    BaseFeatureDTO,
    BollingerBandsDTO,
    EMADTO,
    LiquidityPoolDTO,
    LiquiditySweepDTO,
    PremiumDiscountDTO,
    RSIDTO,
    SMADTO,
)
from tradingagents.risk.config import RiskConfig

PRECISION_TWO = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")


class RegimeQualityEvaluator:
    """Evaluates trend cleanliness, range/chop persistence, and liquidity reversal traps."""

    def __init__(self, config: RiskConfig) -> None:
        self._config = config

    def evaluate(
        self,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
    ) -> tuple[Decimal, Decimal, Decimal, list[str]]:
        """Evaluate regime quality, chop, and liquidity traps.
        
        Returns:
            tuple of (regime_quality [0-100], chop_score [0-100], liquidity_reversal_score [0-100], risk_factors)
        """
        risk_factors: list[str] = []
        cleanliness_points = Decimal("50.0")  # Baseline neutral
        chop_points = Decimal("10.0")
        liquidity_reversal_points = Decimal("10.0")

        # 1. Trend Cleanliness & Alignment Analysis
        ema9 = features.get("ema_9") or features.get("EMA_9")
        ema21 = features.get("ema_21") or features.get("EMA_21")
        sma20 = features.get("sma_20") or features.get("SMA_20")
        sma50 = features.get("sma_50") or features.get("SMA_50")

        if isinstance(ema9, EMADTO) and isinstance(ema21, EMADTO) and isinstance(sma20, SMADTO) and isinstance(sma50, SMADTO):
            # Perfect stack (EMA 9 > 21 > SMA 20 > 50 or vice versa)
            bull_stack = (ema9.value > ema21.value) and (ema21.value >= sma20.value) and (sma20.value > sma50.value)
            bear_stack = (ema9.value < ema21.value) and (ema21.value <= sma20.value) and (sma20.value < sma50.value)

            if bull_stack or bear_stack:
                cleanliness_points += Decimal("40.0")
                chop_points = Decimal("5.0")
            else:
                cleanliness_points -= Decimal("20.0")
                chop_points += Decimal("35.0")
                risk_factors.append("Disorganized Trend: Moving averages intertwined with no dominant alignment")

        # 2. Chop & Equilibrium Compression
        pd = features.get("premium_discount") or features.get("PREMIUM_DISCOUNT") or features.get("PREMIUM_DISCOUNT_20")
        if isinstance(pd, PremiumDiscountDTO):
            if pd.zone == "EQUILIBRIUM" and (Decimal("40.0") <= pd.percentile <= Decimal("60.0")):
                chop_points += Decimal("30.0")
                cleanliness_points -= Decimal("15.0")
                risk_factors.append(
                    f"Consolidation Chop: Price oscillating at dealing range equilibrium ({pd.percentile:.1f}%)"
                )

        # 3. Resting Liquidity Traps (EQH / EQL)
        pool = features.get("liquidity_pool") or features.get("LIQUIDITY_POOL")
        if isinstance(pool, LiquidityPoolDTO) and not pool.swept:
            liquidity_reversal_points += Decimal("35.0")
            trap_type = "Equal Highs (Buy-side magnet)" if pool.is_high else "Equal Lows (Sell-side magnet)"
            risk_factors.append(f"Resting Liquidity Trap: Unswept {trap_type} at {pool.level}")

        # 4. Exhaustion & Reversal Traps
        rsi = features.get("rsi_14") or features.get("RSI_14") or features.get("rsi") or features.get("RSI")
        boll = features.get("bollinger") or features.get("BOLLINGER") or features.get("BB_20_2.0")
        sweep = features.get("liquidity_sweep") or features.get("LIQUIDITY_SWEEP")

        if isinstance(rsi, RSIDTO):
            if rsi.value >= Decimal("75.0"):
                liquidity_reversal_points += Decimal("40.0")
                risk_factors.append(f"Severe Reversal Exhaustion: RSI extreme overbought ({rsi.value})")
            elif rsi.value <= Decimal("25.0"):
                liquidity_reversal_points += Decimal("40.0")
                risk_factors.append(f"Severe Reversal Exhaustion: RSI extreme oversold ({rsi.value})")

        if isinstance(sweep, LiquiditySweepDTO):
            liquidity_reversal_points += Decimal("25.0")
            sweep_dir = "Bearish Rejection" if sweep.is_buy_side else "Bullish Rejection"
            risk_factors.append(f"Liquidity Sweep Invalidation: Recent {sweep_dir} at {sweep.swept_level}")

        q_score = min(HUNDRED, max(ZERO, cleanliness_points)).quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)
        c_score = min(HUNDRED, max(ZERO, chop_points)).quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)
        lr_score = min(HUNDRED, max(ZERO, liquidity_reversal_points)).quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)

        return q_score, c_score, lr_score, risk_factors
