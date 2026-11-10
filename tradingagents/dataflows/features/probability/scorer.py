"""Deterministic feature scoring engine for market structure and technical indicators."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import math
from typing import Any, Mapping

from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.dto.features import (
    ATRDTO,
    BaseFeatureDTO,
    BollingerBandsDTO,
    BreakOfStructureDTO,
    ChangeOfCharacterDTO,
    EMADTO,
    FairValueGapDTO,
    FeatureContributionDTO,
    LiquiditySweepDTO,
    MACDDTO,
    OrderBlockDTO,
    PremiumDiscountDTO,
    RSIDTO,
    SMADTO,
    VolumeProfileDTO,
    VWAPDTO,
)
from tradingagents.dataflows.features.probability.config import ScoringConfig

TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}


class ProbabilityScorer:
    """Pure deterministic scoring module evaluating market features against institutional weights."""

    def __init__(self, config: ScoringConfig | None = None) -> None:
        self._config = config or ScoringConfig()

    @property
    def config(self) -> ScoringConfig:
        return self._config

    def _calculate_event_decay(
        self,
        event_timestamp: datetime,
        as_of: datetime | None,
        timeframe: Timeframe | None,
    ) -> tuple[Decimal, int]:
        """Calculate exponential half-life decay multiplier based on elapsed bars.

        Returns:
            tuple of (decay_multiplier: Decimal, elapsed_bars: int)
        """
        if as_of is None or timeframe is None:
            return Decimal("1.0"), 0

        tf_str = timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe).lower()
        tf_secs = TIMEFRAME_SECONDS.get(tf_str, 3600)

        elapsed_secs = max(0.0, (as_of - event_timestamp).total_seconds())
        elapsed_bars = int(elapsed_secs // tf_secs)

        if elapsed_bars <= 0:
            return Decimal("1.0"), 0

        if elapsed_bars >= self._config.event_max_decay_bars:
            return Decimal("0.0"), elapsed_bars

        half_life = float(self._config.event_half_life_bars)
        decay_val = math.pow(0.5, float(elapsed_bars) / half_life)
        decay_dec = Decimal(str(round(decay_val, 4)))
        return decay_dec, elapsed_bars

    @staticmethod
    def _find_feature(
        features: Mapping[str, BaseFeatureDTO],
        dto_type: type,
        *names: str,
    ) -> Any | None:
        """Find feature observation by name alias (case-insensitive) or by DTO type."""
        lower_map = {k.lower(): v for k, v in features.items()}
        for name in names:
            if name.lower() in lower_map:
                val = lower_map[name.lower()]
                if isinstance(val, dto_type):
                    return val
        for v in features.values():
            if isinstance(v, dto_type):
                return v
        return None

    def score(
        self,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
        as_of: datetime | None = None,
        timeframe: Timeframe | None = None,
    ) -> tuple[Decimal, Decimal, tuple[FeatureContributionDTO, ...], tuple[str, ...], tuple[str, ...]]:
        """Score input features deterministically with event decay and empirical weights.

        Returns:
            Tuple of:
            - bullish_score (Decimal >= 0)
            - bearish_score (Decimal >= 0)
            - contributions (tuple of FeatureContributionDTO)
            - positive_factors (tuple of formatted strings)
            - negative_factors (tuple of formatted strings)
        """
        contributions: list[FeatureContributionDTO] = []
        pos_factors: list[str] = []
        neg_factors: list[str] = []

        cfg = self._config
        lower_map = {k.lower(): v for k, v in features.items()}

        # 1. Break of Structure (BOS) - Event decayed
        bos = self._find_feature(features, BreakOfStructureDTO, "bos", "BOS")
        if isinstance(bos, BreakOfStructureDTO):
            decay, bars_old = self._calculate_event_decay(bos.timestamp, as_of, timeframe)
            weight = (cfg.weight_bos * decay).quantize(Decimal("0.01"))
            if weight > Decimal("0.0"):
                age_str = f" ({bars_old} bars ago, decayed to {decay*100:.0f}%)" if bars_old > 0 else ""
                if bos.is_bullish:
                    score = weight
                    direction = "BULLISH"
                    desc = f"Bullish BOS: Higher high structure break at {bos.broken_level}{age_str}"
                    pos_factors.append(f"✓ Bullish BOS detected at {bos.broken_level}{age_str}")
                else:
                    score = -weight
                    direction = "BEARISH"
                    desc = f"Bearish BOS: Lower low structure break at {bos.broken_level}{age_str}"
                    neg_factors.append(f"✗ Bearish BOS detected at {bos.broken_level}{age_str}")
                contributions.append(
                    FeatureContributionDTO(
                        feature_name="bos",
                        weight=weight,
                        score=score,
                        direction=direction,
                        description=desc,
                    )
                )
            else:
                contributions.append(
                    FeatureContributionDTO(
                        feature_name="bos",
                        weight=Decimal("0.0"),
                        score=Decimal("0.0"),
                        direction="NEUTRAL",
                        description=f"Decayed/expired BOS at {bos.broken_level} ({bars_old} bars ago, weight=0)",
                    )
                )

        # 2. Change of Character (CHoCH) - Event decayed
        choch = self._find_feature(features, ChangeOfCharacterDTO, "choch", "CHOCH")
        if isinstance(choch, ChangeOfCharacterDTO):
            decay, bars_old = self._calculate_event_decay(choch.timestamp, as_of, timeframe)
            weight = (cfg.weight_choch * decay).quantize(Decimal("0.01"))
            if weight > Decimal("0.0"):
                age_str = f" ({bars_old} bars ago, decayed to {decay*100:.0f}%)" if bars_old > 0 else ""
                if choch.is_bullish:
                    score = weight
                    direction = "BULLISH"
                    desc = f"Bullish CHoCH: Structural character reversal above {choch.pivot_level}{age_str}"
                    pos_factors.append(f"✓ Bullish CHoCH detected above {choch.pivot_level}{age_str}")
                else:
                    score = -weight
                    direction = "BEARISH"
                    desc = f"Bearish CHoCH: Structural character reversal below {choch.pivot_level}{age_str}"
                    neg_factors.append(f"✗ Bearish CHoCH detected below {choch.pivot_level}{age_str}")
                contributions.append(
                    FeatureContributionDTO(
                        feature_name="choch",
                        weight=weight,
                        score=score,
                        direction=direction,
                        description=desc,
                    )
                )
            else:
                contributions.append(
                    FeatureContributionDTO(
                        feature_name="choch",
                        weight=Decimal("0.0"),
                        score=Decimal("0.0"),
                        direction="NEUTRAL",
                        description=f"Decayed/expired CHoCH at {choch.pivot_level} ({bars_old} bars ago, weight=0)",
                    )
                )

        # 3. Order Block (OB)
        ob = self._find_feature(features, OrderBlockDTO, "order_block", "ORDER_BLOCK")
        if isinstance(ob, OrderBlockDTO):
            weight = cfg.weight_order_block
            if not ob.mitigated:
                if ob.is_bullish:
                    score = weight
                    direction = "BULLISH"
                    desc = f"Active Bullish Order Block [{ob.bottom_price} - {ob.top_price}]"
                    pos_factors.append(f"✓ Bullish Order Block active [{ob.bottom_price} - {ob.top_price}]")
                else:
                    score = -weight
                    direction = "BEARISH"
                    desc = f"Active Bearish Order Block [{ob.bottom_price} - {ob.top_price}]"
                    neg_factors.append(f"✗ Bearish Order Block active [{ob.bottom_price} - {ob.top_price}]")
            else:
                score = Decimal("0.0")
                direction = "NEUTRAL"
                desc = f"Mitigated Order Block [{ob.bottom_price} - {ob.top_price}] (neutralized)"

            contributions.append(
                FeatureContributionDTO(
                    feature_name="order_block",
                    weight=weight,
                    score=score,
                    direction=direction,
                    description=desc,
                )
            )

        # 4. Liquidity Sweep - Event decayed
        sweep = self._find_feature(features, LiquiditySweepDTO, "liquidity_sweep", "LIQUIDITY_SWEEP")
        if isinstance(sweep, LiquiditySweepDTO):
            decay, bars_old = self._calculate_event_decay(sweep.timestamp, as_of, timeframe)
            weight = (cfg.weight_liquidity_sweep * decay).quantize(Decimal("0.01"))
            if weight > Decimal("0.0"):
                age_str = f" ({bars_old} bars ago, decayed to {decay*100:.0f}%)" if bars_old > 0 else ""
                # is_buy_side=False means sell-side liquidity swept below lows -> Bullish reversal
                # is_buy_side=True means buy-side liquidity swept above highs -> Bearish reversal
                if not sweep.is_buy_side:
                    score = weight
                    direction = "BULLISH"
                    desc = f"Bullish Liquidity Sweep: Sell-side liquidity purged below {sweep.swept_level}{age_str}"
                    pos_factors.append(f"✓ Bullish Liquidity Sweep (sell-side purged below {sweep.swept_level}){age_str}")
                else:
                    score = -weight
                    direction = "BEARISH"
                    desc = f"Bearish Liquidity Sweep: Buy-side liquidity purged above {sweep.swept_level}{age_str}"
                    neg_factors.append(f"✗ Bearish Liquidity Sweep (buy-side purged above {sweep.swept_level}){age_str}")
                contributions.append(
                    FeatureContributionDTO(
                        feature_name="liquidity_sweep",
                        weight=weight,
                        score=score,
                        direction=direction,
                        description=desc,
                    )
                )
            else:
                contributions.append(
                    FeatureContributionDTO(
                        feature_name="liquidity_sweep",
                        weight=Decimal("0.0"),
                        score=Decimal("0.0"),
                        direction="NEUTRAL",
                        description=f"Decayed/expired Liquidity Sweep at {sweep.swept_level} ({bars_old} bars ago, weight=0)",
                    )
                )

        # 5. Premium / Discount Zone
        pd = self._find_feature(features, PremiumDiscountDTO, "premium_discount", "PREMIUM_DISCOUNT", "PREMIUM_DISCOUNT_20")
        if isinstance(pd, PremiumDiscountDTO):
            weight = cfg.weight_premium_discount
            if pd.zone == "DISCOUNT":
                score = weight
                direction = "BULLISH"
                desc = f"Discount Zone ({pd.percentile:.1f}%) - Institutional buying territory"
                pos_factors.append(f"✓ Discount Zone ({pd.percentile:.1f}%)")
            elif pd.zone == "PREMIUM":
                score = -weight
                direction = "BEARISH"
                desc = f"Premium Zone ({pd.percentile:.1f}%) - Institutional selling territory"
                neg_factors.append(f"✗ Premium Zone ({pd.percentile:.1f}%)")
            else:
                score = Decimal("0.0")
                direction = "NEUTRAL"
                desc = f"Equilibrium Zone ({pd.percentile:.1f}%) - Fair value"
            contributions.append(
                FeatureContributionDTO(
                    feature_name="premium_discount",
                    weight=weight,
                    score=score,
                    direction=direction,
                    description=desc,
                )
            )

        # 6. Fair Value Gap (FVG)
        fvg = self._find_feature(features, FairValueGapDTO, "fvg", "FVG")
        if isinstance(fvg, FairValueGapDTO):
            weight = cfg.weight_fvg
            if not fvg.mitigated:
                if fvg.is_bullish:
                    score = weight
                    direction = "BULLISH"
                    desc = f"Unmitigated Bullish FVG [{fvg.lower_bound} - {fvg.upper_bound}]"
                    pos_factors.append(f"✓ Bullish FVG active [{fvg.lower_bound} - {fvg.upper_bound}]")
                else:
                    score = -weight
                    direction = "BEARISH"
                    desc = f"Unmitigated Bearish FVG [{fvg.lower_bound} - {fvg.upper_bound}]"
                    neg_factors.append(f"✗ Bearish FVG active [{fvg.lower_bound} - {fvg.upper_bound}]")
            else:
                score = Decimal("0.0")
                direction = "NEUTRAL"
                desc = f"Mitigated FVG [{fvg.lower_bound} - {fvg.upper_bound}] (neutralized)"
            contributions.append(
                FeatureContributionDTO(
                    feature_name="fvg",
                    weight=weight,
                    score=score,
                    direction=direction,
                    description=desc,
                )
            )

        # 7. EMA Alignment
        ema9 = None
        ema21 = None
        if "ema_9" in lower_map and isinstance(lower_map["ema_9"], EMADTO):
            ema9 = lower_map["ema_9"]
        if "ema_21" in lower_map and isinstance(lower_map["ema_21"], EMADTO):
            ema21 = lower_map["ema_21"]
        if ema9 is None or ema21 is None:
            for v in features.values():
                if isinstance(v, EMADTO):
                    if v.period == 9 or "9" in v.feature_name:
                        ema9 = ema9 or v
                    elif v.period == 21 or "21" in v.feature_name:
                        ema21 = ema21 or v

        if isinstance(ema9, EMADTO) and isinstance(ema21, EMADTO):
            weight = cfg.weight_ema_alignment
            if ema9.value > ema21.value:
                score = weight
                direction = "BULLISH"
                desc = f"Bullish EMA Alignment: Fast EMA 9 ({ema9.value}) > Slow EMA 21 ({ema21.value})"
                pos_factors.append(f"✓ Bullish EMA Alignment (EMA 9 > EMA 21)")
            elif ema9.value < ema21.value:
                score = -weight
                direction = "BEARISH"
                desc = f"Bearish EMA Alignment: Fast EMA 9 ({ema9.value}) < Slow EMA 21 ({ema21.value})"
                neg_factors.append(f"✗ Bearish EMA Alignment (EMA 9 < EMA 21)")
            else:
                score = Decimal("0.0")
                direction = "NEUTRAL"
                desc = "EMA 9 and EMA 21 are converged"
            contributions.append(
                FeatureContributionDTO(
                    feature_name="ema_alignment",
                    weight=weight,
                    score=score,
                    direction=direction,
                    description=desc,
                )
            )

        # 8. SMA Alignment (Golden / Death Trend)
        sma20 = None
        sma50 = None
        if "sma_20" in lower_map and isinstance(lower_map["sma_20"], SMADTO):
            sma20 = lower_map["sma_20"]
        if "sma_50" in lower_map and isinstance(lower_map["sma_50"], SMADTO):
            sma50 = lower_map["sma_50"]
        if sma20 is None or sma50 is None:
            for v in features.values():
                if isinstance(v, SMADTO):
                    if v.period == 20 or "20" in v.feature_name:
                        sma20 = sma20 or v
                    elif v.period == 50 or "50" in v.feature_name:
                        sma50 = sma50 or v

        if isinstance(sma20, SMADTO) and isinstance(sma50, SMADTO):
            weight = cfg.weight_sma_alignment
            if sma20.value > sma50.value:
                score = weight
                direction = "BULLISH"
                desc = f"Bullish SMA Trend: SMA 20 ({sma20.value}) > SMA 50 ({sma50.value})"
                pos_factors.append(f"✓ Bullish SMA Trend (SMA 20 > SMA 50)")
            elif sma20.value < sma50.value:
                score = -weight
                direction = "BEARISH"
                desc = f"Bearish SMA Trend: SMA 20 ({sma20.value}) < SMA 50 ({sma50.value})"
                neg_factors.append(f"✗ Bearish SMA Trend (SMA 20 < SMA 50)")
            else:
                score = Decimal("0.0")
                direction = "NEUTRAL"
                desc = "SMA 20 and SMA 50 converged"
            contributions.append(
                FeatureContributionDTO(
                    feature_name="sma_alignment",
                    weight=weight,
                    score=score,
                    direction=direction,
                    description=desc,
                )
            )

        # 9. RSI Momentum & Overextended Recovery
        rsi = self._find_feature(features, RSIDTO, "rsi", "RSI", "rsi_14", "RSI_14")
        if isinstance(rsi, RSIDTO):
            weight = cfg.weight_rsi
            if rsi.value <= cfg.rsi_oversold:
                score = weight
                direction = "BULLISH"
                desc = f"RSI Oversold ({rsi.value}) - Potential mean-reversion recovery"
                pos_factors.append(f"✓ RSI Oversold Recovery ({rsi.value})")
            elif rsi.value >= cfg.rsi_overbought:
                score = -weight
                direction = "BEARISH"
                desc = f"RSI Overbought ({rsi.value}) - Potential exhaustion pullback"
                neg_factors.append(f"✗ RSI Overbought Rejection ({rsi.value})")
            else:
                score = Decimal("0.0")
                direction = "NEUTRAL"
                desc = f"RSI Neutral Momentum ({rsi.value})"
            contributions.append(
                FeatureContributionDTO(
                    feature_name="rsi",
                    weight=weight,
                    score=score,
                    direction=direction,
                    description=desc,
                )
            )

        # 10. MACD Convergence/Divergence
        macd = self._find_feature(features, MACDDTO, "macd", "MACD", "MACD_12_26_9")
        if isinstance(macd, MACDDTO):
            weight = cfg.weight_macd
            if macd.macd_line > macd.signal_line and macd.histogram > Decimal("0"):
                score = weight
                direction = "BULLISH"
                desc = f"Bullish MACD Cross: Line ({macd.macd_line}) > Signal ({macd.signal_line}), Hist (+{macd.histogram})"
                pos_factors.append(f"✓ MACD Bullish Cross (+{macd.histogram})")
            elif macd.macd_line < macd.signal_line and macd.histogram < Decimal("0"):
                score = -weight
                direction = "BEARISH"
                desc = f"Bearish MACD Cross: Line ({macd.macd_line}) < Signal ({macd.signal_line}), Hist ({macd.histogram})"
                neg_factors.append(f"✗ MACD Bearish Cross ({macd.histogram})")
            else:
                score = Decimal("0.0")
                direction = "NEUTRAL"
                desc = f"MACD Neutral / Transitioning (Hist: {macd.histogram})"
            contributions.append(
                FeatureContributionDTO(
                    feature_name="macd",
                    weight=weight,
                    score=score,
                    direction=direction,
                    description=desc,
                )
            )

        # 11. VWAP Price Location
        vwap = self._find_feature(features, VWAPDTO, "vwap", "VWAP")
        ref_price = current_price
        if ref_price is None and isinstance(pd, PremiumDiscountDTO):
            ref_price = pd.current_price

        if isinstance(vwap, VWAPDTO) and ref_price is not None:
            weight = cfg.weight_vwap
            if ref_price > vwap.vwap:
                score = weight
                direction = "BULLISH"
                desc = f"Price ({ref_price}) trading above Institutional VWAP ({vwap.vwap})"
                pos_factors.append(f"✓ Price above VWAP ({vwap.vwap})")
            elif ref_price < vwap.vwap:
                score = -weight
                direction = "BEARISH"
                desc = f"Price ({ref_price}) trading below Institutional VWAP ({vwap.vwap})"
                neg_factors.append(f"✗ Price below VWAP ({vwap.vwap})")
            else:
                score = Decimal("0.0")
                direction = "NEUTRAL"
                desc = f"Price at VWAP ({vwap.vwap})"
            contributions.append(
                FeatureContributionDTO(
                    feature_name="vwap",
                    weight=weight,
                    score=score,
                    direction=direction,
                    description=desc,
                )
            )

        # 12. Bollinger Bands Mean Reversion & Squeeze
        boll = self._find_feature(features, BollingerBandsDTO, "bollinger", "BOLLINGER", "BB_20_2.0")
        if isinstance(boll, BollingerBandsDTO) and ref_price is not None:
            weight = cfg.weight_bollinger
            if ref_price <= boll.lower_band:
                score = weight
                direction = "BULLISH"
                desc = f"Price ({ref_price}) testing Bollinger Lower Band ({boll.lower_band}) - Oversold stretch"
                pos_factors.append(f"✓ Bollinger Lower Band Bounce ({boll.lower_band})")
            elif ref_price >= boll.upper_band:
                score = -weight
                direction = "BEARISH"
                desc = f"Price ({ref_price}) testing Bollinger Upper Band ({boll.upper_band}) - Overbought stretch"
                neg_factors.append(f"✗ Bollinger Upper Band Rejection ({boll.upper_band})")
            else:
                score = Decimal("0.0")
                direction = "NEUTRAL"
                desc = f"Price inside Bollinger Bands [{boll.lower_band} - {boll.upper_band}]"
            contributions.append(
                FeatureContributionDTO(
                    feature_name="bollinger",
                    weight=weight,
                    score=score,
                    direction=direction,
                    description=desc,
                )
            )

        # 13. Volume Profile Point of Control (POC)
        vp = self._find_feature(features, VolumeProfileDTO, "volume_profile", "VOLUME_PROFILE", "VP_24_70")
        if isinstance(vp, VolumeProfileDTO) and ref_price is not None:
            weight = cfg.weight_volume_profile
            if ref_price > vp.poc:
                score = weight
                direction = "BULLISH"
                desc = f"Price ({ref_price}) holding above Volume Profile POC ({vp.poc})"
                pos_factors.append(f"✓ Price above Volume POC ({vp.poc})")
            elif ref_price < vp.poc:
                score = -weight
                direction = "BEARISH"
                desc = f"Price ({ref_price}) below Volume Profile POC ({vp.poc})"
                neg_factors.append(f"✗ Price below Volume POC ({vp.poc})")
            else:
                score = Decimal("0.0")
                direction = "NEUTRAL"
                desc = f"Price at Volume POC ({vp.poc})"
            contributions.append(
                FeatureContributionDTO(
                    feature_name="volume_profile",
                    weight=weight,
                    score=score,
                    direction=direction,
                    description=desc,
                )
            )

        # 14. ATR Volatility Expansion
        atr = self._find_feature(features, ATRDTO, "atr", "ATR", "atr_14", "ATR_14")
        if isinstance(atr, ATRDTO):
            weight = cfg.weight_atr_expansion
            # ATR is a volatility confirmation; if positive volatility exists, record as active factor
            if atr.value > Decimal("0.0"):
                contributions.append(
                    FeatureContributionDTO(
                        feature_name="atr_expansion",
                        weight=weight,
                        score=Decimal("0.0"),  # Directionally neutral, feeds confidence
                        direction="NEUTRAL",
                        description=f"Market Volatility Quantified: ATR ({atr.value})",
                    )
                )

        # Aggregate bullish and bearish scores
        bullish_score = Decimal("0.0")
        bearish_score = Decimal("0.0")
        for c in contributions:
            if c.score > Decimal("0.0"):
                bullish_score += c.score
            elif c.score < Decimal("0.0"):
                bearish_score += abs(c.score)

        return (
            bullish_score,
            bearish_score,
            tuple(contributions),
            tuple(pos_factors),
            tuple(neg_factors),
        )
