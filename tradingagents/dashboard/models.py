"""Strongly typed View Models and DTOs for Phase 13 Dashboard & CLI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from tradingagents.dataflows.enums import Timeframe


def _serialize_value(val: Any) -> Any:
    """Helper to serialize Decimals, datetimes, and Enums to JSON-compatible types."""
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, datetime):
        return val.isoformat()
    if hasattr(val, "value"):
        return val.value
    if isinstance(val, (list, tuple)):
        return [_serialize_value(item) for item in val]
    if isinstance(val, dict):
        return {k: _serialize_value(v) for k, v in val.items()}
    return val


@dataclass(frozen=True)
class IndicatorViewDTO:
    """Aggregated view of technical indicator observations."""

    ema_9: Decimal | None = None
    ema_21: Decimal | None = None
    sma_20: Decimal | None = None
    sma_50: Decimal | None = None
    sma_200: Decimal | None = None
    rsi_14: Decimal | None = None
    macd_line: Decimal | None = None
    macd_signal: Decimal | None = None
    macd_histogram: Decimal | None = None
    bb_upper: Decimal | None = None
    bb_middle: Decimal | None = None
    bb_lower: Decimal | None = None
    bb_bandwidth: Decimal | None = None
    atr_14: Decimal | None = None
    vwap: Decimal | None = None
    extra_indicators: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(asdict(self))


@dataclass(frozen=True)
class StructureViewDTO:
    """Aggregated view of Smart Money Concepts market structure observations."""

    swing_high: Decimal | None = None
    swing_low: Decimal | None = None
    last_bos_type: str | None = None  # BULLISH / BEARISH
    last_bos_price: Decimal | None = None
    last_choch_type: str | None = None
    last_choch_price: Decimal | None = None
    active_order_blocks_count: int = 0
    unmitigated_fvgs_count: int = 0
    recent_liquidity_sweeps: tuple[str, ...] = ()
    current_dealing_range: str | None = None  # PREMIUM / DISCOUNT / EQUILIBRIUM
    dealing_range_percentile: Decimal | None = None
    market_phase: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(asdict(self))


@dataclass(frozen=True)
class ProbabilityViewDTO:
    """Point-in-time directional probability output."""

    bullish_pct: Decimal = Decimal("33.33")
    bearish_pct: Decimal = Decimal("33.33")
    neutral_pct: Decimal = Decimal("33.34")
    confidence_score: Decimal = Decimal("0.00")
    dominant_direction: str = "NEUTRAL"
    directional_edge: Decimal = Decimal("0.00")
    entropy: Decimal | None = None
    top_positive_features: tuple[str, ...] = ()
    top_negative_features: tuple[str, ...] = ()
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(asdict(self))


@dataclass(frozen=True)
class RiskViewDTO:
    """Point-in-time risk assessment and regime classification."""

    risk_level: str = "LOW"
    volatility_regime: str = "NORMAL"
    regime_tradeable: bool = True
    invalidation_risk: str = "LOW"
    drawdown_risk: str = "LOW"
    signal_conflict_ratio: Decimal = Decimal("0.00")
    regime_quality_score: Decimal = Decimal("100.00")
    position_suitability: str = "FAVORABLE"
    composite_risk_score: Decimal = Decimal("0.00")
    risk_factors: tuple[str, ...] = ()
    explanatory_reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(asdict(self))


@dataclass(frozen=True)
class SynthesisViewDTO:
    """Institutional multi-agent synthesis assessment."""

    directional_bias: str = "NEUTRAL"
    composite_confidence: Decimal = Decimal("0.00")
    conviction_tier: str = "LOW"
    agent_agreement_ratio: Decimal = Decimal("0.00")
    is_actionable: bool = False
    evidence_summary: tuple[str, ...] = ()
    supporting_features: tuple[str, ...] = ()
    conflicting_features: tuple[str, ...] = ()
    final_reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(asdict(self))


@dataclass(frozen=True)
class OrderSummaryDTO:
    """Summary of an individual order in execution history."""

    order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    status: str
    state: str
    requested_qty: Decimal
    filled_qty: Decimal
    remaining_qty: Decimal
    average_price: Decimal | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(asdict(self))


@dataclass(frozen=True)
class ExecutionViewDTO:
    """Aggregated view of portfolio position and recent execution history."""

    symbol: str
    position_qty: Decimal = Decimal("0.00")
    average_entry_price: Decimal = Decimal("0.00")
    realized_pnl: Decimal = Decimal("0.00")
    unrealized_pnl: Decimal = Decimal("0.00")
    active_open_orders_count: int = 0
    active_orders: tuple[OrderSummaryDTO, ...] = ()
    recent_orders: tuple[OrderSummaryDTO, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(asdict(self))


@dataclass(frozen=True)
class DashboardSnapshotDTO:
    """Unified institutional dashboard view model representing full market state as of a point-in-time."""

    symbol: str
    timeframe: Timeframe
    as_of: datetime
    generated_at: datetime
    reference_price: Decimal | None = None
    indicators: IndicatorViewDTO = field(default_factory=IndicatorViewDTO)
    structure: StructureViewDTO = field(default_factory=StructureViewDTO)
    probability: ProbabilityViewDTO = field(default_factory=ProbabilityViewDTO)
    risk: RiskViewDTO = field(default_factory=RiskViewDTO)
    synthesis: SynthesisViewDTO = field(default_factory=SynthesisViewDTO)
    execution: ExecutionViewDTO = field(default_factory=lambda: ExecutionViewDTO(symbol=""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "as_of": self.as_of.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "reference_price": str(self.reference_price) if self.reference_price is not None else None,
            "indicators": self.indicators.to_dict(),
            "structure": self.structure.to_dict(),
            "probability": self.probability.to_dict(),
            "risk": self.risk.to_dict(),
            "synthesis": self.synthesis.to_dict(),
            "execution": self.execution.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
