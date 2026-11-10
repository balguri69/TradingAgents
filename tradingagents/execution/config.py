"""Configuration for Phase 12 Execution Engine."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.execution.enums import OrderType, TimeInForce
from tradingagents.risk.enums import RiskLevel

PRECISION_TWO = Decimal("0.01")
HUNDRED = Decimal("100.00")
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ExecutionConfig:
    """Institutional configuration parameters for trade execution gating and order intent.
    
    All thresholds are strictly deterministic Decimals.
    """

    min_confidence: Decimal = Decimal("50.00")
    min_probability_edge: Decimal = Decimal("15.00")
    max_allowed_risk_level: RiskLevel = RiskLevel.HIGH
    require_tradeable_regime: bool = True
    default_order_type: OrderType = OrderType.MARKET
    limit_offset_bps: Decimal = Decimal("5.0")
    max_slippage_bps: Decimal = Decimal("25.0")
    default_time_in_force: TimeInForce = TimeInForce.GTC
    default_order_quantity: Decimal = Decimal("1.0")
    maker_fee_bps: Decimal = Decimal("5.0")
    taker_fee_bps: Decimal = Decimal("10.0")
    max_cache_size: int = 10000

    def __post_init__(self) -> None:
        if not (ZERO <= self.min_confidence <= HUNDRED):
            raise DTOValidationError(f"min_confidence must be in [0.00, 100.00], got {self.min_confidence}")
        if not (ZERO <= self.min_probability_edge <= HUNDRED):
            raise DTOValidationError(
                f"min_probability_edge must be in [0.00, 100.00], got {self.min_probability_edge}"
            )
        if not isinstance(self.max_allowed_risk_level, RiskLevel):
            raise DTOValidationError(
                f"max_allowed_risk_level must be RiskLevel instance, got {type(self.max_allowed_risk_level)}"
            )
        if not isinstance(self.default_order_type, OrderType):
            raise DTOValidationError(
                f"default_order_type must be OrderType instance, got {type(self.default_order_type)}"
            )
        if not isinstance(self.default_time_in_force, TimeInForce):
            raise DTOValidationError(
                f"default_time_in_force must be TimeInForce instance, got {type(self.default_time_in_force)}"
            )
        if self.limit_offset_bps < ZERO:
            raise DTOValidationError(f"limit_offset_bps must be non-negative, got {self.limit_offset_bps}")
        if self.max_slippage_bps < ZERO:
            raise DTOValidationError(f"max_slippage_bps must be non-negative, got {self.max_slippage_bps}")
        if self.default_order_quantity <= ZERO:
            raise DTOValidationError(f"default_order_quantity must be positive, got {self.default_order_quantity}")
        if self.maker_fee_bps < ZERO:
            raise DTOValidationError(f"maker_fee_bps must be non-negative, got {self.maker_fee_bps}")
        if self.taker_fee_bps < ZERO:
            raise DTOValidationError(f"taker_fee_bps must be non-negative, got {self.taker_fee_bps}")
        if self.max_cache_size < 1:
            raise DTOValidationError(f"max_cache_size must be >= 1, got {self.max_cache_size}")
