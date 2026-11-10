"""Deterministic quantitative volatility risk evaluator."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping

from tradingagents.dataflows.dto.features import (
    ATRDTO,
    BaseFeatureDTO,
    BollingerBandsDTO,
)
from tradingagents.risk.config import RiskConfig
from tradingagents.risk.enums import VolatilityRegime

PRECISION_TWO = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")


class VolatilityRiskEvaluator:
    """Evaluates ATR, Bollinger bandwidth, and regime volatility dynamics."""

    def __init__(self, config: RiskConfig) -> None:
        self._config = config

    def evaluate(
        self,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
    ) -> tuple[VolatilityRegime, Decimal, list[str]]:
        """Evaluate volatility conditions and return (regime, volatility_score [0-100], risk_factors)."""
        cfg = self._config
        risk_factors: list[str] = []
        volatility_score = Decimal("20.00")  # Baseline normal volatility
        regime = VolatilityRegime.NORMAL

        boll = None
        for k in ("bollinger", "BOLLINGER", "BB_20_2.0"):
            if isinstance(features.get(k), BollingerBandsDTO):
                boll = features[k]
                break

        atr = None
        for k in ("atr_14", "ATR_14", "atr", "ATR"):
            if isinstance(features.get(k), ATRDTO):
                atr = features[k]
                break

        # 1. Bollinger Bandwidth Analysis
        if boll and boll.middle_band > ZERO:
            bandwidth = boll.upper_band - boll.lower_band
            bw_pct = bandwidth / boll.middle_band

            if bw_pct < cfg.bollinger_squeeze_pct:
                regime = VolatilityRegime.COMPRESSED
                volatility_score = Decimal("50.00")
                risk_factors.append(
                    f"Volatility Compression: Bollinger bandwidth is compressed ({bw_pct*100:.1f}% < {cfg.bollinger_squeeze_pct*100:.1f}%)"
                )
            elif bw_pct > cfg.bollinger_explosive_pct:
                regime = VolatilityRegime.EXPLOSIVE
                volatility_score = Decimal("95.00")
                risk_factors.append(
                    f"Explosive Volatility: Bollinger bandwidth extreme ({bw_pct*100:.1f}% > {cfg.bollinger_explosive_pct*100:.1f}%)"
                )
            elif bw_pct > cfg.bollinger_expansion_pct:
                regime = VolatilityRegime.ELEVATED
                volatility_score = Decimal("65.00")
                risk_factors.append(
                    f"Elevated Volatility: Bollinger bandwidth expanding ({bw_pct*100:.1f}%)"
                )

        # 2. ATR Price Ratio Analysis
        if atr and current_price and current_price > ZERO:
            atr_ratio = atr.value / current_price
            if atr_ratio >= cfg.atr_extreme_ratio:
                volatility_score = max(volatility_score, Decimal("85.00"))
                regime = VolatilityRegime.EXPLOSIVE if regime != VolatilityRegime.EXPLOSIVE else regime
                risk_factors.append(
                    f"Extreme ATR Risk: 14-period ATR ({atr.value}) is {atr_ratio*100:.1f}% of current price"
                )
            elif atr_ratio >= Decimal("0.03"):
                volatility_score = max(volatility_score, Decimal("55.00"))
                risk_factors.append(
                    f"Elevated ATR Volatility: ATR represents {atr_ratio*100:.1f}% of price"
                )

        score = min(HUNDRED, max(ZERO, volatility_score)).quantize(PRECISION_TWO, rounding=ROUND_HALF_UP)
        return regime, score, risk_factors
