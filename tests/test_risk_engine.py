"""Comprehensive unit, scenario, and regression test suite for Phase 11: Risk Engine."""

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

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import (
    ATRDTO,
    BollingerBandsDTO,
    BreakOfStructureDTO,
    ChangeOfCharacterDTO,
    EMADTO,
    FairValueGapDTO,
    LiquidityPoolDTO,
    LiquiditySweepDTO,
    MACDDTO,
    OrderBlockDTO,
    PremiumDiscountDTO,
    RSIDTO,
    SMADTO,
    VWAPDTO,
)
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.store import InMemoryFeatureStore
from tradingagents.orchestration.dto import (
    MarketStructureAssessmentDTO,
    TechnicalAssessmentDTO,
)
from tradingagents.orchestration.enums import DirectionalBias, MarketPhase
from tradingagents.risk.config import RiskConfig
from tradingagents.risk.dto import RiskAssessmentDTO, RiskSubMetricsDTO
from tradingagents.risk.engine import RiskComputer, RiskEngine
from tradingagents.risk.enums import (
    DrawdownRisk,
    InvalidationRisk,
    PositionSuitability,
    RiskLevel,
    VolatilityRegime,
)


class TestRiskEngineScenarios(unittest.TestCase):
    """Test deterministic risk evaluation across market scenarios."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.engine = RiskEngine(feature_store=self.store)
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_orderly_low_risk_scenario(self) -> None:
        """Verify that aligned moving averages, normal volatility, and favorable dealing range yield LOW risk."""
        features = {
            "ema_9": EMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_9", period=9, value=Decimal("585.0")),
            "ema_21": EMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_21", period=21, value=Decimal("580.0")),
            "sma_20": SMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="sma_20", period=20, value=Decimal("578.0")),
            "sma_50": SMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="sma_50", period=50, value=Decimal("570.0")),
            "bollinger": BollingerBandsDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="bollinger", middle_band=Decimal("580.0"), upper_band=Decimal("590.0"), lower_band=Decimal("570.0")),
            "atr_14": ATRDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="atr_14", period=14, value=Decimal("5.0")),  # ~0.8% of price
            "premium_discount": PremiumDiscountDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="premium_discount", zone="DISCOUNT", equilibrium=Decimal("582.0"), range_low=Decimal("560.0"), range_high=Decimal("600.0"), current_price=Decimal("575.0"), percentile=Decimal("37.5")),
        }

        dto = self.engine.compute_from_features(
            symbol="SPY",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            features=features,
            current_price=Decimal("585.0"),
            directional_intent="BULLISH",
        )

        self.assertEqual(dto.risk_level, RiskLevel.LOW)
        self.assertEqual(dto.volatility_regime, VolatilityRegime.NORMAL)
        self.assertTrue(dto.regime_tradeable)
        self.assertEqual(dto.invalidation_risk, InvalidationRisk.LOW)
        self.assertEqual(dto.position_suitability, PositionSuitability.FAVORABLE)
        self.assertLess(dto.risk_score, Decimal("30.00"))
        self.assertIn("=== INSTITUTIONAL RISK ASSESSMENT: SPY [1h] ===", dto.explanatory_reasoning)

    def test_explosive_volatility_scenario(self) -> None:
        """Verify that wide Bollinger bandwidth (>15%) and extreme ATR (>5%) trigger EXPLOSIVE volatility."""
        features = {
            "bollinger": BollingerBandsDTO(
                symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="bollinger",
                middle_band=Decimal("80000.0"), upper_band=Decimal("95000.0"), lower_band=Decimal("65000.0")  # Bandwidth = 30000 / 80000 = 37.5%
            ),
            "atr_14": ATRDTO(
                symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="atr_14",
                period=14, value=Decimal("5500.0")  # 5500 / 80000 = 6.8% of price
            ),
        }

        dto = self.engine.compute_from_features(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            features=features,
            current_price=Decimal("80000.0"),
        )

        self.assertEqual(dto.volatility_regime, VolatilityRegime.EXPLOSIVE)
        self.assertGreaterEqual(dto.sub_metrics.volatility_score, Decimal("85.00"))
        self.assertEqual(dto.drawdown_risk, DrawdownRisk.SEVERE)

    def test_severe_cross_discipline_conflict_scenario(self) -> None:
        """Verify that Technical Bullish vs Market Structure Bearish triggers high conflict and non-tradeable regime."""
        tech_assessment = TechnicalAssessmentDTO(
            bias=DirectionalBias.BULLISH, score=Decimal("70.0"), trend_regime="STRONG_BULLISH_TREND",
            volatility_regime="NORMAL", momentum_state="BULLISH_EXPANSION", signals=("EMA alignment",),
            contributing_indicators=("EMA",), reasoning="Bullish tech"
        )
        struct_assessment = MarketStructureAssessmentDTO(
            bias=DirectionalBias.BEARISH, score=Decimal("-80.0"), market_phase=MarketPhase.DISTRIBUTION,
            dealing_range_zone="PREMIUM", active_order_blocks_count=2, unmitigated_fvgs_count=1,
            sweeps_detected=(), key_levels=(), reasoning="Bearish structure"
        )

        # Mock an upstream object with these assessments
        class MockUpstream:
            def __init__(self, t: Any, s: Any) -> None:
                self.technical_assessment = t
                self.structure_assessment = s

        mock_upstream = MockUpstream(tech_assessment, struct_assessment)

        # Features with opposing signals
        features = {
            "ema_9": EMADTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_9", period=9, value=Decimal("82000.0")),
            "ema_21": EMADTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_21", period=21, value=Decimal("80000.0")),
            "choch": ChangeOfCharacterDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="choch", is_bullish=False, pivot_level=Decimal("81500.0")),
            "order_block": OrderBlockDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="order_block", is_bullish=False, bottom_price=Decimal("82500.0"), top_price=Decimal("83500.0"), volume_surge_ratio=Decimal("2.0"), mitigated=False),
        }

        dto = self.engine.compute_from_features(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            features=features,
            upstream_assessment=mock_upstream,
        )

        self.assertGreaterEqual(dto.signal_conflict_ratio, Decimal("0.70"))
        self.assertEqual(dto.risk_level, RiskLevel.EXTREME)
        self.assertFalse(dto.regime_tradeable)
        self.assertEqual(dto.position_suitability, PositionSuitability.UNSUITABLE_CASH_ONLY)

    def test_overextended_dealing_range_invalidation_risk(self) -> None:
        """Verify buying in deep PREMIUM (95th percentile) triggers CRITICAL invalidation risk."""
        features = {
            "premium_discount": PremiumDiscountDTO(
                symbol="ETHUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="premium_discount",
                zone="PREMIUM", equilibrium=Decimal("3000.0"), range_low=Decimal("2700.0"), range_high=Decimal("3300.0"),
                current_price=Decimal("3270.0"), percentile=Decimal("95.0")
            ),
        }

        dto = self.engine.compute_from_features(
            symbol="ETHUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            features=features,
            directional_intent="BULLISH",
        )

        self.assertEqual(dto.invalidation_risk, InvalidationRisk.CRITICAL)
        self.assertGreaterEqual(dto.sub_metrics.dealing_range_score, Decimal("85.00"))
        self.assertIn("Overextended Dealing Range", "; ".join(dto.risk_factors))

    def test_liquidity_reversal_exhaustion_scenario(self) -> None:
        """Verify extreme RSI overbought (>75) and bearish sweep trigger elevated reversal score."""
        features = {
            "rsi_14": RSIDTO(symbol="SOLUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="rsi_14", period=14, value=Decimal("78.5")),
            "liquidity_sweep": LiquiditySweepDTO(symbol="SOLUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="liquidity_sweep", is_buy_side=True, swept_level=Decimal("220.0"), rejection_price=Decimal("215.0")),
        }

        dto = self.engine.compute_from_features(
            symbol="SOLUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            features=features,
            current_price=Decimal("216.0"),
        )

        self.assertGreaterEqual(dto.sub_metrics.liquidity_reversal_score, Decimal("60.00"))
        self.assertIn("Severe Reversal Exhaustion", "; ".join(dto.risk_factors))

    def test_consolidation_chop_detection(self) -> None:
        """Verify price oscillating at dealing range equilibrium with unaligned MAs triggers chop risk."""
        features = {
            "ema_9": EMADTO(symbol="EURUSD", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_9", period=9, value=Decimal("1.0850")),
            "ema_21": EMADTO(symbol="EURUSD", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_21", period=21, value=Decimal("1.0852")),
            "sma_20": SMADTO(symbol="EURUSD", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="sma_20", period=20, value=Decimal("1.0851")),
            "sma_50": SMADTO(symbol="EURUSD", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="sma_50", period=50, value=Decimal("1.0849")),
            "premium_discount": PremiumDiscountDTO(symbol="EURUSD", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="premium_discount", zone="EQUILIBRIUM", equilibrium=Decimal("1.0850"), range_low=Decimal("1.0750"), range_high=Decimal("1.0950"), current_price=Decimal("1.0850"), percentile=Decimal("50.0")),
        }

        dto = self.engine.compute_from_features(
            symbol="EURUSD",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            features=features,
            current_price=Decimal("1.0850"),
        )

        self.assertGreaterEqual(dto.sub_metrics.chop_score, Decimal("50.00"))
        self.assertIn("Consolidation Chop", "; ".join(dto.risk_factors))


class TestPointInTimeCorrectness(unittest.TestCase):
    """Test point-in-time isolation in RiskEngine."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.engine = RiskEngine(feature_store=self.store)
        self.ts_past = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
        self.ts_future = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)

    def test_future_features_not_leaked(self) -> None:
        """Verify query at ts_past does NOT incorporate future explosive volatility."""
        self.store.store_feature(
            BollingerBandsDTO(
                symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts_future,
                feature_name="bollinger", middle_band=Decimal("80000.0"), upper_band=Decimal("95000.0"), lower_band=Decimal("65000.0")
            )
        )

        assessment_past = self.engine.assess_risk(symbol="BTCUSDT", timeframe=Timeframe.H1, as_of=self.ts_past)
        self.assertEqual(assessment_past.volatility_regime, VolatilityRegime.NORMAL)

        assessment_future = self.engine.assess_risk(symbol="BTCUSDT", timeframe=Timeframe.H1, as_of=self.ts_future)
        self.assertEqual(assessment_future.volatility_regime, VolatilityRegime.EXPLOSIVE)


class TestBoundedLRUMemoization(unittest.TestCase):
    """Test bounded LRU memoization cache in RiskEngine."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        config = RiskConfig(max_cache_size=3)
        self.engine = RiskEngine(feature_store=self.store, config=config)
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_lru_capacity_and_eviction(self) -> None:
        """Verify cache capacity is bounded and evicts oldest items."""
        self.assertEqual(self.engine.max_cache_size, 3)
        self.assertEqual(self.engine.cache_size, 0)

        # 1st entry
        self.engine.assess_risk(symbol="SPY", timeframe=Timeframe.H1, as_of=self.ts)
        self.assertEqual(self.engine.cache_size, 1)

        # 2nd entry
        self.engine.assess_risk(symbol="SPY", timeframe=Timeframe.H1, as_of=self.ts + timedelta(hours=1))
        self.assertEqual(self.engine.cache_size, 2)

        # 3rd entry
        self.engine.assess_risk(symbol="SPY", timeframe=Timeframe.H1, as_of=self.ts + timedelta(hours=2))
        self.assertEqual(self.engine.cache_size, 3)

        # 4th entry triggers eviction
        self.engine.assess_risk(symbol="SPY", timeframe=Timeframe.H1, as_of=self.ts + timedelta(hours=3))
        self.assertEqual(self.engine.cache_size, 3)

    def test_cache_key_discriminates_current_price_and_intent(self) -> None:
        """Verify differing price or intent values yield distinct cache entries."""
        self.store.store_feature(
            PremiumDiscountDTO(
                symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="premium_discount",
                zone="DISCOUNT", equilibrium=Decimal("80000.0"), range_low=Decimal("70000.0"), range_high=Decimal("90000.0"),
                current_price=Decimal("75000.0"), percentile=Decimal("25.0")
            )
        )

        dto_bull = self.engine.assess_risk(
            symbol="BTCUSDT", timeframe=Timeframe.H1, as_of=self.ts, current_price=Decimal("75000.0"), directional_intent="BULLISH"
        )
        dto_bear = self.engine.assess_risk(
            symbol="BTCUSDT", timeframe=Timeframe.H1, as_of=self.ts, current_price=Decimal("75000.0"), directional_intent="BEARISH"
        )

        self.assertEqual(self.engine.cache_size, 2)
        self.assertNotEqual(dto_bull.invalidation_risk, dto_bear.invalidation_risk)

    def test_clear_memo_cache(self) -> None:
        """Verify clear_memo_cache resets cache size to 0."""
        self.engine.assess_risk(symbol="BTCUSDT", timeframe=Timeframe.H1, as_of=self.ts)
        self.assertGreater(self.engine.cache_size, 0)
        self.engine.clear_memo_cache()
        self.assertEqual(self.engine.cache_size, 0)


class TestThreadSafetyAndConcurrency(unittest.TestCase):
    """Test multi-threaded concurrent risk assessment."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.engine = RiskEngine(feature_store=self.store)
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        self.store.store_feature(
            EMADTO(symbol="ETHUSDT", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_9", period=9, value=Decimal("3000.0"))
        )

    def test_concurrent_risk_assessment(self) -> None:
        """Verify 10 concurrent threads can query assess_risk() without race conditions."""
        errors: list[Exception] = []

        def worker(thread_id: int) -> None:
            try:
                for i in range(20):
                    assessment = self.engine.assess_risk(
                        symbol="ETHUSDT",
                        timeframe=Timeframe.H1,
                        as_of=self.ts,
                        current_price=Decimal(str(3000 + thread_id + i)),
                    )
                    self.assertIsInstance(assessment, RiskAssessmentDTO)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent execution errors: {errors}")


class TestFeatureStoreIntegrationAndProtocol(unittest.TestCase):
    """Test FeatureStore persistence and FeatureComputer protocol implementation."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.engine = RiskEngine(feature_store=self.store)
        self.computer = RiskComputer(self.engine)
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_computer_conforms_to_feature_computer_protocol(self) -> None:
        """Verify RiskComputer implements FeatureComputer."""
        self.assertIsInstance(self.computer, FeatureComputer)
        self.assertEqual(self.computer.feature_name, "risk_assessment")

    def test_store_results_persists_dto(self) -> None:
        """Verify assess_risk stores RiskAssessmentDTO back into FeatureStore."""
        dto = self.engine.assess_risk(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            as_of=self.ts,
            store_results=True,
        )
        stored = self.store.get_latest("BTCUSDT", Timeframe.H1, "risk_assessment")
        self.assertIsNotNone(stored)
        self.assertIsInstance(stored, RiskAssessmentDTO)
        self.assertEqual(stored.symbol, "BTCUSDT")
        self.assertEqual(stored.timeframe, Timeframe.H1)
        self.assertEqual(stored.risk_score, dto.risk_score)

    def test_empty_store_graceful_handling(self) -> None:
        """Verify empty FeatureStore produces clean low-risk default without crashing."""
        dto = self.engine.assess_risk(
            symbol="UNKNOWN",
            timeframe=Timeframe.M15,
            as_of=self.ts,
        )
        self.assertEqual(dto.symbol, "UNKNOWN")
        self.assertEqual(dto.timeframe, Timeframe.M15)
        self.assertEqual(dto.volatility_regime, VolatilityRegime.NORMAL)
        self.assertTrue(dto.regime_tradeable)


class TestValidationAndInvariants(unittest.TestCase):
    """Test validation errors and immutability."""

    def setUp(self) -> None:
        self.engine = RiskEngine()
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_invalid_symbol_rejection(self) -> None:
        with self.assertRaises(DTOValidationError):
            self.engine.compute_from_features("", Timeframe.H1, self.ts, {})

    def test_invalid_timeframe_rejection(self) -> None:
        with self.assertRaises(DTOValidationError):
            self.engine.compute_from_features("BTCUSDT", "1h", self.ts, {})  # type: ignore

    def test_naive_datetime_rejection(self) -> None:
        naive_ts = datetime(2026, 11, 10, 12, 0)
        with self.assertRaises(DTOValidationError):
            self.engine.compute_from_features("BTCUSDT", Timeframe.H1, naive_ts, {})

    def test_dto_immutability(self) -> None:
        dto = self.engine.compute_from_features("BTCUSDT", Timeframe.H1, self.ts, {})
        with self.assertRaises(Exception):
            dto.risk_level = RiskLevel.EXTREME  # type: ignore


if __name__ == "__main__":
    unittest.main()
