"""Comprehensive unit test suite for Phase 9: Probability Engine."""

from __future__ import annotations

import sys
import types

if "dotenv" not in sys.modules:
    _d = types.ModuleType("dotenv")
    _d.find_dotenv = lambda *a, **k: ""
    _d.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = _d

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import threading
import unittest

from tradingagents.dataflows.contracts.features import FeatureComputer
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
    ProbabilityDTO,
    RSIDTO,
    SMADTO,
    VolumeProfileDTO,
    VWAPDTO,
)
from tradingagents.dataflows.dto.market_data import CandleDTO, OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.probability import (
    ConfidenceCalculator,
    DEFAULT_FEATURE_NAMES,
    ExplanationBuilder,
    ProbabilityComputer,
    ProbabilityEngine,
    ProbabilityScorer,
    ScoreNormalizer,
    ScoringConfig,
)
from tradingagents.dataflows.features.store import InMemoryFeatureStore


class TestProbabilityNormalizationAndInvariants(unittest.TestCase):
    """Test mathematical invariants, 100.00% sum guarantees, and DTO validations."""

    def setUp(self) -> None:
        self.normalizer = ScoreNormalizer()

    def test_exact_100_percent_sum_invariant(self) -> None:
        """Verify that Bullish + Bearish + Neutral == 100.00% across wide range of scores."""
        test_pairs = [
            (Decimal("0.0"), Decimal("0.0")),
            (Decimal("100.0"), Decimal("0.0")),
            (Decimal("0.0"), Decimal("100.0")),
            (Decimal("50.0"), Decimal("50.0")),
            (Decimal("12.345"), Decimal("67.891")),
            (Decimal("1.0"), Decimal("999.0")),
            (Decimal("999.0"), Decimal("1.0")),
            (Decimal("25.0"), Decimal("75.0")),
            (Decimal("33.33"), Decimal("33.33")),
            (Decimal("7.0"), Decimal("8.0")),
            (Decimal("0.01"), Decimal("0.02")),
        ]
        # Add generated combinations
        for b in range(0, 100, 11):
            for be in range(0, 100, 13):
                test_pairs.append((Decimal(str(b)), Decimal(str(be))))

        for bull, bear in test_pairs:
            p_bull, p_bear, p_neutral = self.normalizer.normalize(bull, bear)
            total = p_bull + p_bear + p_neutral
            self.assertEqual(
                total,
                Decimal("100.00"),
                f"Failed for bull={bull}, bear={bear}: {p_bull} + {p_bear} + {p_neutral} = {total}",
            )
            self.assertGreaterEqual(p_bull, Decimal("0.00"))
            self.assertGreaterEqual(p_bear, Decimal("0.00"))
            self.assertGreaterEqual(p_neutral, Decimal("0.00"))

    def test_negative_scores_rejected(self) -> None:
        """Verify that negative scores raise ValueError."""
        with self.assertRaises(ValueError):
            self.normalizer.normalize(Decimal("-5.0"), Decimal("10.0"))
        with self.assertRaises(ValueError):
            self.normalizer.normalize(Decimal("10.0"), Decimal("-5.0"))

    def test_probability_dto_invariant_enforcement(self) -> None:
        """Verify ProbabilityDTO post_init rejects probabilities not summing to 100.00%."""
        now = datetime.now(timezone.utc)
        # Sum is 99.00 -> should fail
        with self.assertRaises(DTOValidationError):
            ProbabilityDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=now,
                feature_name="probability",
                bullish_probability=Decimal("50.00"),
                bearish_probability=Decimal("40.00"),
                neutral_probability=Decimal("9.00"),
                confidence=Decimal("80.00"),
                total_score=Decimal("10.00"),
                bullish_score=Decimal("50.00"),
                bearish_score=Decimal("40.00"),
            )

        # Sum is 101.00 -> should fail
        with self.assertRaises(DTOValidationError):
            ProbabilityDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=now,
                feature_name="probability",
                bullish_probability=Decimal("50.00"),
                bearish_probability=Decimal("50.00"),
                neutral_probability=Decimal("1.00"),
                confidence=Decimal("80.00"),
                total_score=Decimal("10.00"),
                bullish_score=Decimal("50.00"),
                bearish_score=Decimal("40.00"),
            )

    def test_probability_dto_bounds(self) -> None:
        """Verify ProbabilityDTO post_init rejects probabilities outside [0, 100]."""
        now = datetime.now(timezone.utc)
        with self.assertRaises(DTOValidationError):
            ProbabilityDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=now,
                feature_name="probability",
                bullish_probability=Decimal("-5.00"),
                bearish_probability=Decimal("50.00"),
                neutral_probability=Decimal("55.00"),
                confidence=Decimal("80.00"),
                total_score=Decimal("0.0"),
                bullish_score=Decimal("0.0"),
                bearish_score=Decimal("0.0"),
            )

    def test_probability_dto_immutability(self) -> None:
        """Verify ProbabilityDTO is frozen and cannot be mutated."""
        now = datetime.now(timezone.utc)
        dto = ProbabilityDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=now,
            feature_name="probability",
            bullish_probability=Decimal("60.00"),
            bearish_probability=Decimal("10.00"),
            neutral_probability=Decimal("30.00"),
            confidence=Decimal("75.00"),
            total_score=Decimal("50.00"),
            bullish_score=Decimal("60.00"),
            bearish_score=Decimal("10.00"),
        )
        with self.assertRaises(Exception):
            dto.bullish_probability = Decimal("70.00")  # type: ignore


class TestDirectionalScoring(unittest.TestCase):
    """Test pure bullish, pure bearish, sideways, and conflicting market states."""

    def setUp(self) -> None:
        self.ts = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        self.engine = ProbabilityEngine()

    def test_pure_bullish_trend(self) -> None:
        """Verify that aligned bullish indicators and structure produce high bullish probability and confidence."""
        features: dict[str, BaseFeatureDTO] = {
            "bos": BreakOfStructureDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="bos",
                is_bullish=True,
                broken_level=Decimal("65000.0"),
                displacement_volume=Decimal("1200.0"),
            ),
            "choch": ChangeOfCharacterDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="choch",
                is_bullish=True,
                pivot_level=Decimal("64200.0"),
            ),
            "order_block": OrderBlockDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="order_block",
                is_bullish=True,
                top_price=Decimal("64500.0"),
                bottom_price=Decimal("64000.0"),
                volume_surge_ratio=Decimal("2.1"),
                mitigated=False,
            ),
            "premium_discount": PremiumDiscountDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="premium_discount",
                range_high=Decimal("66000.0"),
                range_low=Decimal("62000.0"),
                equilibrium=Decimal("64000.0"),
                current_price=Decimal("63000.0"),
                zone="DISCOUNT",
                percentile=Decimal("25.0"),
            ),
            "liquidity_sweep": LiquiditySweepDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="liquidity_sweep",
                is_buy_side=False,  # Sell-side sweep = Bullish reversal
                swept_level=Decimal("62500.0"),
                rejection_price=Decimal("63000.0"),
            ),
            "fvg": FairValueGapDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="fvg",
                is_bullish=True,
                upper_bound=Decimal("64800.0"),
                lower_bound=Decimal("64300.0"),
                mitigated=False,
            ),
            "ema_9": EMADTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="ema_9",
                period=9,
                value=Decimal("64600.0"),
            ),
            "ema_21": EMADTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="ema_21",
                period=21,
                value=Decimal("64100.0"),
            ),
            "macd": MACDDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="macd",
                macd_line=Decimal("150.0"),
                signal_line=Decimal("50.0"),
                histogram=Decimal("100.0"),
            ),
            "rsi_14": RSIDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="rsi_14",
                period=14,
                value=Decimal("32.0"),  # Oversold recovery
            ),
            "vwap": VWAPDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="vwap",
                vwap=Decimal("63500.0"),
                volume_sum=Decimal("50000.0"),
            ),
        }

        dto = self.engine.compute_from_features(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            features=features,
            current_price=Decimal("64700.0"),
        )

        self.assertGreater(dto.bullish_probability, Decimal("70.00"))
        self.assertEqual(dto.bearish_probability, Decimal("0.00"))
        self.assertEqual(dto.bullish_probability + dto.bearish_probability + dto.neutral_probability, Decimal("100.00"))
        self.assertGreater(dto.confidence, Decimal("80.00"))
        self.assertGreater(dto.total_score, Decimal("50.0"))
        self.assertGreater(len(dto.positive_factors), 5)
        self.assertEqual(len(dto.negative_factors), 0)

    def test_pure_bearish_trend(self) -> None:
        """Verify that aligned bearish indicators and structure produce high bearish probability and confidence."""
        features: dict[str, BaseFeatureDTO] = {
            "bos": BreakOfStructureDTO(
                symbol="ETHUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="bos",
                is_bullish=False,
                broken_level=Decimal("3100.0"),
                displacement_volume=Decimal("500.0"),
            ),
            "choch": ChangeOfCharacterDTO(
                symbol="ETHUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="choch",
                is_bullish=False,
                pivot_level=Decimal("3250.0"),
            ),
            "order_block": OrderBlockDTO(
                symbol="ETHUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="order_block",
                is_bullish=False,
                top_price=Decimal("3300.0"),
                bottom_price=Decimal("3200.0"),
                volume_surge_ratio=Decimal("1.8"),
                mitigated=False,
            ),
            "premium_discount": PremiumDiscountDTO(
                symbol="ETHUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="premium_discount",
                range_high=Decimal("3400.0"),
                range_low=Decimal("3000.0"),
                equilibrium=Decimal("3200.0"),
                current_price=Decimal("3350.0"),
                zone="PREMIUM",
                percentile=Decimal("87.5"),
            ),
            "liquidity_sweep": LiquiditySweepDTO(
                symbol="ETHUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="liquidity_sweep",
                is_buy_side=True,  # Buy-side sweep = Bearish reversal
                swept_level=Decimal("3410.0"),
                rejection_price=Decimal("3350.0"),
            ),
            "fvg": FairValueGapDTO(
                symbol="ETHUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="fvg",
                is_bullish=False,
                upper_bound=Decimal("3280.0"),
                lower_bound=Decimal("3220.0"),
                mitigated=False,
            ),
            "ema_9": EMADTO(
                symbol="ETHUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="ema_9",
                period=9,
                value=Decimal("3150.0"),
            ),
            "ema_21": EMADTO(
                symbol="ETHUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="ema_21",
                period=21,
                value=Decimal("3220.0"),
            ),
            "macd": MACDDTO(
                symbol="ETHUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="macd",
                macd_line=Decimal("-25.0"),
                signal_line=Decimal("-10.0"),
                histogram=Decimal("-15.0"),
            ),
            "rsi_14": RSIDTO(
                symbol="ETHUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="rsi_14",
                period=14,
                value=Decimal("68.0"),  # Overbought rejection
            ),
            "vwap": VWAPDTO(
                symbol="ETHUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="vwap",
                vwap=Decimal("3250.0"),
                volume_sum=Decimal("15000.0"),
            ),
        }

        dto = self.engine.compute_from_features(
            symbol="ETHUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            features=features,
            current_price=Decimal("3120.0"),
        )

        self.assertGreater(dto.bearish_probability, Decimal("70.00"))
        self.assertEqual(dto.bullish_probability, Decimal("0.00"))
        self.assertEqual(dto.bullish_probability + dto.bearish_probability + dto.neutral_probability, Decimal("100.00"))
        self.assertGreater(dto.confidence, Decimal("80.00"))
        self.assertLess(dto.total_score, Decimal("-50.0"))
        self.assertGreater(len(dto.negative_factors), 5)
        self.assertEqual(len(dto.positive_factors), 0)

    def test_sideways_and_equilibrium_market(self) -> None:
        """Verify that equilibrium and mitigated features produce dominant neutral probability."""
        features: dict[str, BaseFeatureDTO] = {
            "premium_discount": PremiumDiscountDTO(
                symbol="SPY",
                timeframe=Timeframe.D1,
                timestamp=self.ts,
                feature_name="premium_discount",
                range_high=Decimal("500.0"),
                range_low=Decimal("480.0"),
                equilibrium=Decimal("490.0"),
                current_price=Decimal("490.0"),
                zone="EQUILIBRIUM",
                percentile=Decimal("50.0"),
            ),
            "order_block": OrderBlockDTO(
                symbol="SPY",
                timeframe=Timeframe.D1,
                timestamp=self.ts,
                feature_name="order_block",
                is_bullish=True,
                top_price=Decimal("492.0"),
                bottom_price=Decimal("488.0"),
                volume_surge_ratio=Decimal("1.3"),
                mitigated=True,  # Mitigated OB has 0 score
            ),
            "rsi_14": RSIDTO(
                symbol="SPY",
                timeframe=Timeframe.D1,
                timestamp=self.ts,
                feature_name="rsi_14",
                period=14,
                value=Decimal("50.0"),  # Dead neutral
            ),
        }

        dto = self.engine.compute_from_features(
            symbol="SPY",
            timeframe=Timeframe.D1,
            timestamp=self.ts,
            features=features,
            current_price=Decimal("490.0"),
        )

        self.assertEqual(dto.neutral_probability, Decimal("100.00"))
        self.assertEqual(dto.bullish_probability, Decimal("0.00"))
        self.assertEqual(dto.bearish_probability, Decimal("0.00"))
        self.assertEqual(dto.confidence, Decimal("0.00"))

    def test_conflicting_signals_dampening(self) -> None:
        """Verify that conflicting signals transfer weight to neutral and depress confidence."""
        features: dict[str, BaseFeatureDTO] = {
            # Bullish BOS (+12)
            "bos": BreakOfStructureDTO(
                symbol="EURUSD",
                timeframe=Timeframe.M15,
                timestamp=self.ts,
                feature_name="bos",
                is_bullish=True,
                broken_level=Decimal("1.0850"),
                displacement_volume=Decimal("0.0"),
            ),
            # Bearish CHoCH (-10)
            "choch": ChangeOfCharacterDTO(
                symbol="EURUSD",
                timeframe=Timeframe.M15,
                timestamp=self.ts,
                feature_name="choch",
                is_bullish=False,
                pivot_level=Decimal("1.0820"),
            ),
            # Bearish Order Block (-8)
            "order_block": OrderBlockDTO(
                symbol="EURUSD",
                timeframe=Timeframe.M15,
                timestamp=self.ts,
                feature_name="order_block",
                is_bullish=False,
                top_price=Decimal("1.0890"),
                bottom_price=Decimal("1.0860"),
                volume_surge_ratio=Decimal("1.5"),
                mitigated=False,
            ),
            # Bullish EMA (+5)
            "ema_9": EMADTO(
                symbol="EURUSD",
                timeframe=Timeframe.M15,
                timestamp=self.ts,
                feature_name="ema_9",
                period=9,
                value=Decimal("1.0860"),
            ),
            "ema_21": EMADTO(
                symbol="EURUSD",
                timeframe=Timeframe.M15,
                timestamp=self.ts,
                feature_name="ema_21",
                period=21,
                value=Decimal("1.0840"),
            ),
        }

        dto = self.engine.compute_from_features(
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            timestamp=self.ts,
            features=features,
            current_price=Decimal("1.0855"),
        )

        # Bullish points = 12 + 5 = 17, Bearish points = 10 + 8 = 18. Conflict = 17.
        # Neutral should expand significantly, and confidence should be depressed.
        self.assertGreater(dto.neutral_probability, Decimal("40.00"))
        self.assertLess(dto.confidence, Decimal("50.00"))
        self.assertEqual(dto.bullish_probability + dto.bearish_probability + dto.neutral_probability, Decimal("100.00"))


class TestMissingFeaturesAndDegradedData(unittest.TestCase):
    """Test resilience against empty FeatureStore and sparse/missing features."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.engine = ProbabilityEngine(feature_store=self.store)
        self.ts = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)

    def test_empty_feature_store_handling(self) -> None:
        """Verify that empty FeatureStore returns 100% neutral and 0% confidence gracefully."""
        dto = self.engine.compute_probability(
            symbol="XAUUSD",
            timeframe=Timeframe.H1,
            as_of=self.ts,
        )

        self.assertEqual(dto.bullish_probability, Decimal("0.00"))
        self.assertEqual(dto.bearish_probability, Decimal("0.00"))
        self.assertEqual(dto.neutral_probability, Decimal("100.00"))
        self.assertEqual(dto.confidence, Decimal("0.00"))
        self.assertEqual(dto.total_score, Decimal("0.00"))
        self.assertEqual(len(dto.positive_factors), 0)
        self.assertEqual(len(dto.negative_factors), 0)

    def test_missing_indicators_structure_only(self) -> None:
        """Verify engine functions cleanly when only market structure is present."""
        self.store.store_feature(
            BreakOfStructureDTO(
                symbol="QQQ",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="bos",
                is_bullish=True,
                broken_level=Decimal("490.0"),
                displacement_volume=Decimal("10000.0"),
            )
        )
        self.store.store_feature(
            OrderBlockDTO(
                symbol="QQQ",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="order_block",
                is_bullish=True,
                top_price=Decimal("488.0"),
                bottom_price=Decimal("485.0"),
                volume_surge_ratio=Decimal("1.9"),
                mitigated=False,
            )
        )

        dto = self.engine.compute_probability(
            symbol="QQQ",
            timeframe=Timeframe.H1,
            as_of=self.ts,
        )

        self.assertGreater(dto.bullish_probability, Decimal("50.00"))
        self.assertEqual(dto.bearish_probability, Decimal("0.00"))
        self.assertEqual(dto.bullish_probability + dto.bearish_probability + dto.neutral_probability, Decimal("100.00"))
        # Partial evidence coverage means confidence is moderate rather than 100%
        self.assertLess(dto.confidence, Decimal("85.00"))

    def test_missing_structure_indicators_only(self) -> None:
        """Verify engine functions cleanly when only technical indicators are present."""
        self.store.store_feature(
            EMADTO(
                symbol="SPY",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="ema_9",
                period=9,
                value=Decimal("580.0"),
            )
        )
        self.store.store_feature(
            EMADTO(
                symbol="SPY",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="ema_21",
                period=21,
                value=Decimal("575.0"),
            )
        )
        self.store.store_feature(
            MACDDTO(
                symbol="SPY",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="macd",
                macd_line=Decimal("2.5"),
                signal_line=Decimal("1.0"),
                histogram=Decimal("1.5"),
            )
        )

        dto = self.engine.compute_probability(
            symbol="SPY",
            timeframe=Timeframe.H1,
            as_of=self.ts,
        )

        self.assertGreater(dto.bullish_probability, Decimal("25.00"))
        self.assertEqual(dto.bearish_probability, Decimal("0.00"))
        self.assertEqual(dto.bullish_probability + dto.bearish_probability + dto.neutral_probability, Decimal("100.00"))

    def test_single_indicator_only(self) -> None:
        """Verify that even a single indicator computes without error."""
        self.store.store_feature(
            RSIDTO(
                symbol="EURUSD",
                timeframe=Timeframe.M5,
                timestamp=self.ts,
                feature_name="rsi_14",
                period=14,
                value=Decimal("25.0"),  # Oversold
            )
        )

        dto = self.engine.compute_probability(
            symbol="EURUSD",
            timeframe=Timeframe.M5,
            as_of=self.ts,
        )

        self.assertGreater(dto.bullish_probability, Decimal("15.00"))
        self.assertEqual(dto.bullish_probability + dto.bearish_probability + dto.neutral_probability, Decimal("100.00"))
        self.assertLess(dto.confidence, Decimal("40.00"))  # Very low confidence due to single feature


class TestExplainabilityAndReasoning(unittest.TestCase):
    """Test human-readable narrative and feature breakdown formatting."""

    def test_explanation_formatting(self) -> None:
        builder = ExplanationBuilder()
        contribs = [
            FeatureContributionDTO("bos", Decimal("12.0"), Decimal("12.0"), "BULLISH", "Bullish BOS detected"),
            FeatureContributionDTO("order_block", Decimal("8.0"), Decimal("8.0"), "BULLISH", "Bullish OB active"),
            FeatureContributionDTO("premium_discount", Decimal("6.0"), Decimal("-6.0"), "BEARISH", "Premium Zone"),
        ]
        reasoning = builder.build_reasoning(
            bullish_prob=Decimal("78.0"),
            bearish_prob=Decimal("12.0"),
            neutral_prob=Decimal("10.0"),
            confidence=Decimal("86.0"),
            total_score=Decimal("14.0"),
            bullish_score=Decimal("20.0"),
            bearish_score=Decimal("6.0"),
            positive_factors=["✓ Bullish BOS detected", "✓ Bullish OB active"],
            negative_factors=["✗ Premium Zone resistance"],
            contributions=contribs,
        )

        self.assertIn("Bullish Probability: 78.0%", reasoning)
        self.assertIn("Confidence: 86.0%", reasoning)
        self.assertIn("✓ Bullish BOS detected", reasoning)
        self.assertIn("✗ Premium Zone resistance", reasoning)
        self.assertIn("[BOS] BULLISH: +12.0", reasoning)
        self.assertIn("[PREMIUM_DISCOUNT] BEARISH: -6.0", reasoning)


class TestProbabilityEngineOrchestration(unittest.TestCase):
    """Test FeatureStore integration, memoization, point-in-time correctness, and thread-safety."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.engine = ProbabilityEngine(feature_store=self.store)

    def test_feature_store_persistence(self) -> None:
        """Verify ProbabilityDTO is stored into FeatureStore and can be retrieved."""
        now = datetime.now(timezone.utc)
        self.store.store_feature(
            BreakOfStructureDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=now,
                feature_name="bos",
                is_bullish=True,
                broken_level=Decimal("70000.0"),
                displacement_volume=Decimal("5000.0"),
            )
        )

        dto = self.engine.compute_probability(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            as_of=now,
            store_results=True,
        )

        # Retrieve from store
        retrieved = self.store.get_latest("BTCUSDT", Timeframe.H1, "probability")
        self.assertIsInstance(retrieved, ProbabilityDTO)
        self.assertEqual(retrieved.bullish_probability, dto.bullish_probability)
        self.assertEqual(retrieved.confidence, dto.confidence)

    def test_point_in_time_as_of_lookahead_prevention(self) -> None:
        """Verify point-in-time lookup strictly ignores features with timestamp > as_of."""
        t1 = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 11, 9, 11, 0, tzinfo=timezone.utc)

        # Bullish BOS at t1
        self.store.store_feature(
            BreakOfStructureDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=t1,
                feature_name="bos",
                is_bullish=True,
                broken_level=Decimal("70000.0"),
                displacement_volume=Decimal("1000.0"),
            )
        )

        # Bearish CHoCH at t2
        self.store.store_feature(
            ChangeOfCharacterDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=t2,
                feature_name="choch",
                is_bullish=False,
                pivot_level=Decimal("69000.0"),
            )
        )

        # Query as of t1: CHoCH at t2 must NOT be visible!
        dto_t1 = self.engine.compute_probability(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            as_of=t1,
        )
        self.assertEqual(dto_t1.bearish_score, Decimal("0.0"))
        self.assertGreater(dto_t1.bullish_score, Decimal("0.0"))

        # Query as of t2: both features should now be visible
        self.engine.clear_memo_cache()
        dto_t2 = self.engine.compute_probability(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            as_of=t2,
        )
        self.assertGreater(dto_t2.bearish_score, Decimal("0.0"))

    def test_memoization_cache(self) -> None:
        """Verify identical queries return memoized instance without recalculation."""
        now = datetime.now(timezone.utc)
        self.store.store_feature(
            BreakOfStructureDTO(
                symbol="ETHUSDT",
                timeframe=Timeframe.H1,
                timestamp=now,
                feature_name="bos",
                is_bullish=True,
                broken_level=Decimal("3000.0"),
                displacement_volume=Decimal("200.0"),
            )
        )

        res1 = self.engine.compute_probability("ETHUSDT", Timeframe.H1, as_of=now)
        res2 = self.engine.compute_probability("ETHUSDT", Timeframe.H1, as_of=now)
        self.assertIs(res1, res2)

        self.engine.clear_memo_cache()
        res3 = self.engine.compute_probability("ETHUSDT", Timeframe.H1, as_of=now)
        self.assertEqual(res1, res3)

    def test_deterministic_reproducibility(self) -> None:
        """Verify that 50 repeated computations produce identical results."""
        now = datetime.now(timezone.utc)
        self.store.store_feature(
            BreakOfStructureDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=now,
                feature_name="bos",
                is_bullish=True,
                broken_level=Decimal("65000.0"),
                displacement_volume=Decimal("100.0"),
            )
        )
        self.store.store_feature(
            EMADTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=now,
                feature_name="ema_9",
                period=9,
                value=Decimal("65100.0"),
            )
        )
        self.store.store_feature(
            EMADTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=now,
                feature_name="ema_21",
                period=21,
                value=Decimal("64900.0"),
            )
        )

        self.engine.clear_memo_cache()
        baseline = self.engine.compute_probability("BTCUSDT", Timeframe.H1, as_of=now)

        for _ in range(50):
            self.engine.clear_memo_cache()
            current = self.engine.compute_probability("BTCUSDT", Timeframe.H1, as_of=now)
            self.assertEqual(baseline, current)

    def test_thread_safety_concurrent_execution(self) -> None:
        """Verify multi-threaded concurrent execution across 10 threads without race conditions."""
        now = datetime.now(timezone.utc)
        self.store.store_feature(
            BreakOfStructureDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=now,
                feature_name="bos",
                is_bullish=True,
                broken_level=Decimal("60000.0"),
                displacement_volume=Decimal("100.0"),
            )
        )

        errors: list[Exception] = []

        def worker(thread_id: int) -> None:
            try:
                for i in range(25):
                    # Compute with slight timestamp shifts
                    t = now + timedelta(seconds=i)
                    self.engine.compute_probability(
                        symbol="BTCUSDT",
                        timeframe=Timeframe.H1,
                        as_of=t,
                        store_results=True,
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread errors encountered: {errors}")


class TestProbabilityComputerProtocol(unittest.TestCase):
    """Test ProbabilityComputer conformance with FeatureComputer protocol."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.computer = ProbabilityComputer(feature_store=self.store)

    def test_feature_computer_protocol_conformance(self) -> None:
        """Verify runtime protocol check and properties."""
        self.assertTrue(isinstance(self.computer, FeatureComputer))
        self.assertEqual(self.computer.feature_name, "probability")

    def test_computer_execution(self) -> None:
        """Verify compute() returns a sequence of ProbabilityDTO."""
        now = datetime.now(timezone.utc)
        candles = [
            CandleDTO(
                timestamp=now - timedelta(minutes=5),
                open=Decimal("100.0"),
                high=Decimal("105.0"),
                low=Decimal("99.0"),
                close=Decimal("104.0"),
                volume=Decimal("1000.0"),
            ),
            CandleDTO(
                timestamp=now,
                open=Decimal("104.0"),
                high=Decimal("108.0"),
                low=Decimal("103.0"),
                close=Decimal("107.0"),
                volume=Decimal("1500.0"),
            ),
        ]
        series = OHLCVSeriesDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.M5,
            candles=tuple(candles),
        )

        results = self.computer.compute("BTCUSDT", Timeframe.M5, series)
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], ProbabilityDTO)
        self.assertEqual(results[0].symbol, "BTCUSDT")
        self.assertEqual(results[0].timeframe, Timeframe.M5)
        self.assertEqual(
            results[0].bullish_probability + results[0].bearish_probability + results[0].neutral_probability,
            Decimal("100.00"),
        )



class TestPhase91EventTimeDecay(unittest.TestCase):
    """Test exponential time-decay for event-based signals (Phase 9.1)."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.engine = ProbabilityEngine(feature_store=self.store)
        self.base_ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_fresh_event_zero_decay(self) -> None:
        """Verify that an event occurring on the current bar has full weight (decay = 1.0)."""
        bos = BreakOfStructureDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.base_ts,
            feature_name="bos",
            is_bullish=True,
            broken_level=Decimal("80000.0"),
        )
        dto = self.engine.compute_from_features(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.base_ts,
            features={"bos": bos},
        )
        self.assertEqual(dto.bullish_score, Decimal("4.00"))
        contrib = next(c for c in dto.contributing_features if c.feature_name == "bos")
        self.assertEqual(contrib.weight, Decimal("4.00"))
        self.assertNotIn("decayed", contrib.description)

    def test_half_life_decay_5_bars(self) -> None:
        """Verify that an event 5 bars old has half-life decay (50% weight)."""
        event_ts = self.base_ts - timedelta(hours=5)
        bos = BreakOfStructureDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=event_ts,
            feature_name="bos",
            is_bullish=True,
            broken_level=Decimal("80000.0"),
        )
        dto = self.engine.compute_from_features(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.base_ts,
            features={"bos": bos},
        )
        self.assertEqual(dto.bullish_score, Decimal("2.00"))
        contrib = next(c for c in dto.contributing_features if c.feature_name == "bos")
        self.assertEqual(contrib.weight, Decimal("2.00"))
        self.assertIn("5 bars ago", contrib.description)
        self.assertIn("decayed to 50%", contrib.description)

    def test_two_half_lives_decay_10_bars(self) -> None:
        """Verify that an event 10 bars old decays to 25% weight."""
        event_ts = self.base_ts - timedelta(hours=10)
        choch = ChangeOfCharacterDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=event_ts,
            feature_name="choch",
            is_bullish=False,
            pivot_level=Decimal("82000.0"),
        )
        dto = self.engine.compute_from_features(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.base_ts,
            features={"choch": choch},
        )
        # CHoCH weight = 4.0 * 0.25 = 1.00
        self.assertEqual(dto.bearish_score, Decimal("1.00"))
        contrib = next(c for c in dto.contributing_features if c.feature_name == "choch")
        self.assertEqual(contrib.weight, Decimal("1.00"))
        self.assertIn("10 bars ago", contrib.description)
        self.assertIn("decayed to 25%", contrib.description)

    def test_max_decay_expiration_30_bars(self) -> None:
        """Verify that an event 30+ bars old completely decays to zero weight."""
        event_ts = self.base_ts - timedelta(hours=35)
        sweep = LiquiditySweepDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=event_ts,
            feature_name="liquidity_sweep",
            is_buy_side=False,
            swept_level=Decimal("79000.0"),
            rejection_price=Decimal("79200.0"),
        )
        dto = self.engine.compute_from_features(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.base_ts,
            features={"liquidity_sweep": sweep},
        )
        self.assertEqual(dto.bullish_score, Decimal("0.00"))
        contrib = next(c for c in dto.contributing_features if c.feature_name == "liquidity_sweep")
        self.assertEqual(contrib.weight, Decimal("0.00"))
        self.assertIn("Decayed/expired", contrib.description)

    def test_persistent_state_features_do_not_decay(self) -> None:
        """Verify that state-based features (FVG, OrderBlock) do NOT undergo event time-decay."""
        old_ts = self.base_ts - timedelta(hours=15)
        fvg = FairValueGapDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=old_ts,
            feature_name="fvg",
            is_bullish=True,
            upper_bound=Decimal("81000.0"),
            lower_bound=Decimal("80500.0"),
            mitigated=False,
        )
        dto = self.engine.compute_from_features(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.base_ts,
            features={"fvg": fvg},
        )
        # FVG weight is full 12.0 regardless of timestamp
        self.assertEqual(dto.bullish_score, Decimal("12.00"))
        dto = self.engine.compute_from_features(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.base_ts,
            features={"fvg": fvg},
        )
        # FVG weight is full 12.0 regardless of timestamp
        self.assertEqual(dto.bullish_score, Decimal("12.00"))


class TestPhase91RebalancedWeights(unittest.TestCase):
    """Test rebalanced institutional weights (Phase 9.1)."""

    def setUp(self) -> None:
        self.engine = ProbabilityEngine()
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_rebalanced_weights_hierarchy(self) -> None:
        """Verify exact institutional weight values."""
        cfg = self.engine.config
        self.assertEqual(cfg.weight_fvg, Decimal("12.0"))
        self.assertEqual(cfg.weight_order_block, Decimal("12.0"))
        self.assertEqual(cfg.weight_liquidity_sweep, Decimal("7.0"))
        self.assertEqual(cfg.weight_premium_discount, Decimal("6.0"))
        self.assertEqual(cfg.weight_bos, Decimal("4.0"))
        self.assertEqual(cfg.weight_choch, Decimal("4.0"))
        self.assertEqual(cfg.weight_rsi, Decimal("5.0"))
        self.assertEqual(cfg.weight_bollinger, Decimal("4.0"))
        self.assertEqual(cfg.weight_vwap, Decimal("4.0"))
        self.assertEqual(cfg.weight_ema_alignment, Decimal("3.0"))
        self.assertEqual(cfg.weight_macd, Decimal("3.0"))
        self.assertEqual(cfg.weight_sma_alignment, Decimal("2.0"))


class TestPhase91ConfidenceInflationMitigation(unittest.TestCase):
    """Test orthogonal indicator clustering and confidence inflation mitigation (Phase 9.1)."""

    def setUp(self) -> None:
        self.engine = ProbabilityEngine()
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_collinear_trend_indicators_clustered(self) -> None:
        """Verify that multiple collinear trend indicators (EMA, SMA, MACD) only count as 1 cluster."""
        # Collinear cluster: EMA alignment, SMA alignment, MACD (all Trend cluster)
        collinear_features = {
            "ema_9": EMADTO(
                symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_9", period=9, value=Decimal("580.0")
            ),
            "ema_21": EMADTO(
                symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_21", period=21, value=Decimal("570.0")
            ),
            "sma_20": SMADTO(
                symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="sma_20", period=20, value=Decimal("575.0")
            ),
            "sma_50": SMADTO(
                symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="sma_50", period=50, value=Decimal("565.0")
            ),
            "macd": MACDDTO(
                symbol="SPY",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="macd",
                macd_line=Decimal("3.0"),
                signal_line=Decimal("1.0"),
                histogram=Decimal("2.0"),
            ),
        }

        # Orthogonal cluster: EMA alignment (Trend), VWAP (Volume), RSI (Oscillator)
        orthogonal_features = {
            "ema_9": EMADTO(
                symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_9", period=9, value=Decimal("580.0")
            ),
            "ema_21": EMADTO(
                symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="ema_21", period=21, value=Decimal("570.0")
            ),
            "vwap": VWAPDTO(
                symbol="SPY",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="vwap",
                vwap=Decimal("570.0"),
                volume_sum=Decimal("100000.0"),
            ),
            "rsi_14": RSIDTO(
                symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="rsi_14", period=14, value=Decimal("25.0")
            ),
        }

        dto_collinear = self.engine.compute_from_features(
            symbol="SPY",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            features=collinear_features,
            current_price=Decimal("585.0"),
        )
        dto_orthogonal = self.engine.compute_from_features(
            symbol="SPY",
            timeframe=Timeframe.H1,
            timestamp=self.ts,
            features=orthogonal_features,
            current_price=Decimal("585.0"),
        )

        # Collinear indicators only get 1 cluster (trend factor = 0.40)
        # Orthogonal indicators get 3 clusters (trend factor = 1.00)
        # Therefore, orthogonal confirmation MUST produce higher confidence than duplicated collinear indicators
        self.assertGreater(dto_orthogonal.confidence, dto_collinear.confidence)


class TestPhase91BoundedLRUMemoization(unittest.TestCase):
    """Test bounded LRU memoization cache and current_price cache key inclusion (Phase 9.1)."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        config = ScoringConfig(max_cache_size=3)
        self.engine = ProbabilityEngine(feature_store=self.store, config=config)
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_cache_bounds_and_lru_eviction(self) -> None:
        """Verify that cache does not exceed max_cache_size and evicts oldest items."""
        self.assertEqual(self.engine.max_cache_size, 3)
        self.assertEqual(self.engine.cache_size, 0)

        # Populate store with a feature
        self.store.store_feature(
            RSIDTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.ts, feature_name="rsi_14", period=14, value=Decimal("25.0"))
        )

        # 1st entry
        ts1 = self.ts
        self.engine.compute_probability(symbol="SPY", timeframe=Timeframe.H1, as_of=ts1)
        self.assertEqual(self.engine.cache_size, 1)

        # 2nd entry
        ts2 = self.ts + timedelta(hours=1)
        self.engine.compute_probability(symbol="SPY", timeframe=Timeframe.H1, as_of=ts2)
        self.assertEqual(self.engine.cache_size, 2)

        # 3rd entry
        ts3 = self.ts + timedelta(hours=2)
        self.engine.compute_probability(symbol="SPY", timeframe=Timeframe.H1, as_of=ts3)
        self.assertEqual(self.engine.cache_size, 3)

        # 4th entry - should trigger LRU eviction of ts1
        ts4 = self.ts + timedelta(hours=3)
        self.engine.compute_probability(symbol="SPY", timeframe=Timeframe.H1, as_of=ts4)
        self.assertEqual(self.engine.cache_size, 3)

    def test_cache_key_includes_current_price(self) -> None:
        """Verify that varying current_price produces distinct cache entries and correct evaluations."""
        # Store VWAP at 150.0
        self.store.store_feature(
            VWAPDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.ts,
                feature_name="vwap",
                vwap=Decimal("150.0"),
                volume_sum=Decimal("10000.0"),
            )
        )

        # Call with price above VWAP (180.0) -> Bullish bias
        dto_above = self.engine.compute_probability(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            as_of=self.ts,
            current_price=Decimal("180.0"),
        )

        # Call with price below VWAP (120.0) -> Bearish bias
        dto_below = self.engine.compute_probability(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            as_of=self.ts,
            current_price=Decimal("120.0"),
        )

        # They should both be in the cache as distinct entries
        self.assertEqual(self.engine.cache_size, 2)
        self.assertGreater(dto_above.bullish_score, dto_above.bearish_score)
        self.assertGreater(dto_below.bearish_score, dto_below.bullish_score)


if __name__ == "__main__":
    unittest.main()
