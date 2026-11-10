"""Deterministic Technical Analysis Agent focusing on momentum, trend, and volatility."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping

from tradingagents.dataflows.dto.features import (
    ATRDTO,
    BaseFeatureDTO,
    BollingerBandsDTO,
    EMADTO,
    MACDDTO,
    RSIDTO,
    SMADTO,
    VolumeProfileDTO,
    VWAPDTO,
)
from tradingagents.dataflows.enums import Timeframe
from tradingagents.orchestration.agents.base import BaseMarketAgent
from tradingagents.orchestration.dto import TechnicalAssessmentDTO
from tradingagents.orchestration.enums import AgentRole, DirectionalBias

PRECISION_TWO = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")


class TechnicalAnalysisAgent(BaseMarketAgent):
    """Specialized agent synthesizing quantitative momentum, moving averages, and volatility."""

    @property
    def role(self) -> AgentRole:
        return AgentRole.TECHNICAL_ANALYSIS

    def analyze(
        self,
        symbol: str,
        timeframe: Timeframe,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
        as_of: datetime | None = None,
    ) -> TechnicalAssessmentDTO:
        self._validate_inputs(symbol, timeframe, as_of)

        bull_points = Decimal("0.0")
        bear_points = Decimal("0.0")
        signals: list[str] = []
        indicators_used: list[str] = []

        ref_price = current_price

        # 1. Moving Average Alignment (EMA 9/21)
        ema9 = self._find_feature(features, EMADTO, "ema_9", "EMA_9")
        ema21 = self._find_feature(features, EMADTO, "ema_21", "EMA_21")
        ema_aligned = False
        if ema9 and ema21:
            indicators_used.append("EMA")
            if ema9.value > ema21.value:
                bull_points += Decimal("15.0")
                signals.append(f"EMA 9 ({ema9.value}) > EMA 21 ({ema21.value}) [Bullish Trend]")
                ema_aligned = True
            elif ema9.value < ema21.value:
                bear_points += Decimal("15.0")
                signals.append(f"EMA 9 ({ema9.value}) < EMA 21 ({ema21.value}) [Bearish Trend]")
                ema_aligned = True

        # 2. Macro Moving Average Alignment (SMA 20/50)
        sma20 = self._find_feature(features, SMADTO, "sma_20", "SMA_20")
        sma50 = self._find_feature(features, SMADTO, "sma_50", "SMA_50")
        sma_aligned = False
        if sma20 and sma50:
            indicators_used.append("SMA")
            if sma20.value > sma50.value:
                bull_points += Decimal("10.0")
                signals.append(f"SMA 20 ({sma20.value}) > SMA 50 ({sma50.value}) [Macro Bullish]")
                sma_aligned = True
            elif sma20.value < sma50.value:
                bear_points += Decimal("10.0")
                signals.append(f"SMA 20 ({sma20.value}) < SMA 50 ({sma50.value}) [Macro Bearish]")
                sma_aligned = True

        # 3. MACD Momentum
        macd = self._find_feature(features, MACDDTO, "macd", "MACD", "MACD_12_26_9")
        if macd:
            indicators_used.append("MACD")
            if macd.histogram > ZERO:
                bull_points += Decimal("15.0")
                signals.append(f"MACD Histogram Positive (+{macd.histogram}) [Bullish Momentum]")
            elif macd.histogram < ZERO:
                bear_points += Decimal("15.0")
                signals.append(f"MACD Histogram Negative ({macd.histogram}) [Bearish Momentum]")

        # 4. RSI Momentum & Overbought/Oversold
        rsi = self._find_feature(features, RSIDTO, "rsi_14", "RSI_14", "rsi", "RSI")
        momentum_state = "NEUTRAL_MOMENTUM"
        if rsi:
            indicators_used.append("RSI")
            if rsi.value <= Decimal("35.0"):
                bull_points += Decimal("20.0")
                momentum_state = "OVERSOLD_REVERSAL_SETUP"
                signals.append(f"RSI Oversold ({rsi.value}) [Bullish Rebound Edge]")
            elif rsi.value >= Decimal("65.0"):
                bear_points += Decimal("20.0")
                momentum_state = "OVERBOUGHT_EXHAUSTION_SETUP"
                signals.append(f"RSI Overbought ({rsi.value}) [Bearish Pullback Edge]")
            elif rsi.value > Decimal("50.0"):
                bull_points += Decimal("5.0")
                momentum_state = "BULLISH_EXPANSION"
                signals.append(f"RSI Above Midpoint ({rsi.value})")
            else:
                bear_points += Decimal("5.0")
                momentum_state = "BEARISH_EXPANSION"
                signals.append(f"RSI Below Midpoint ({rsi.value})")

        # 5. VWAP Price Anchor
        vwap = self._find_feature(features, VWAPDTO, "vwap", "VWAP")
        if vwap and ref_price is not None:
            indicators_used.append("VWAP")
            if ref_price > vwap.vwap:
                bull_points += Decimal("15.0")
                signals.append(f"Price ({ref_price}) > VWAP ({vwap.vwap}) [Bullish Acceptance]")
            elif ref_price < vwap.vwap:
                bear_points += Decimal("15.0")
                signals.append(f"Price ({ref_price}) < VWAP ({vwap.vwap}) [Bearish Acceptance]")

        # 6. Bollinger Bands Volatility & Mean Reversion
        boll = self._find_feature(features, BollingerBandsDTO, "bollinger", "BOLLINGER", "BB_20_2.0")
        volatility_regime = "NORMAL_VOLATILITY"
        if boll:
            indicators_used.append("BollingerBands")
            bandwidth = boll.upper_band - boll.lower_band
            if ref_price is not None:
                if ref_price <= boll.lower_band:
                    bull_points += Decimal("15.0")
                    signals.append(f"Price ({ref_price}) testing Bollinger Lower Band ({boll.lower_band})")
                elif ref_price >= boll.upper_band:
                    bear_points += Decimal("15.0")
                    signals.append(f"Price ({ref_price}) testing Bollinger Upper Band ({boll.upper_band})")

        # 7. Volume Profile Anchor
        vp = self._find_feature(features, VolumeProfileDTO, "volume_profile", "VOLUME_PROFILE", "VP_24_70")
        if vp and ref_price is not None:
            indicators_used.append("VolumeProfile")
            if ref_price > vp.vah:
                bull_points += Decimal("10.0")
                signals.append(f"Price ({ref_price}) above Value Area High ({vp.vah})")
            elif ref_price < vp.val:
                bear_points += Decimal("10.0")
                signals.append(f"Price ({ref_price}) below Value Area Low ({vp.val})")

        # 8. ATR Volatility Expansion
        atr = self._find_feature(features, ATRDTO, "atr_14", "ATR_14", "atr", "ATR")
        if atr:
            indicators_used.append("ATR")
            if atr.value > Decimal("0"):
                volatility_regime = "ACTIVE_RANGE"

        # Determine Trend Regime
        if ema_aligned and sma_aligned:
            trend_regime = "STRONG_BULLISH_TREND" if bull_points > bear_points else "STRONG_BEARISH_TREND"
        elif ema_aligned or sma_aligned:
            trend_regime = "MODERATE_TREND"
        else:
            trend_regime = "CONSOLIDATION_RANGE"

        # Calculate Net Score (-100.00 to +100.00)
        total_possible = Decimal("100.0")
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
            reasoning = "Technical analysis neutral: no active technical indicators present in store."
        else:
            reasoning = (
                f"Technical Analysis: {bias.value} bias (Score: {net_score:+0.2f}). "
                f"Regime: {trend_regime}, {volatility_regime}, {momentum_state}. "
                f"Key drivers: {'; '.join(signals[:3])}."
            )

        return TechnicalAssessmentDTO(
            bias=bias,
            score=net_score,
            trend_regime=trend_regime,
            volatility_regime=volatility_regime,
            momentum_state=momentum_state,
            signals=tuple(signals),
            contributing_indicators=tuple(indicators_used),
            reasoning=reasoning,
        )
