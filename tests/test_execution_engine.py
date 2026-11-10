"""Comprehensive unit, scenario, and regression test suite for Phase 12: Execution Engine."""

from __future__ import annotations

import sys
import threading
import types
import unittest
from datetime import datetime, timezone
from decimal import Decimal

if "dotenv" not in sys.modules:
    _d = types.ModuleType("dotenv")
    _d.find_dotenv = lambda *a, **k: ""
    _d.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = _d

from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.store import InMemoryFeatureStore
from tradingagents.execution.adapters.paper import PaperBrokerAdapter
from tradingagents.execution.builder import OrderIntentBuilder
from tradingagents.execution.config import ExecutionConfig
from tradingagents.execution.dto import (
    ExecutionReportDTO,
    FillDTO,
    OrderIntentDTO,
    PositionDTO,
)
from tradingagents.execution.engine import ExecutionEngine
from tradingagents.execution.enums import (
    ExecutionStatus,
    OrderSide,
    OrderState,
    OrderType,
    TimeInForce,
    TradeDirection,
)
from tradingagents.execution.planner import ExecutionPlanner
from tradingagents.execution.tracker import ExecutionTracker
from tradingagents.orchestration.dto import (
    ConfidenceAssessmentDTO,
    MarketAssessmentDTO,
    MarketStructureAssessmentDTO,
    ProbabilityAssessmentDTO,
    ProbabilityBreakdownDTO,
    RiskContextAssessmentDTO,
    TechnicalAssessmentDTO,
)
from tradingagents.orchestration.enums import (
    ConvictionTier,
    DirectionalBias,
    MarketPhase,
    RiskLevel as OrchRiskLevel,
)
from tradingagents.risk.dto import RiskAssessmentDTO, RiskSubMetricsDTO
from tradingagents.risk.enums import (
    DrawdownRisk,
    InvalidationRisk,
    PositionSuitability,
    RiskLevel,
    VolatilityRegime,
)


def _make_dummy_assessment(
    symbol: str = "BTCUSDT",
    bias: DirectionalBias = DirectionalBias.BULLISH,
    confidence: Decimal = Decimal("75.00"),
    bullish_prob: Decimal = Decimal("65.00"),
    bearish_prob: Decimal = Decimal("15.00"),
    neutral_prob: Decimal = Decimal("20.00"),
    timestamp: datetime | None = None,
) -> MarketAssessmentDTO:
    ts = timestamp or datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    prob_breakdown = ProbabilityBreakdownDTO(
        bullish=bullish_prob,
        bearish=bearish_prob,
        neutral=neutral_prob,
    )
    return MarketAssessmentDTO(
        symbol=symbol,
        timeframe=Timeframe.H1,
        timestamp=ts,
        directional_bias=bias,
        confidence=confidence,
        probability_breakdown=prob_breakdown,
        evidence_summary=("Test evidence",),
        supporting_features=("ema_9", "fvg_bullish"),
        conflicting_features=(),
        final_reasoning="Synthesized bullish trend with strong structure support.",
        technical_assessment=TechnicalAssessmentDTO(
            bias=bias,
            score=Decimal("40.00"),
            trend_regime="BULLISH",
            volatility_regime="NORMAL",
            momentum_state="POSITIVE",
            signals=("ema_bullish",),
            contributing_indicators=("ema_9", "sma_20"),
            reasoning="Aligned moving averages",
        ),
        structure_assessment=MarketStructureAssessmentDTO(
            bias=bias,
            score=Decimal("40.00"),
            market_phase=MarketPhase.EXPANSION,
            dealing_range_zone="DISCOUNT",
            active_order_blocks_count=1,
            unmitigated_fvgs_count=1,
            sweeps_detected=("sweep_low",),
            key_levels=(Decimal("79000.00"),),
            reasoning="Break of structure confirmed",
        ),
        probability_assessment=ProbabilityAssessmentDTO(
            directional_bias=bias,
            breakdown=prob_breakdown,
            total_score=Decimal("50.00"),
            confidence=confidence,
            top_positive_factors=("ema_9",),
            top_negative_factors=(),
            reasoning="Directional bias supported by structural expansion",
        ),
        risk_assessment=RiskContextAssessmentDTO(
            risk_level=OrchRiskLevel.LOW,
            volatility_state="NORMAL",
            signal_conflict_ratio=Decimal("0.10"),
            invalidation_risk="LOW",
            is_tradeable_regime=True,
            risk_factors=(),
            reasoning="Low structural risk",
        ),
        confidence_assessment=ConfidenceAssessmentDTO(
            composite_confidence=confidence,
            conviction_tier=ConvictionTier.HIGH,
            agent_agreement_ratio=Decimal("0.90"),
            evidence_breadth_score=Decimal("0.80"),
            conflict_penalty=Decimal("0.05"),
            reasoning="High cross-discipline conviction",
        ),
        is_actionable=True,
    )


def _make_dummy_risk(
    symbol: str = "BTCUSDT",
    risk_level: RiskLevel = RiskLevel.LOW,
    regime_tradeable: bool = True,
    volatility_regime: VolatilityRegime = VolatilityRegime.NORMAL,
    timestamp: datetime | None = None,
) -> RiskAssessmentDTO:
    ts = timestamp or datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    return RiskAssessmentDTO(
        symbol=symbol,
        timeframe=Timeframe.H1,
        timestamp=ts,
        risk_level=risk_level,
        volatility_regime=volatility_regime,
        regime_tradeable=regime_tradeable,
        invalidation_risk=InvalidationRisk.LOW,
        signal_conflict_ratio=Decimal("0.10"),
        drawdown_risk=DrawdownRisk.LOW,
        regime_quality=Decimal("90.00"),
        position_suitability=PositionSuitability.FAVORABLE,
        risk_score=Decimal("20.00"),
        sub_metrics=RiskSubMetricsDTO(),
        risk_factors=(),
        explanatory_reasoning="Risk context orderly and tradeable.",
    )


class TestExecutionDTOs(unittest.TestCase):
    """Test immutability, field validation, and invariants of Execution DTOs."""

    def setUp(self) -> None:
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_valid_order_intent(self) -> None:
        intent = OrderIntentDTO(
            intent_id="intent_1",
            client_order_id="co_1",
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            direction=TradeDirection.LONG,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1.5"),
            is_executable=True,
        )
        self.assertEqual(intent.direction, TradeDirection.LONG)
        self.assertEqual(intent.side, OrderSide.BUY)
        self.assertTrue(intent.is_executable)

    def test_invalid_executable_intent_validation(self) -> None:
        with self.assertRaises(DTOValidationError):
            OrderIntentDTO(
                intent_id="intent_1",
                client_order_id="co_1",
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                direction=TradeDirection.NO_TRADE,  # Invalid when executable
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("1.0"),
                is_executable=True,
            )

        with self.assertRaises(DTOValidationError):
            OrderIntentDTO(
                intent_id="intent_1",
                client_order_id="co_1",
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                direction=TradeDirection.LONG,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal("1.0"),
                limit_price=None,  # Limit requires limit_price
                is_executable=True,
            )

    def test_gated_order_intent(self) -> None:
        intent = OrderIntentDTO(
            intent_id="intent_2",
            client_order_id="co_2",
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            direction=TradeDirection.NO_TRADE,
            side=None,
            order_type=OrderType.MARKET,
            quantity=Decimal("1.0"),
            is_executable=False,
            gating_reason="Risk level is EXTREME",
        )
        self.assertFalse(intent.is_executable)
        self.assertEqual(intent.gating_reason, "Risk level is EXTREME")

    def test_fill_and_execution_report_dto(self) -> None:
        fill = FillDTO(
            fill_id="f_1",
            order_id="ord_1",
            timestamp=self.ts,
            price=Decimal("80000.00"),
            quantity=Decimal("0.5"),
            fee=Decimal("4.00"),
        )
        report = ExecutionReportDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            order_id="ord_1",
            client_order_id="co_1",
            status=ExecutionStatus.EXECUTED,
            state=OrderState.FILLED,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=Decimal("0.5"),
            filled_quantity=Decimal("0.5"),
            remaining_quantity=Decimal("0.0"),
            average_price=Decimal("80000.00"),
            total_fee=Decimal("4.00"),
            fills=(fill,),
        )
        self.assertEqual(report.feature_name, "execution_report")
        self.assertEqual(report.status, ExecutionStatus.EXECUTED)
        self.assertEqual(report.state, OrderState.FILLED)
        self.assertEqual(len(report.fills), 1)


class TestExecutionPlanner(unittest.TestCase):
    """Test deterministic evaluation of execution safeguards."""

    def setUp(self) -> None:
        self.config = ExecutionConfig(
            min_confidence=Decimal("60.00"),
            min_probability_edge=Decimal("15.00"),
            max_allowed_risk_level=RiskLevel.HIGH,
            require_tradeable_regime=True,
            limit_offset_bps=Decimal("10.0"),
        )
        self.planner = ExecutionPlanner(self.config)

    def test_gate_when_untradeable_regime(self) -> None:
        assessment = _make_dummy_assessment()
        risk = _make_dummy_risk(regime_tradeable=False, volatility_regime=VolatilityRegime.EXPLOSIVE)

        intent = self.planner.plan(assessment, risk, current_price=Decimal("80000.0"))
        self.assertFalse(intent.is_executable)
        self.assertIn("Regime untradeable", intent.gating_reason or "")

    def test_gate_when_extreme_risk_level(self) -> None:
        assessment = _make_dummy_assessment()
        risk = _make_dummy_risk(risk_level=RiskLevel.EXTREME)

        intent = self.planner.plan(assessment, risk, current_price=Decimal("80000.0"))
        self.assertFalse(intent.is_executable)
        self.assertIn("exceeds maximum allowed", intent.gating_reason or "")

    def test_gate_when_low_confidence(self) -> None:
        assessment = _make_dummy_assessment(confidence=Decimal("45.00"))
        risk = _make_dummy_risk()

        intent = self.planner.plan(assessment, risk, current_price=Decimal("80000.0"))
        self.assertFalse(intent.is_executable)
        self.assertIn("below threshold", intent.gating_reason or "")

    def test_gate_when_neutral_bias(self) -> None:
        assessment = _make_dummy_assessment(bias=DirectionalBias.NEUTRAL)
        risk = _make_dummy_risk()

        intent = self.planner.plan(assessment, risk, current_price=Decimal("80000.0"))
        self.assertFalse(intent.is_executable)
        self.assertIn("bias is NEUTRAL", intent.gating_reason or "")

    def test_gate_when_insufficient_edge(self) -> None:
        assessment = _make_dummy_assessment(
            bias=DirectionalBias.BULLISH,
            bullish_prob=Decimal("45.00"),
            bearish_prob=Decimal("35.00"),  # Edge = 10.00 < 15.00 min edge
            neutral_prob=Decimal("20.00"),
        )
        risk = _make_dummy_risk()

        intent = self.planner.plan(assessment, risk, current_price=Decimal("80000.0"))
        self.assertFalse(intent.is_executable)
        self.assertIn("edge 10.00% below threshold", intent.gating_reason or "")

    def test_executable_bullish_market_order(self) -> None:
        assessment = _make_dummy_assessment(bias=DirectionalBias.BULLISH)
        risk = _make_dummy_risk()

        intent = self.planner.plan(
            assessment,
            risk,
            current_price=Decimal("80000.0"),
            quantity=Decimal("2.0"),
            order_type=OrderType.MARKET,
        )
        self.assertTrue(intent.is_executable)
        self.assertEqual(intent.direction, TradeDirection.LONG)
        self.assertEqual(intent.side, OrderSide.BUY)
        self.assertEqual(intent.quantity, Decimal("2.0"))
        self.assertEqual(intent.order_type, OrderType.MARKET)

    def test_executable_bearish_limit_order(self) -> None:
        assessment = _make_dummy_assessment(
            bias=DirectionalBias.BEARISH,
            bullish_prob=Decimal("15.00"),
            bearish_prob=Decimal("70.00"),
            neutral_prob=Decimal("15.00"),
        )
        risk = _make_dummy_risk()

        # Limit order: 10 bps offset on 80,000 = 80. For SELL, limit = 80,080
        intent = self.planner.plan(
            assessment,
            risk,
            current_price=Decimal("80000.0"),
            quantity=Decimal("1.0"),
            order_type=OrderType.LIMIT,
        )
        self.assertTrue(intent.is_executable)
        self.assertEqual(intent.direction, TradeDirection.SHORT)
        self.assertEqual(intent.side, OrderSide.SELL)
        self.assertEqual(intent.limit_price, Decimal("80080.0000"))


class TestExecutionTracker(unittest.TestCase):
    """Test order state transitions, partial fills, and position ledger math."""

    def setUp(self) -> None:
        self.tracker = ExecutionTracker()
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_state_lifecycle_and_fills(self) -> None:
        report = ExecutionReportDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            order_id="ord_101",
            client_order_id="co_101",
            status=ExecutionStatus.PARTIAL,
            state=OrderState.SUBMITTED,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            requested_quantity=Decimal("2.0"),
            filled_quantity=Decimal("0.0"),
            remaining_quantity=Decimal("2.0"),
            limit_price=Decimal("80000.00"),
        )
        self.tracker.record_order(report)

        # Apply Partial Fill 1: 0.8 BTC @ 79,900
        fill1 = FillDTO(
            fill_id="f_1",
            order_id="ord_101",
            timestamp=self.ts,
            price=Decimal("79900.00"),
            quantity=Decimal("0.8"),
            fee=Decimal("3.196"),
        )
        updated = self.tracker.apply_fill("ord_101", fill1)
        self.assertEqual(updated.state, OrderState.PARTIALLY_FILLED)
        self.assertEqual(updated.filled_quantity, Decimal("0.8"))
        self.assertEqual(updated.remaining_quantity, Decimal("1.2"))
        self.assertEqual(updated.average_price, Decimal("79900.0000"))

        pos = self.tracker.get_position("BTCUSDT")
        self.assertEqual(pos.quantity, Decimal("0.8"))
        self.assertEqual(pos.average_entry_price, Decimal("79900.0000"))

        # Apply Final Fill 2: 1.2 BTC @ 80,000
        fill2 = FillDTO(
            fill_id="f_2",
            order_id="ord_101",
            timestamp=self.ts,
            price=Decimal("80000.00"),
            quantity=Decimal("1.2"),
            fee=Decimal("4.800"),
        )
        final_report = self.tracker.apply_fill("ord_101", fill2)
        self.assertEqual(final_report.state, OrderState.FILLED)
        self.assertEqual(final_report.status, ExecutionStatus.EXECUTED)
        self.assertEqual(final_report.filled_quantity, Decimal("2.0"))
        self.assertEqual(final_report.remaining_quantity, Decimal("0.0"))

        # Weighted average: (0.8 * 79900 + 1.2 * 80000) / 2.0 = (63920 + 96000) / 2 = 79960.0000
        self.assertEqual(final_report.average_price, Decimal("79960.0000"))

        pos = self.tracker.get_position("BTCUSDT")
        self.assertEqual(pos.quantity, Decimal("2.0"))
        self.assertEqual(pos.average_entry_price, Decimal("79960.0000"))

    def test_position_closure_and_realized_pnl(self) -> None:
        # Initial buy 1 BTC @ 80,000
        buy_order = ExecutionReportDTO(
            symbol="ETHUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            order_id="ord_buy",
            client_order_id="co_buy",
            status=ExecutionStatus.PARTIAL,
            state=OrderState.SUBMITTED,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=Decimal("10.0"),
            filled_quantity=Decimal("0.0"),
            remaining_quantity=Decimal("10.0"),
        )
        self.tracker.record_order(buy_order)
        self.tracker.apply_fill(
            "ord_buy",
            FillDTO("f_buy", "ord_buy", self.ts, Decimal("3000.00"), Decimal("10.0")),
        )

        # Sell 6 ETH @ 3200 (Gain: 6 * 200 = 1200)
        sell_order = ExecutionReportDTO(
            symbol="ETHUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            order_id="ord_sell",
            client_order_id="co_sell",
            status=ExecutionStatus.PARTIAL,
            state=OrderState.SUBMITTED,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            requested_quantity=Decimal("6.0"),
            filled_quantity=Decimal("0.0"),
            remaining_quantity=Decimal("6.0"),
        )
        self.tracker.record_order(sell_order)
        self.tracker.apply_fill(
            "ord_sell",
            FillDTO("f_sell", "ord_sell", self.ts, Decimal("3200.00"), Decimal("6.0")),
        )

        pos = self.tracker.get_position("ETHUSDT")
        self.assertEqual(pos.quantity, Decimal("4.0"))
        self.assertEqual(pos.average_entry_price, Decimal("3000.0000"))
        self.assertEqual(pos.realized_pnl, Decimal("1200.00"))


class TestPaperBrokerAdapter(unittest.TestCase):
    """Test paper broker execution simulation, slippage, and order matching."""

    def setUp(self) -> None:
        self.config = ExecutionConfig(
            max_slippage_bps=Decimal("10.0"),
            taker_fee_bps=Decimal("10.0"),
            maker_fee_bps=Decimal("5.0"),
        )
        self.broker = PaperBrokerAdapter(
            config=self.config,
            initial_balances={"USD": Decimal("200000.00")},
        )
        self.broker.set_market_price("BTCUSDT", Decimal("80000.00"))
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_market_buy_execution_with_slippage_and_balance_deduction(self) -> None:
        intent = OrderIntentDTO(
            intent_id="int_1",
            client_order_id="co_1",
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            direction=TradeDirection.LONG,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1.0"),
            is_executable=True,
        )

        report = self.broker.submit_order(intent)
        self.assertEqual(report.status, ExecutionStatus.EXECUTED)
        self.assertEqual(report.state, OrderState.FILLED)
        # Price 80,000 + 10 bps slippage (80) = 80,080.0000
        self.assertEqual(report.average_price, Decimal("80080.0000"))

        pos = self.broker.get_position("BTCUSDT")
        self.assertEqual(pos.quantity, Decimal("1.0"))
        self.assertLess(self.broker.get_balance("USD"), Decimal("120000.00"))

    def test_limit_order_queueing_and_trigger_on_tick(self) -> None:
        # Market price is 80,000. Submit BUY limit @ 79,500 (below market -> queues)
        intent = OrderIntentDTO(
            intent_id="int_limit",
            client_order_id="co_limit",
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            direction=TradeDirection.LONG,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1.0"),
            limit_price=Decimal("79500.00"),
            is_executable=True,
        )

        report = self.broker.submit_order(intent)
        self.assertEqual(report.state, OrderState.SUBMITTED)
        self.assertEqual(len(self.broker.get_open_orders("BTCUSDT")), 1)

        # Market tick arrives at 79,400 (below limit) -> should trigger fill
        filled_reports = self.broker.process_market_tick(
            symbol="BTCUSDT",
            price=Decimal("79400.00"),
            low=Decimal("79350.00"),
            timestamp=self.ts,
        )
        self.assertEqual(len(filled_reports), 1)
        self.assertEqual(filled_reports[0].state, OrderState.FILLED)
        self.assertEqual(len(self.broker.get_open_orders("BTCUSDT")), 0)

    def test_order_cancellation(self) -> None:
        intent = OrderIntentDTO(
            intent_id="int_cancel",
            client_order_id="co_cancel",
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            direction=TradeDirection.LONG,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1.0"),
            limit_price=Decimal("75000.00"),
            is_executable=True,
        )
        report = self.broker.submit_order(intent)
        self.assertEqual(report.state, OrderState.SUBMITTED)

        cancelled = self.broker.cancel_order(report.order_id)
        self.assertEqual(cancelled.state, OrderState.CANCELLED)
        self.assertEqual(len(self.broker.get_open_orders("BTCUSDT")), 0)


class TestExecutionEngine(unittest.TestCase):
    """Test full ExecutionEngine pipeline, FeatureStore persistence, memoization, and concurrency."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.broker = PaperBrokerAdapter(initial_balances={"USD": Decimal("500000.00")})
        self.broker.set_market_price("BTCUSDT", Decimal("80000.00"))
        self.engine = ExecutionEngine(
            broker=self.broker,
            feature_store=self.store,
        )
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_end_to_end_assess_and_execute(self) -> None:
        assessment = _make_dummy_assessment()
        risk = _make_dummy_risk()

        report = self.engine.assess_and_execute(
            assessment=assessment,
            risk=risk,
            current_price=Decimal("80000.00"),
            quantity=Decimal("1.0"),
        )
        self.assertEqual(report.status, ExecutionStatus.EXECUTED)
        self.assertEqual(report.state, OrderState.FILLED)

        # Check FeatureStore persistence
        stored_report = self.store.get_as_of(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            feature_name="execution_report",
            as_of=self.ts,
        )
        self.assertIsNotNone(stored_report)
        self.assertEqual(stored_report.order_id, report.order_id)

    def test_gated_execution_pipeline(self) -> None:
        # Create an untradeable assessment
        assessment = _make_dummy_assessment()
        risk = _make_dummy_risk(regime_tradeable=False)

        report = self.engine.assess_and_execute(
            assessment=assessment,
            risk=risk,
            current_price=Decimal("80000.00"),
        )
        self.assertEqual(report.status, ExecutionStatus.GATED_BY_RISK)
        self.assertEqual(report.state, OrderState.REJECTED)
        self.assertIn("Regime untradeable", report.gating_reason or "")

    def test_lru_memoization(self) -> None:
        assessment = _make_dummy_assessment()
        risk = _make_dummy_risk()

        # Call plan twice with identical inputs
        plan1 = self.engine.plan(assessment, risk, current_price=Decimal("80000.00"))
        plan2 = self.engine.plan(assessment, risk, current_price=Decimal("80000.00"))

        # Should be identical cached object
        self.assertIs(plan1, plan2)

    def test_thread_safety_under_concurrent_execution(self) -> None:
        num_threads = 8
        orders_per_thread = 5
        errors: list[Exception] = []

        def worker(idx: int) -> None:
            try:
                for i in range(orders_per_thread):
                    ts = datetime(2026, 11, 10, 12, idx, i, tzinfo=timezone.utc)
                    assessment = _make_dummy_assessment(timestamp=ts)
                    risk = _make_dummy_risk(timestamp=ts)
                    self.engine.assess_and_execute(
                        assessment=assessment,
                        risk=risk,
                        current_price=Decimal("80000.00"),
                        quantity=Decimal("0.1"),
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")
        pos = self.engine.get_position("BTCUSDT")
        # 8 * 5 * 0.1 = 4.0 BTC
        self.assertEqual(pos.quantity, Decimal("4.0"))


if __name__ == "__main__":
    unittest.main()
