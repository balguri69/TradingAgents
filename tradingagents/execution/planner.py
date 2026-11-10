"""Execution Planner: translates market assessments and risk safeguards into OrderIntentDTO."""

from __future__ import annotations

import uuid
from decimal import Decimal

from tradingagents.execution.builder import OrderIntentBuilder
from tradingagents.execution.config import ExecutionConfig
from tradingagents.execution.dto import OrderIntentDTO
from tradingagents.execution.enums import (
    OrderSide,
    OrderType,
    TradeDirection,
)
from tradingagents.orchestration.dto import MarketAssessmentDTO
from tradingagents.orchestration.enums import DirectionalBias
from tradingagents.risk.dto import RiskAssessmentDTO
from tradingagents.risk.enums import RiskLevel

RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.LOW: 1,
    RiskLevel.MODERATE: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.EXTREME: 4,
}

PRECISION_TWO = Decimal("0.01")
PRECISION_FOUR = Decimal("0.0001")
BPS_DIVISOR = Decimal("10000")


class ExecutionPlanner:
    """Evaluates institutional market synthesis and risk metrics to produce deterministic order intents."""

    def __init__(self, config: ExecutionConfig | None = None) -> None:
        self._config = config or ExecutionConfig()

    @property
    def config(self) -> ExecutionConfig:
        return self._config

    def plan(
        self,
        assessment: MarketAssessmentDTO,
        risk: RiskAssessmentDTO,
        current_price: Decimal | None = None,
        quantity: Decimal | None = None,
        order_type: OrderType | None = None,
    ) -> OrderIntentDTO:
        """Evaluate point-in-time assessment and risk to generate an executable or gated OrderIntentDTO.
        
        Strictly zero lookahead bias. Evaluates safeguards in a deterministic sequence.
        """
        symbol = assessment.symbol
        timeframe = assessment.timeframe
        timestamp = assessment.timestamp
        effective_order_type = order_type or self._config.default_order_type
        effective_quantity = quantity if (quantity is not None and quantity > Decimal("0.00")) else self._config.default_order_quantity

        client_order_id = f"co_{symbol}_{timeframe.value}_{uuid.uuid4().hex[:8]}"
        intent_id = f"intent_{uuid.uuid4().hex[:12]}"

        builder = (
            OrderIntentBuilder()
            .with_intent_id(intent_id)
            .with_client_order_id(client_order_id)
            .with_symbol(symbol)
            .with_timeframe(timeframe)
            .with_timestamp(timestamp)
            .with_order_type(effective_order_type)
            .with_quantity(effective_quantity)
            .with_time_in_force(self._config.default_time_in_force)
            .with_confidence(assessment.confidence)
            .with_risk_level(risk.risk_level)
        )

        # 1. Check Regime Tradeability
        if self._config.require_tradeable_regime and not risk.regime_tradeable:
            return (
                builder.gate(
                    f"Regime untradeable: volatility_regime={risk.volatility_regime.value}, risk_level={risk.risk_level.value}"
                ).build()
            )

        # 2. Check Risk Level Gating
        if RISK_RANK[risk.risk_level] > RISK_RANK[self._config.max_allowed_risk_level]:
            return (
                builder.gate(
                    f"Risk level {risk.risk_level.value} exceeds maximum allowed {self._config.max_allowed_risk_level.value}"
                ).build()
            )

        # 3. Check Confidence Threshold
        if assessment.confidence < self._config.min_confidence:
            return (
                builder.gate(
                    f"Assessment confidence {assessment.confidence}% below threshold {self._config.min_confidence}%"
                ).build()
            )

        # 4. Check Directional Bias
        if assessment.directional_bias == DirectionalBias.NEUTRAL:
            return builder.gate("Market assessment directional bias is NEUTRAL").build()

        # 5. Check Directional Edge
        prob = assessment.probability_breakdown
        if assessment.directional_bias == DirectionalBias.BULLISH:
            edge = prob.bullish - prob.bearish
            direction = TradeDirection.LONG
            side = OrderSide.BUY
        else:
            edge = prob.bearish - prob.bullish
            direction = TradeDirection.SHORT
            side = OrderSide.SELL

        if edge < self._config.min_probability_edge:
            return (
                builder.gate(
                    f"Directional probability edge {edge}% below threshold {self._config.min_probability_edge}%"
                ).build()
            )

        # 6. Price Calculation for Limit / Stop Orders
        limit_price: Decimal | None = None
        stop_price: Decimal | None = None

        if effective_order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            if current_price is None or current_price <= Decimal("0.00"):
                return builder.gate("Limit order requires positive current_price").build()

            offset = (current_price * self._config.limit_offset_bps) / BPS_DIVISOR
            # Favorable limit pricing: Buy slightly lower, Sell slightly higher
            if side == OrderSide.BUY:
                limit_price = (current_price - offset).quantize(PRECISION_FOUR)
            else:
                limit_price = (current_price + offset).quantize(PRECISION_FOUR)

        if effective_order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT):
            if current_price is None or current_price <= Decimal("0.00"):
                return builder.gate("Stop order requires positive current_price").build()
            # Stop placement (breakout trigger): Buy stop higher, Sell stop lower
            offset = (current_price * self._config.limit_offset_bps) / BPS_DIVISOR
            if side == OrderSide.BUY:
                stop_price = (current_price + offset).quantize(PRECISION_FOUR)
            else:
                stop_price = (current_price - offset).quantize(PRECISION_FOUR)

        return (
            builder.with_direction(direction)
            .with_side(side)
            .with_limit_price(limit_price)
            .with_stop_price(stop_price)
            .with_is_executable(True)
            .with_gating_reason(None)
            .build()
        )
