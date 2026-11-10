"""Dashboard Service: thread-safe point-in-time data aggregation across all analytical and execution engines."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from tradingagents.dataflows.contracts.features import FeatureStore
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dashboard.models import (
    DashboardSnapshotDTO,
    ExecutionViewDTO,
    IndicatorViewDTO,
    OrderSummaryDTO,
    ProbabilityViewDTO,
    RiskViewDTO,
    StructureViewDTO,
    SynthesisViewDTO,
)
from tradingagents.execution.engine import ExecutionEngine
from tradingagents.orchestration.orchestrator import MultiAgentOrchestrator
from tradingagents.risk.engine import RiskEngine

TIMEFRAME_MAP = {
    "1m": Timeframe.M1,
    "m1": Timeframe.M1,
    "5m": Timeframe.M5,
    "m5": Timeframe.M5,
    "15m": Timeframe.M15,
    "m15": Timeframe.M15,
    "1h": Timeframe.H1,
    "h1": Timeframe.H1,
    "4h": Timeframe.H4,
    "h4": Timeframe.H4,
    "1d": Timeframe.D1,
    "d1": Timeframe.D1,
    "1w": Timeframe.W1,
    "w1": Timeframe.W1,
}


class DashboardService:
    """Thread-safe aggregation service compiling point-in-time dashboard views.
    
    Adheres strictly to Phase 13 requirements:
    - Deterministic and auditable
    - Zero future lookahead bias
    - Zero execution or trading decisions inside the service
    - Read-only queries to FeatureStore and upstream engines
    """

    def __init__(
        self,
        feature_store: FeatureStore | None = None,
        orchestrator: MultiAgentOrchestrator | None = None,
        risk_engine: RiskEngine | None = None,
        execution_engine: ExecutionEngine | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._feature_store = feature_store
        self._orchestrator = orchestrator
        self._risk_engine = risk_engine
        self._execution_engine = execution_engine

    @staticmethod
    def normalize_timeframe(tf: Timeframe | str) -> Timeframe:
        """Normalize string or enum to Timeframe."""
        if isinstance(tf, Timeframe):
            return tf
        cleaned = tf.strip().lower()
        if cleaned in TIMEFRAME_MAP:
            return TIMEFRAME_MAP[cleaned]
        try:
            return Timeframe(cleaned)
        except ValueError:
            return Timeframe.H1

    def get_snapshot(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        as_of: datetime | None = None,
        reference_price: Decimal | None = None,
    ) -> DashboardSnapshotDTO:
        """Produce a complete, point-in-time market and system state snapshot."""
        with self._lock:
            tf = self.normalize_timeframe(timeframe)
            norm_symbol = symbol.strip().upper()
            query_time = as_of or datetime.now(timezone.utc)
            gen_time = datetime.now(timezone.utc)

            indicators = self._build_indicator_view(norm_symbol, tf, query_time)
            structure = self._build_structure_view(norm_symbol, tf, query_time)
            probability = self._build_probability_view(norm_symbol, tf, query_time)
            risk = self._build_risk_view(norm_symbol, tf, query_time)
            synthesis = self._build_synthesis_view(norm_symbol, tf, query_time)
            execution = self._build_execution_view(norm_symbol)

            # Infer reference price if not provided
            ref_p = reference_price
            if ref_p is None:
                if indicators.vwap is not None:
                    ref_p = indicators.vwap
                elif indicators.bb_middle is not None:
                    ref_p = indicators.bb_middle
                elif indicators.ema_9 is not None:
                    ref_p = indicators.ema_9

            return DashboardSnapshotDTO(
                symbol=norm_symbol,
                timeframe=tf,
                as_of=query_time,
                generated_at=gen_time,
                reference_price=ref_p,
                indicators=indicators,
                structure=structure,
                probability=probability,
                risk=risk,
                synthesis=synthesis,
                execution=execution,
            )

    def _get_feature(self, symbol: str, timeframe: Timeframe, feature_name: str, as_of: datetime) -> Any | None:
        """Query FeatureStore safely without throwing exceptions."""
        if self._feature_store is None:
            return None
        try:
            return self._feature_store.get_as_of(
                symbol=symbol,
                timeframe=timeframe,
                feature_name=feature_name,
                as_of=as_of,
            )
        except Exception:
            return None

    def _build_indicator_view(self, symbol: str, timeframe: Timeframe, as_of: datetime) -> IndicatorViewDTO:
        """Extract technical indicator features point-in-time."""
        ema9 = self._get_feature(symbol, timeframe, "ema_9", as_of)
        ema21 = self._get_feature(symbol, timeframe, "ema_21", as_of)
        sma20 = self._get_feature(symbol, timeframe, "sma_20", as_of)
        sma50 = self._get_feature(symbol, timeframe, "sma_50", as_of)
        sma200 = self._get_feature(symbol, timeframe, "sma_200", as_of)
        rsi14 = self._get_feature(symbol, timeframe, "rsi_14", as_of)
        macd = self._get_feature(symbol, timeframe, "macd", as_of)
        boll = self._get_feature(symbol, timeframe, "bollinger", as_of)
        atr14 = self._get_feature(symbol, timeframe, "atr_14", as_of)
        vwap = self._get_feature(symbol, timeframe, "vwap", as_of)

        extra: dict[str, str] = {}

        return IndicatorViewDTO(
            ema_9=getattr(ema9, "value", None),
            ema_21=getattr(ema21, "value", None),
            sma_20=getattr(sma20, "value", None),
            sma_50=getattr(sma50, "value", None),
            sma_200=getattr(sma200, "value", None),
            rsi_14=getattr(rsi14, "value", None),
            macd_line=getattr(macd, "macd_line", None),
            macd_signal=getattr(macd, "signal_line", None),
            macd_histogram=getattr(macd, "histogram", None),
            bb_upper=getattr(boll, "upper_band", None),
            bb_middle=getattr(boll, "middle_band", None),
            bb_lower=getattr(boll, "lower_band", None),
            bb_bandwidth=getattr(boll, "bandwidth", None),
            atr_14=getattr(atr14, "value", None),
            vwap=getattr(vwap, "vwap", getattr(vwap, "value", None)),
            extra_indicators=extra,
        )

    def _build_structure_view(self, symbol: str, timeframe: Timeframe, as_of: datetime) -> StructureViewDTO:
        """Extract market structure features point-in-time."""
        swing = self._get_feature(symbol, timeframe, "swing", as_of)
        bos = self._get_feature(symbol, timeframe, "break_of_structure", as_of)
        choch = self._get_feature(symbol, timeframe, "change_of_character", as_of)
        fvg = self._get_feature(symbol, timeframe, "fair_value_gap", as_of)
        ob = self._get_feature(symbol, timeframe, "order_block", as_of)
        sweep = self._get_feature(symbol, timeframe, "liquidity_sweep", as_of)
        pd_zone = self._get_feature(symbol, timeframe, "premium_discount", as_of)

        bos_type = None
        if bos is not None:
            bos_type = "BULLISH" if getattr(bos, "is_bullish", True) else "BEARISH"

        choch_type = None
        if choch is not None:
            choch_type = "BULLISH" if getattr(choch, "is_bullish", True) else "BEARISH"

        sweeps: list[str] = []
        if sweep is not None:
            side = "BUYSIDE" if getattr(sweep, "is_buy_side", True) else "SELLSIDE"
            sweeps.append(f"{side} @ {getattr(sweep, 'swept_level', '')}")

        return StructureViewDTO(
            swing_high=getattr(swing, "high", None) or getattr(swing, "swing_high", None),
            swing_low=getattr(swing, "low", None) or getattr(swing, "swing_low", None),
            last_bos_type=bos_type,
            last_bos_price=getattr(bos, "broken_level", None),
            last_choch_type=choch_type,
            last_choch_price=getattr(choch, "broken_level", None),
            active_order_blocks_count=1 if ob is not None else 0,
            unmitigated_fvgs_count=1 if fvg is not None else 0,
            recent_liquidity_sweeps=tuple(sweeps),
            current_dealing_range=getattr(pd_zone, "zone", None),
            dealing_range_percentile=getattr(pd_zone, "percentile", None),
            market_phase=None,
        )

    def _build_probability_view(self, symbol: str, timeframe: Timeframe, as_of: datetime) -> ProbabilityViewDTO:
        """Extract directional probability features point-in-time."""
        prob_feat = self._get_feature(symbol, timeframe, "probability_assessment", as_of) or self._get_feature(
            symbol, timeframe, "probability_breakdown", as_of
        )

        if prob_feat is not None:
            # Handle ProbabilityAssessmentDTO or ProbabilityBreakdownDTO
            b_pct = getattr(prob_feat, "bullish", None)
            be_pct = getattr(prob_feat, "bearish", None)
            n_pct = getattr(prob_feat, "neutral", None)

            if b_pct is None and hasattr(prob_feat, "breakdown"):
                bd = prob_feat.breakdown
                b_pct = getattr(bd, "bullish", Decimal("33.33"))
                be_pct = getattr(bd, "bearish", Decimal("33.33"))
                n_pct = getattr(bd, "neutral", Decimal("33.34"))

            b_pct = b_pct or Decimal("33.33")
            be_pct = be_pct or Decimal("33.33")
            n_pct = n_pct or Decimal("33.34")

            conf = getattr(prob_feat, "confidence", Decimal("0.00"))
            dom = getattr(prob_feat, "dominant_direction", None) or (
                "BULLISH" if b_pct > be_pct and b_pct > n_pct else ("BEARISH" if be_pct > b_pct and be_pct > n_pct else "NEUTRAL")
            )
            edge = abs(b_pct - be_pct)
            entropy = getattr(prob_feat, "entropy", None)
            top_pos = tuple(getattr(prob_feat, "top_positive_factors", ()) or getattr(prob_feat, "top_positive_features", ()))
            top_neg = tuple(getattr(prob_feat, "top_negative_factors", ()) or getattr(prob_feat, "top_negative_features", ()))
            reasoning = getattr(prob_feat, "reasoning", "")

            return ProbabilityViewDTO(
                bullish_pct=b_pct,
                bearish_pct=be_pct,
                neutral_pct=n_pct,
                confidence_score=conf,
                dominant_direction=str(dom),
                directional_edge=edge,
                entropy=entropy,
                top_positive_features=top_pos,
                top_negative_features=top_neg,
                reasoning=reasoning,
            )

        return ProbabilityViewDTO()

    def _build_risk_view(self, symbol: str, timeframe: Timeframe, as_of: datetime) -> RiskViewDTO:
        """Extract risk assessment features point-in-time."""
        risk_feat = self._get_feature(symbol, timeframe, "risk_assessment", as_of)

        if risk_feat is not None:
            r_level = getattr(getattr(risk_feat, "risk_level", None), "value", str(getattr(risk_feat, "risk_level", "LOW")))
            v_regime = getattr(getattr(risk_feat, "volatility_regime", None), "value", str(getattr(risk_feat, "volatility_regime", "NORMAL")))
            r_tradeable = bool(getattr(risk_feat, "regime_tradeable", True))
            inv_risk = getattr(getattr(risk_feat, "invalidation_risk", None), "value", str(getattr(risk_feat, "invalidation_risk", "LOW")))
            dd_risk = getattr(getattr(risk_feat, "drawdown_risk", None), "value", str(getattr(risk_feat, "drawdown_risk", "LOW")))
            conflict = getattr(risk_feat, "signal_conflict_ratio", Decimal("0.00"))
            quality = getattr(risk_feat, "regime_quality", Decimal("100.00"))
            suitability = getattr(getattr(risk_feat, "position_suitability", None), "value", str(getattr(risk_feat, "position_suitability", "FAVORABLE")))
            score = getattr(risk_feat, "risk_score", Decimal("0.00"))
            factors = tuple(getattr(risk_feat, "risk_factors", ()))
            reasoning = getattr(risk_feat, "explanatory_reasoning", "")

            return RiskViewDTO(
                risk_level=r_level,
                volatility_regime=v_regime,
                regime_tradeable=r_tradeable,
                invalidation_risk=inv_risk,
                drawdown_risk=dd_risk,
                signal_conflict_ratio=conflict,
                regime_quality_score=quality,
                position_suitability=suitability,
                composite_risk_score=score,
                risk_factors=factors,
                explanatory_reasoning=reasoning,
            )

        return RiskViewDTO()

    def _build_synthesis_view(self, symbol: str, timeframe: Timeframe, as_of: datetime) -> SynthesisViewDTO:
        """Extract multi-agent synthesis assessment."""
        synth_feat = self._get_feature(symbol, timeframe, "market_assessment", as_of)

        if synth_feat is not None:
            bias = getattr(getattr(synth_feat, "directional_bias", None), "value", str(getattr(synth_feat, "directional_bias", "NEUTRAL")))
            conf = getattr(synth_feat, "confidence", Decimal("0.00"))
            conv_tier = "MODERATE"
            agreement = Decimal("0.00")
            if hasattr(synth_feat, "confidence_assessment"):
                ca = synth_feat.confidence_assessment
                conv_tier = getattr(getattr(ca, "conviction_tier", None), "value", "MODERATE")
                agreement = getattr(ca, "agent_agreement_ratio", Decimal("0.00"))

            is_act = bool(getattr(synth_feat, "is_actionable", False))
            ev = tuple(getattr(synth_feat, "evidence_summary", ()))
            sup = tuple(getattr(synth_feat, "supporting_features", ()))
            con = tuple(getattr(synth_feat, "conflicting_features", ()))
            reasoning = getattr(synth_feat, "final_reasoning", "")

            return SynthesisViewDTO(
                directional_bias=bias,
                composite_confidence=conf,
                conviction_tier=conv_tier,
                agent_agreement_ratio=agreement,
                is_actionable=is_act,
                evidence_summary=ev,
                supporting_features=sup,
                conflicting_features=con,
                final_reasoning=reasoning,
            )

        return SynthesisViewDTO()

    def _build_execution_view(self, symbol: str) -> ExecutionViewDTO:
        """Extract current portfolio position and execution status from ExecutionEngine."""
        if self._execution_engine is None:
            return ExecutionViewDTO(symbol=symbol)

        pos = self._execution_engine.get_position(symbol)
        open_orders = self._execution_engine.get_open_orders(symbol)

        active_summaries: list[OrderSummaryDTO] = []
        for o in open_orders:
            active_summaries.append(
                OrderSummaryDTO(
                    order_id=o.order_id,
                    client_order_id=o.client_order_id,
                    symbol=o.symbol,
                    side=getattr(getattr(o, "side", None), "value", str(o.side)),
                    order_type=getattr(getattr(o, "order_type", None), "value", str(o.order_type)),
                    status=getattr(getattr(o, "status", None), "value", str(o.status)),
                    state=getattr(getattr(o, "state", None), "value", str(o.state)),
                    requested_qty=o.requested_quantity,
                    filled_qty=o.filled_quantity,
                    remaining_qty=o.remaining_quantity,
                    average_price=o.average_price,
                    created_at=o.created_at,
                )
            )

        return ExecutionViewDTO(
            symbol=symbol,
            position_qty=pos.quantity,
            average_entry_price=pos.average_entry_price,
            realized_pnl=pos.realized_pnl,
            unrealized_pnl=pos.unrealized_pnl,
            active_open_orders_count=len(active_summaries),
            active_orders=tuple(active_summaries),
            recent_orders=(),
        )
