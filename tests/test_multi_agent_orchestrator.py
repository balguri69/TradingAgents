"""Comprehensive unit and regression test suite for Phase 10: Multi-Agent Orchestrator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import sys
import threading
import types
import unittest

if "dotenv" not in sys.modules:
    _d = types.ModuleType("dotenv")
    _d.find_dotenv = lambda *a, **k: ""
    _d.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = _d

from tradingagents.dataflows.dto.features import (
    ATRDTO,
    BollingerBandsDTO,
    BreakOfStructureDTO,
    ChangeOfCharacterDTO,
    EMADTO,
    FairValueGapDTO,
    LiquiditySweepDTO,
    MACDDTO,
    OrderBlockDTO,
    PremiumDiscountDTO,
    RSIDTO,
    SMADTO,
    VolumeProfileDTO,
    VWAPDTO,
)
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.features.store import InMemoryFeatureStore
from tradingagents.orchestration.adapters import LLMNarrativeAdapter
from tradingagents.orchestration.agents import (
    ConfidenceEvidenceAgent,
    FinalSynthesisAgent,
    MarketStructureAgent,
    ProbabilityAgent,
    RiskContextAgent,
    TechnicalAnalysisAgent,
)
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
    AgentRole,
    ConvictionTier,
    DirectionalBias,
    MarketPhase,
    RiskLevel,
)
from tradingagents.orchestration.orchestrator import MultiAgentOrchestrator
from tradingagents.orchestration.protocols import MarketAgent, MarketOrchestrator


class TestSpecializedAgents(unittest.TestCase):
    """Test individual deterministic specialized analytical agents."""

    def setUp(self) -> None:
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        self.tech_agent = TechnicalAnalysisAgent()
        self.struct_agent = MarketStructureAgent()
        self.prob_agent = ProbabilityAgent()
        self.risk_agent = RiskContextAgent()
        self.conf_agent = ConfidenceEvidenceAgent()
        self.synth_agent = FinalSynthesisAgent()

    def test_protocol_conformance(self) -> None:
        """Verify all agents satisfy MarketAgent runtime protocol."""
        self.assertIsInstance(self.tech_agent, MarketAgent)
        self.assertIsInstance(self.struct_agent, MarketAgent)
        self.assertIsInstance(self.prob_agent, MarketAgent)
        self.assertIsInstance(self.risk_agent, MarketAgent)
        self.assertIsInstance(self.conf_agent, MarketAgent)
        self.assertIsInstance(self.synth_agent, MarketAgent)

    def test_technical_analysis_agent_bullish(self) -> None:
        """Verify TechnicalAnalysisAgent detects bullish alignment, positive momentum, and VWAP acceptance."""
        features = {
            "ema_9": EMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_9", period=9, value=Decimal("585.0")),
            "ema_21": EMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_21", period=21, value=Decimal("580.0")),
            "sma_20": SMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="sma_20", period=20, value=Decimal("582.0")),
            "sma_50": SMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="sma_50", period=50, value=Decimal("575.0")),
            "macd": MACDDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="macd", macd_line=Decimal("3.0"), signal_line=Decimal("1.0"), histogram=Decimal("2.0")),
            "vwap": VWAPDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="vwap", vwap=Decimal("580.0"), volume_sum=Decimal("10000.0")),
        }
        dto = self.tech_agent.analyze("SPY", Timeframe.H1, features, current_price=Decimal("588.0"), as_of=self.ts)
        self.assertEqual(dto.bias, DirectionalBias.BULLISH)
        self.assertGreater(dto.score, Decimal("20.00"))
        self.assertEqual(dto.trend_regime, "STRONG_BULLISH_TREND")
        self.assertIn("EMA", dto.contributing_indicators)
        self.assertIn("MACD", dto.contributing_indicators)

    def test_market_structure_agent_accumulation(self) -> None:
        """Verify MarketStructureAgent correctly identifies ACCUMULATION phase in discount zone."""
        features = {
            "premium_discount": PremiumDiscountDTO(
                symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="premium_discount",
                zone="DISCOUNT", equilibrium=Decimal("80000.0"), range_low=Decimal("75000.0"), range_high=Decimal("85000.0"),
                current_price=Decimal("76500.0"), percentile=Decimal("15.0")
            ),
            "order_block": OrderBlockDTO(
                symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="order_block",
                is_bullish=True, bottom_price=Decimal("76000.0"), top_price=Decimal("77000.0"), volume_surge_ratio=Decimal("2.5"), mitigated=False
            ),
            "liquidity_sweep": LiquiditySweepDTO(
                symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="liquidity_sweep",
                is_buy_side=False, swept_level=Decimal("75500.0"), rejection_price=Decimal("76200.0")
            ),
        }
        dto = self.struct_agent.analyze("BTCUSDT", Timeframe.H1, features, current_price=Decimal("76500.0"), as_of=self.ts)
        self.assertEqual(dto.bias, DirectionalBias.BULLISH)
        self.assertEqual(dto.market_phase, MarketPhase.ACCUMULATION)
        self.assertEqual(dto.dealing_range_zone, "DISCOUNT")
        self.assertEqual(dto.active_order_blocks_count, 1)
        self.assertEqual(len(dto.sweeps_detected), 1)

    def test_market_structure_agent_distribution(self) -> None:
        """Verify MarketStructureAgent correctly identifies DISTRIBUTION phase in premium zone."""
        features = {
            "premium_discount": PremiumDiscountDTO(
                symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="premium_discount",
                zone="PREMIUM", equilibrium=Decimal("80000.0"), range_low=Decimal("75000.0"), range_high=Decimal("85000.0"),
                current_price=Decimal("84000.0"), percentile=Decimal("90.0")
            ),
            "order_block": OrderBlockDTO(
                symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="order_block",
                is_bullish=False, bottom_price=Decimal("83500.0"), top_price=Decimal("84500.0"), volume_surge_ratio=Decimal("2.0"), mitigated=False
            ),
            "liquidity_sweep": LiquiditySweepDTO(
                symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="liquidity_sweep",
                is_buy_side=True, swept_level=Decimal("84800.0"), rejection_price=Decimal("83900.0")
            ),
        }
        dto = self.struct_agent.analyze("BTCUSDT", Timeframe.H1, features, current_price=Decimal("84000.0"), as_of=self.ts)
        self.assertEqual(dto.bias, DirectionalBias.BEARISH)
        self.assertEqual(dto.market_phase, MarketPhase.DISTRIBUTION)
        self.assertEqual(dto.dealing_range_zone, "PREMIUM")

    def test_risk_context_agent_cross_discipline_conflict(self) -> None:
        """Verify RiskContextAgent detects severe conflict when Technical and Structure oppose each other."""
        tech_dto = TechnicalAssessmentDTO(
            bias=DirectionalBias.BULLISH, score=Decimal("50.0"), trend_regime="STRONG_BULLISH_TREND",
            volatility_regime="NORMAL", momentum_state="BULLISH_EXPANSION", signals=("EMA Bullish",),
            contributing_indicators=("EMA",), reasoning="Bullish tech"
        )
        struct_dto = MarketStructureAssessmentDTO(
            bias=DirectionalBias.BEARISH, score=Decimal("-60.0"), market_phase=MarketPhase.DISTRIBUTION,
            dealing_range_zone="PREMIUM", active_order_blocks_count=1, unmitigated_fvgs_count=0,
            sweeps_detected=(), key_levels=(), reasoning="Bearish structure"
        )
        features = {}
        risk_dto = self.risk_agent.analyze(
            "BTCUSDT", Timeframe.H1, features,
            technical_assessment=tech_dto, structure_assessment=struct_dto, as_of=self.ts
        )
        # Direct opposition should trigger conflict ratio >= 0.70 and EXTREME risk
        self.assertGreaterEqual(risk_dto.signal_conflict_ratio, Decimal("0.70"))
        self.assertEqual(risk_dto.risk_level, RiskLevel.EXTREME)
        self.assertFalse(risk_dto.is_tradeable_regime)

    def test_confidence_evidence_agent_synthesis(self) -> None:
        """Verify ConfidenceEvidenceAgent combines agreement, breadth, and conflict penalty."""
        tech_dto = TechnicalAssessmentDTO(
            bias=DirectionalBias.BULLISH, score=Decimal("50.0"), trend_regime="STRONG_BULLISH_TREND",
            volatility_regime="NORMAL", momentum_state="BULLISH_EXPANSION", signals=("EMA Bullish",),
            contributing_indicators=("EMA",), reasoning="Bullish tech"
        )
        struct_dto = MarketStructureAssessmentDTO(
            bias=DirectionalBias.BULLISH, score=Decimal("60.0"), market_phase=MarketPhase.ACCUMULATION,
            dealing_range_zone="DISCOUNT", active_order_blocks_count=1, unmitigated_fvgs_count=1,
            sweeps_detected=(), key_levels=(), reasoning="Bullish structure"
        )
        prob_dto = ProbabilityAssessmentDTO(
            directional_bias=DirectionalBias.BULLISH,
            breakdown=ProbabilityBreakdownDTO(bullish=Decimal("70.0"), bearish=Decimal("10.0"), neutral=Decimal("20.0")),
            total_score=Decimal("25.0"), confidence=Decimal("75.0"),
            top_positive_factors=("FVG",), top_negative_factors=(), reasoning="High probability"
        )
        risk_dto = RiskContextAssessmentDTO(
            risk_level=RiskLevel.LOW, volatility_state="NORMAL", signal_conflict_ratio=Decimal("0.0"),
            invalidation_risk="LOW", is_tradeable_regime=True, risk_factors=(), reasoning="Low risk"
        )
        features = {
            "ema_9": EMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_9", period=9, value=Decimal("580.0")),
            "fvg": FairValueGapDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="fvg", is_bullish=True, upper_bound=Decimal("580.0"), lower_bound=Decimal("575.0")),
            "order_block": OrderBlockDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="order_block", is_bullish=True, bottom_price=Decimal("570.0"), top_price=Decimal("575.0")),
            "vwap": VWAPDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="vwap", vwap=Decimal("575.0"), volume_sum=Decimal("1000.0")),
            "rsi_14": RSIDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="rsi_14", period=14, value=Decimal("30.0")),
            "bos": BreakOfStructureDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="bos", is_bullish=True, broken_level=Decimal("578.0")),
        }
        conf_dto = self.conf_agent.analyze(
            "SPY", Timeframe.H1, features, as_of=self.ts,
            technical_assessment=tech_dto, structure_assessment=struct_dto,
            probability_assessment=prob_dto, risk_assessment=risk_dto
        )
        # 100% agreement, 100% breadth, 0 penalty
        self.assertEqual(conf_dto.agent_agreement_ratio, Decimal("1.00"))
        self.assertEqual(conf_dto.evidence_breadth_score, Decimal("1.00"))
        self.assertEqual(conf_dto.conflict_penalty, Decimal("0.00"))
        self.assertGreaterEqual(conf_dto.composite_confidence, Decimal("80.00"))
        self.assertEqual(conf_dto.conviction_tier, ConvictionTier.VERY_HIGH)


class TestMultiAgentOrchestratorAggregation(unittest.TestCase):
    """Test full multi-agent orchestration end-to-end."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.orchestrator = MultiAgentOrchestrator(feature_store=self.store)
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_orchestrator_protocol_conformance(self) -> None:
        """Verify MultiAgentOrchestrator satisfies MarketOrchestrator protocol."""
        self.assertIsInstance(self.orchestrator, MarketOrchestrator)

    def test_full_aligned_bullish_assessment(self) -> None:
        """Verify end-to-end synthesis when all analytical disciplines align bullishly."""
        # Store technical indicators
        self.store.store_feature(EMADTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_9", period=9, value=Decimal("82000.0")))
        self.store.store_feature(EMADTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_21", period=21, value=Decimal("80000.0")))
        self.store.store_feature(MACDDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="macd", macd_line=Decimal("200.0"), signal_line=Decimal("50.0"), histogram=Decimal("150.0")))
        self.store.store_feature(VWAPDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="vwap", vwap=Decimal("80500.0"), volume_sum=Decimal("50000.0")))

        # Store market structure SMC features
        self.store.store_feature(FairValueGapDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="fvg", is_bullish=True, upper_bound=Decimal("81500.0"), lower_bound=Decimal("81000.0"), mitigated=False))
        self.store.store_feature(OrderBlockDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="order_block", is_bullish=True, bottom_price=Decimal("79500.0"), top_price=Decimal("80500.0"), volume_surge_ratio=Decimal("2.0"), mitigated=False))
        self.store.store_feature(LiquiditySweepDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="liquidity_sweep", is_buy_side=False, swept_level=Decimal("79000.0"), rejection_price=Decimal("79800.0")))
        self.store.store_feature(PremiumDiscountDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="premium_discount", zone="DISCOUNT", equilibrium=Decimal("81000.0"), range_low=Decimal("77000.0"), range_high=Decimal("85000.0"), current_price=Decimal("80800.0"), percentile=Decimal("45.0")))

        assessment = self.orchestrator.assess(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            as_of=self.ts,
            current_price=Decimal("82500.0"),
        )

        # Requirement 5 Field Assertions:
        self.assertEqual(assessment.symbol, "BTCUSDT")
        self.assertEqual(assessment.timeframe, Timeframe.H1)
        self.assertEqual(assessment.timestamp, self.ts)
        self.assertEqual(assessment.directional_bias, DirectionalBias.BULLISH)
        self.assertGreaterEqual(assessment.confidence, Decimal("60.00"))
        self.assertGreater(assessment.probability_breakdown.bullish, assessment.probability_breakdown.bearish)
        self.assertGreater(len(assessment.evidence_summary), 0)
        self.assertGreater(len(assessment.supporting_features), 0)
        self.assertTrue(assessment.is_actionable)
        self.assertIn("=== INSTITUTIONAL MARKET ASSESSMENT: BTCUSDT [1h] ===", assessment.final_reasoning)

    def test_full_aligned_bearish_assessment(self) -> None:
        """Verify end-to-end synthesis when all analytical disciplines align bearishly."""
        self.store.store_feature(EMADTO(symbol="ETHUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_9", period=9, value=Decimal("3000.0")))
        self.store.store_feature(EMADTO(symbol="ETHUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_21", period=21, value=Decimal("3100.0")))
        self.store.store_feature(MACDDTO(symbol="ETHUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="macd", macd_line=Decimal("-50.0"), signal_line=Decimal("-10.0"), histogram=Decimal("-40.0")))
        self.store.store_feature(FairValueGapDTO(symbol="ETHUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="fvg", is_bullish=False, upper_bound=Decimal("3150.0"), lower_bound=Decimal("3080.0"), mitigated=False))
        self.store.store_feature(OrderBlockDTO(symbol="ETHUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="order_block", is_bullish=False, bottom_price=Decimal("3120.0"), top_price=Decimal("3180.0"), volume_surge_ratio=Decimal("2.0"), mitigated=False))

        assessment = self.orchestrator.assess(
            symbol="ETHUSDT",
            timeframe=Timeframe.H1,
            as_of=self.ts,
            current_price=Decimal("2980.0"),
        )

        self.assertEqual(assessment.directional_bias, DirectionalBias.BEARISH)
        self.assertGreater(assessment.probability_breakdown.bearish, assessment.probability_breakdown.bullish)
        self.assertGreater(len(assessment.supporting_features), 0)

    def test_conflicting_disciplines_neutralization(self) -> None:
        """Verify orchestrator neutralizes bias when Technical is Bullish but Market Structure is Bearish."""
        # Bullish technicals
        self.store.store_feature(EMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_9", period=9, value=Decimal("590.0")))
        self.store.store_feature(EMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_21", period=21, value=Decimal("580.0")))
        # Bearish structure
        self.store.store_feature(ChangeOfCharacterDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="choch", is_bullish=False, pivot_level=Decimal("585.0")))
        self.store.store_feature(OrderBlockDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="order_block", is_bullish=False, bottom_price=Decimal("588.0"), top_price=Decimal("595.0"), volume_surge_ratio=Decimal("2.0"), mitigated=False))
        self.store.store_feature(PremiumDiscountDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="premium_discount", zone="PREMIUM", equilibrium=Decimal("570.0"), range_low=Decimal("550.0"), range_high=Decimal("595.0"), current_price=Decimal("592.0"), percentile=Decimal("93.0")))

        assessment = self.orchestrator.assess(
            symbol="SPY",
            timeframe=Timeframe.H1,
            as_of=self.ts,
            current_price=Decimal("592.0"),
        )

        # Conflict must neutralize the directional thesis and report conflict
        self.assertEqual(assessment.directional_bias, DirectionalBias.NEUTRAL)
        self.assertFalse(assessment.is_actionable)
        self.assertGreater(len(assessment.conflicting_features), 0)

    def test_empty_store_graceful_handling(self) -> None:
        """Verify empty FeatureStore produces clean NEUTRAL assessment without errors."""
        assessment = self.orchestrator.assess(
            symbol="GOLD",
            timeframe=Timeframe.D1,
            as_of=self.ts,
        )
        self.assertEqual(assessment.directional_bias, DirectionalBias.NEUTRAL)
        self.assertEqual(assessment.symbol, "GOLD")
        self.assertEqual(assessment.timeframe, Timeframe.D1)
        self.assertFalse(assessment.is_actionable)
        self.assertEqual(assessment.confidence_assessment.conviction_tier, ConvictionTier.VERY_LOW)


class TestPointInTimeCorrectness(unittest.TestCase):
    """Test strict point-in-time boundary enforcement."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.orchestrator = MultiAgentOrchestrator(feature_store=self.store)
        self.ts_past = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
        self.ts_future = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)

    def test_future_features_not_leaked(self) -> None:
        """Verify query as of ts_past does NOT incorporate features stored at ts_future."""
        # Store future bullish signals
        self.store.store_feature(
            BreakOfStructureDTO(
                symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts_future,
                feature_name="bos", is_bullish=True, broken_level=Decimal("85000.0")
            )
        )
        self.store.store_feature(
            OrderBlockDTO(
                symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts_future,
                feature_name="order_block", is_bullish=True, bottom_price=Decimal("83000.0"),
                top_price=Decimal("84500.0"), volume_surge_ratio=Decimal("2.0"), mitigated=False
            )
        )

        # Query past timestamp
        assessment_past = self.orchestrator.assess(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            as_of=self.ts_past,
        )
        self.assertEqual(assessment_past.directional_bias, DirectionalBias.NEUTRAL)

        # Query future timestamp
        assessment_future = self.orchestrator.assess(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            as_of=self.ts_future,
        )
        self.assertEqual(assessment_future.directional_bias, DirectionalBias.BULLISH)


class TestMemoizationAndLRUCache(unittest.TestCase):
    """Test bounded LRU memoization cache, capacity limits, and current_price discrimination."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.orchestrator = MultiAgentOrchestrator(feature_store=self.store, max_cache_size=3)
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_lru_capacity_and_eviction(self) -> None:
        """Verify cache never exceeds max_cache_size and evicts oldest items in O(1)."""
        self.assertEqual(self.orchestrator.max_cache_size, 3)
        self.assertEqual(self.orchestrator.cache_size, 0)

        # Query 1
        self.orchestrator.assess(symbol="BTCUSDT", timeframe=Timeframe.H1, as_of=self.ts)
        self.assertEqual(self.orchestrator.cache_size, 1)

        # Query 2
        self.orchestrator.assess(symbol="BTCUSDT", timeframe=Timeframe.H1, as_of=self.ts + timedelta(hours=1))
        self.assertEqual(self.orchestrator.cache_size, 2)

        # Query 3
        self.orchestrator.assess(symbol="BTCUSDT", timeframe=Timeframe.H1, as_of=self.ts + timedelta(hours=2))
        self.assertEqual(self.orchestrator.cache_size, 3)

        # Query 4 triggers eviction
        self.orchestrator.assess(symbol="BTCUSDT", timeframe=Timeframe.H1, as_of=self.ts + timedelta(hours=3))
        self.assertEqual(self.orchestrator.cache_size, 3)

    def test_cache_key_discriminates_current_price(self) -> None:
        """Verify different current_price values at identical timestamps produce distinct cache entries."""
        self.store.store_feature(
            VWAPDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="vwap", vwap=Decimal("80000.0"), volume_sum=Decimal("1000.0"))
        )

        dto_above = self.orchestrator.assess(
            symbol="BTCUSDT", timeframe=Timeframe.H1, as_of=self.ts, current_price=Decimal("85000.0")
        )
        dto_below = self.orchestrator.assess(
            symbol="BTCUSDT", timeframe=Timeframe.H1, as_of=self.ts, current_price=Decimal("75000.0")
        )

        self.assertEqual(self.orchestrator.cache_size, 2)
        self.assertNotEqual(dto_above.technical_assessment.score, dto_below.technical_assessment.score)

    def test_clear_memo_cache(self) -> None:
        """Verify clearing cache resets size to 0."""
        self.orchestrator.assess(symbol="ETHUSDT", timeframe=Timeframe.H1, as_of=self.ts)
        self.assertGreater(self.orchestrator.cache_size, 0)
        self.orchestrator.clear_memo_cache()
        self.assertEqual(self.orchestrator.cache_size, 0)


class TestThreadSafetyAndConcurrency(unittest.TestCase):
    """Test thread safety under concurrent multi-agent executions."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.orchestrator = MultiAgentOrchestrator(feature_store=self.store)
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        self.store.store_feature(
            EMADTO(symbol="SOLUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_9", period=9, value=Decimal("200.0"))
        )

    def test_concurrent_multi_agent_assessment(self) -> None:
        """Verify 10 concurrent threads can query assess() concurrently without race conditions."""
        errors: list[Exception] = []

        def worker(thread_id: int) -> None:
            try:
                for i in range(20):
                    assessment = self.orchestrator.assess(
                        symbol="SOLUSDT",
                        timeframe=Timeframe.H1,
                        as_of=self.ts,
                        current_price=Decimal(str(200 + thread_id + i)),
                    )
                    self.assertIsInstance(assessment, MarketAssessmentDTO)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent execution errors encountered: {errors}")


class TestPresentationAdapterDecoupling(unittest.TestCase):
    """Test LLMNarrativeAdapter presentation decoupling."""

    def test_narrative_formatting_without_llm(self) -> None:
        """Verify presentation adapter formats clean markdown briefing deterministically."""
        orchestrator = MultiAgentOrchestrator()
        ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        features = {
            "ema_9": EMADTO(symbol="AAPL", timeframe=Timeframe.D1, timestamp=ts, feature_name="ema_9", period=9, value=Decimal("230.0")),
            "ema_21": EMADTO(symbol="AAPL", timeframe=Timeframe.D1, timestamp=ts, feature_name="ema_21", period=21, value=Decimal("220.0")),
        }
        assessment = orchestrator.assess_from_features(
            symbol="AAPL", timeframe=Timeframe.D1, timestamp=ts, features=features, current_price=Decimal("235.0")
        )

        adapter = LLMNarrativeAdapter()
        briefing = adapter.format_morning_briefing(assessment)
        self.assertIn("# Institutional Desk Briefing: AAPL [1d]", briefing)
        self.assertIn("## 1. Probability Distribution", briefing)
        self.assertIn("## 2. Evidence Synthesis", briefing)
        self.assertIn("## 5. Discipline Details", briefing)


class TestValidationAndEdgeCases(unittest.TestCase):
    """Test validation errors, immutability, and edge case handling."""

    def setUp(self) -> None:
        self.orchestrator = MultiAgentOrchestrator()
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_invalid_symbol_rejection(self) -> None:
        """Verify empty or invalid symbol raises DTOValidationError."""
        from tradingagents.dataflows.exceptions import DTOValidationError
        with self.assertRaises(DTOValidationError):
            self.orchestrator.assess_from_features("", Timeframe.H1, self.ts, {})

    def test_invalid_timeframe_rejection(self) -> None:
        """Verify non-Timeframe type raises DTOValidationError."""
        from tradingagents.dataflows.exceptions import DTOValidationError
        with self.assertRaises(DTOValidationError):
            self.orchestrator.assess_from_features("BTCUSDT", "1h", self.ts, {})  # type: ignore

    def test_naive_datetime_rejection(self) -> None:
        """Verify timezone-naive datetime raises DTOValidationError."""
        from tradingagents.dataflows.exceptions import DTOValidationError
        naive_ts = datetime(2026, 11, 10, 12, 0)
        with self.assertRaises(DTOValidationError):
            self.orchestrator.assess_from_features("BTCUSDT", Timeframe.H1, naive_ts, {})

    def test_assess_without_store_raises_value_error(self) -> None:
        """Verify assess() without configured FeatureStore raises ValueError."""
        with self.assertRaises(ValueError):
            self.orchestrator.assess("BTCUSDT", Timeframe.H1)

    def test_probability_breakdown_invariant(self) -> None:
        """Verify ProbabilityBreakdownDTO enforces 100.00% sum."""
        from tradingagents.dataflows.exceptions import DTOValidationError
        with self.assertRaises(DTOValidationError):
            ProbabilityBreakdownDTO(bullish=Decimal("50.0"), bearish=Decimal("50.0"), neutral=Decimal("20.0"))

    def test_dto_immutability(self) -> None:
        """Verify MarketAssessmentDTO is frozen and cannot be mutated."""
        assessment = self.orchestrator.assess_from_features("SPY", Timeframe.D1, self.ts, {})
        with self.assertRaises(Exception):
            assessment.directional_bias = DirectionalBias.BULLISH  # type: ignore

    def test_llm_narrative_adapter_custom_callable(self) -> None:
        """Verify LLMNarrativeAdapter invokes custom callable and handles fallback."""
        assessment = self.orchestrator.assess_from_features("SPY", Timeframe.D1, self.ts, {})
        
        # Successful callable
        mock_callable = lambda text: f"LLM POLISHED: {text[:20]}"
        adapter = LLMNarrativeAdapter(llm_callable=mock_callable)
        output = adapter.format_morning_briefing(assessment)
        self.assertTrue(output.startswith("LLM POLISHED:"))

        # Failing callable falls back gracefully
        def failing_callable(text: str) -> str:
            raise RuntimeError("API timeout")
        failing_adapter = LLMNarrativeAdapter(llm_callable=failing_callable)
        fallback_output = failing_adapter.format_morning_briefing(assessment)
        self.assertIn("# Institutional Desk Briefing: SPY [1d]", fallback_output)


if __name__ == "__main__":
    unittest.main()
