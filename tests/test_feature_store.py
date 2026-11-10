"""Unit tests for FeatureStore, FeatureComputer contracts, and Feature DTOs."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import threading
import time
import unittest

from tradingagents.dataflows.contracts.features import FeatureComputer, FeatureStore
from tradingagents.dataflows.dto.features import (
    ATRDTO,
    BaseFeatureDTO,
    BollingerBandsDTO,
    BreakOfStructureDTO,
    ChangeOfCharacterDTO,
    EMADTO,
    FairValueGapDTO,
    FundingMetricsDTO,
    LiquiditySweepDTO,
    MACDDTO,
    OpenInterestMetricsDTO,
    OrderBlockDTO,
    RSIDTO,
    SMADTO,
    VolumeProfileDTO,
    VWAPDTO,
)
from tradingagents.dataflows.dto.market_data import CandleDTO, OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.store import InMemoryFeatureStore


class TestFeatureDTOs(unittest.TestCase):
    """Test validation and immutability of Feature DTOs."""

    def setUp(self) -> None:
        self.now = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)

    def test_immutability(self) -> None:
        ema = EMADTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.now,
            feature_name="EMA_21",
            period=21,
            value=Decimal("85000.50"),
        )
        with self.assertRaises(FrozenInstanceError):
            ema.value = Decimal("86000.00")  # type: ignore

    def test_timezone_validation(self) -> None:
        naive_dt = datetime(2026, 11, 9, 12, 0, 0)
        with self.assertRaises(DTOValidationError):
            EMADTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=naive_dt,
                feature_name="EMA_21",
                period=21,
                value=Decimal("85000.50"),
            )

    def test_rsi_bounds_validation(self) -> None:
        # Valid bounds
        rsi_valid = RSIDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.now,
            feature_name="RSI_14",
            period=14,
            value=Decimal("65.5"),
        )
        self.assertEqual(rsi_valid.value, Decimal("65.5"))

        # Negative RSI
        with self.assertRaises(DTOValidationError):
            RSIDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.now,
                feature_name="RSI_14",
                period=14,
                value=Decimal("-1.0"),
            )

        # RSI > 100
        with self.assertRaises(DTOValidationError):
            RSIDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.now,
                feature_name="RSI_14",
                period=14,
                value=Decimal("101.0"),
            )

    def test_bollinger_bands_invariants(self) -> None:
        # Valid: lower <= middle <= upper
        bb = BollingerBandsDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.now,
            feature_name="BB_20_2",
            middle_band=Decimal("85000.00"),
            upper_band=Decimal("86000.00"),
            lower_band=Decimal("84000.00"),
            bandwidth_bps=Decimal("235.29"),
        )
        self.assertGreater(bb.upper_band, bb.middle_band)

        # Inverted bands (lower > upper)
        with self.assertRaises(DTOValidationError):
            BollingerBandsDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.now,
                feature_name="BB_20_2",
                middle_band=Decimal("85000.00"),
                upper_band=Decimal("83000.00"),
                lower_band=Decimal("86000.00"),
                bandwidth_bps=Decimal("10.0"),
            )

    def test_volume_profile_invariants(self) -> None:
        vp = VolumeProfileDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.D1,
            timestamp=self.now,
            feature_name="VP_DAILY",
            poc=Decimal("85200.00"),
            vah=Decimal("86000.00"),
            val=Decimal("84500.00"),
            total_volume=Decimal("15000.00"),
        )
        self.assertTrue(vp.val <= vp.poc <= vp.vah)

        # POC outside value area
        with self.assertRaises(DTOValidationError):
            VolumeProfileDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.D1,
                timestamp=self.now,
                feature_name="VP_DAILY",
                poc=Decimal("87000.00"),  # > vah
                vah=Decimal("86000.00"),
                val=Decimal("84500.00"),
                total_volume=Decimal("15000.00"),
            )

    def test_smc_dtos(self) -> None:
        # Fair Value Gap
        fvg = FairValueGapDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.now,
            feature_name="FVG_BULLISH",
            is_bullish=True,
            upper_bound=Decimal("85500.00"),
            lower_bound=Decimal("85100.00"),
        )
        self.assertTrue(fvg.is_bullish)

        with self.assertRaises(DTOValidationError):
            FairValueGapDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.now,
                feature_name="FVG_INVALID",
                is_bullish=True,
                upper_bound=Decimal("85000.00"),
                lower_bound=Decimal("85500.00"),  # lower > upper
            )

        # Break of Structure
        bos = BreakOfStructureDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H4,
            timestamp=self.now,
            feature_name="BOS_BULLISH",
            is_bullish=True,
            broken_level=Decimal("86000.00"),
            displacement_volume=Decimal("1250.5"),
        )
        self.assertEqual(bos.broken_level, Decimal("86000.00"))

        # Order Block
        ob = OrderBlockDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.now,
            feature_name="OB_BULLISH",
            is_bullish=True,
            top_price=Decimal("84200.00"),
            bottom_price=Decimal("83900.00"),
            volume_surge_ratio=Decimal("2.4"),
        )
        self.assertTrue(ob.top_price >= ob.bottom_price)


class TestInMemoryFeatureStore(unittest.TestCase):
    """Test InMemoryFeatureStore core functionality."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore(default_ttl_seconds=300)
        self.t0 = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
        self.t1 = datetime(2026, 11, 9, 11, 0, 0, tzinfo=timezone.utc)
        self.t2 = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
        self.t3 = datetime(2026, 11, 9, 13, 0, 0, tzinfo=timezone.utc)

    def test_protocol_conformance(self) -> None:
        self.assertIsInstance(self.store, FeatureStore)

    def test_store_and_get_latest(self) -> None:
        ema1 = EMADTO("BTCUSDT", Timeframe.H1, self.t0, "EMA_21", 21, Decimal("80000"))
        ema2 = EMADTO("BTCUSDT", Timeframe.H1, self.t1, "EMA_21", 21, Decimal("81000"))

        self.store.store_feature(ema1)
        latest = self.store.get_latest("BTCUSDT", Timeframe.H1, "EMA_21")
        self.assertEqual(latest, ema1)

        self.store.store_feature(ema2)
        latest = self.store.get_latest("BTCUSDT", Timeframe.H1, "EMA_21")
        self.assertEqual(latest, ema2)
        self.assertEqual(latest.value, Decimal("81000"))  # type: ignore

    def test_point_in_time_lookup_no_future_leakage(self) -> None:
        """Verify strict point-in-time correctness: as_of must never return future observations."""
        ema0 = EMADTO("BTCUSDT", Timeframe.H1, self.t0, "EMA_21", 21, Decimal("80000"))
        ema1 = EMADTO("BTCUSDT", Timeframe.H1, self.t1, "EMA_21", 21, Decimal("81000"))
        ema2 = EMADTO("BTCUSDT", Timeframe.H1, self.t2, "EMA_21", 21, Decimal("82000"))

        self.store.store_features([ema0, ema1, ema2])

        # Query before any data existed -> None (zero future leakage)
        past_query = datetime(2026, 11, 9, 9, 59, 59, tzinfo=timezone.utc)
        self.assertIsNone(self.store.get_as_of("BTCUSDT", Timeframe.H1, "EMA_21", as_of=past_query))

        # Query exactly at t0 -> ema0
        self.assertEqual(self.store.get_as_of("BTCUSDT", Timeframe.H1, "EMA_21", as_of=self.t0), ema0)

        # Query between t0 and t1 (10:30) -> ema0
        mid1 = datetime(2026, 11, 9, 10, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(self.store.get_as_of("BTCUSDT", Timeframe.H1, "EMA_21", as_of=mid1), ema0)

        # Query at t1 -> ema1
        self.assertEqual(self.store.get_as_of("BTCUSDT", Timeframe.H1, "EMA_21", as_of=self.t1), ema1)

        # Query between t1 and t2 (11:45) -> ema1
        mid2 = datetime(2026, 11, 9, 11, 45, 0, tzinfo=timezone.utc)
        self.assertEqual(self.store.get_as_of("BTCUSDT", Timeframe.H1, "EMA_21", as_of=mid2), ema1)

        # Query far in future -> ema2 (latest observation)
        far_future = datetime(2026, 11, 10, 0, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(self.store.get_as_of("BTCUSDT", Timeframe.H1, "EMA_21", as_of=far_future), ema2)

    def test_idempotent_overwrite_same_timestamp(self) -> None:
        """Storing updated feature with same timestamp replaces observation rather than duplicating."""
        ema_initial = EMADTO("BTCUSDT", Timeframe.H1, self.t1, "EMA_21", 21, Decimal("81000"))
        ema_revised = EMADTO("BTCUSDT", Timeframe.H1, self.t1, "EMA_21", 21, Decimal("81500"))

        self.store.store_feature(ema_initial)
        self.assertEqual(self.store.total_observations(), 1)

        self.store.store_feature(ema_revised)
        self.assertEqual(self.store.total_observations(), 1)  # No duplicate
        latest = self.store.get_latest("BTCUSDT", Timeframe.H1, "EMA_21")
        self.assertEqual(latest, ema_revised)

    def test_get_batch(self) -> None:
        ema = EMADTO("BTCUSDT", Timeframe.H1, self.t1, "EMA_21", 21, Decimal("81000"))
        rsi = RSIDTO("BTCUSDT", Timeframe.H1, self.t1, "RSI_14", 14, Decimal("58.2"))
        self.store.store_features([ema, rsi])

        # Batch latest
        batch = self.store.get_batch("BTCUSDT", Timeframe.H1, ["EMA_21", "RSI_14", "NON_EXISTENT"])
        self.assertEqual(len(batch), 2)
        self.assertEqual(batch["EMA_21"], ema)
        self.assertEqual(batch["RSI_14"], rsi)
        self.assertNotIn("NON_EXISTENT", batch)

        # Batch as_of
        as_of = datetime(2026, 11, 9, 11, 30, 0, tzinfo=timezone.utc)
        batch_as_of = self.store.get_batch("BTCUSDT", Timeframe.H1, ["EMA_21", "RSI_14"], as_of=as_of)
        self.assertEqual(len(batch_as_of), 2)
        self.assertEqual(batch_as_of["EMA_21"], ema)

    def test_cache_invalidation(self) -> None:
        ema_btc_h1 = EMADTO("BTCUSDT", Timeframe.H1, self.t1, "EMA_21", 21, Decimal("81000"))
        rsi_btc_h1 = RSIDTO("BTCUSDT", Timeframe.H1, self.t1, "RSI_14", 14, Decimal("58.2"))
        ema_eth_h1 = EMADTO("ETHUSDT", Timeframe.H1, self.t1, "EMA_21", 21, Decimal("3100"))
        ema_btc_d1 = EMADTO("BTCUSDT", Timeframe.D1, self.t1, "EMA_21", 21, Decimal("80000"))

        self.store.store_features([ema_btc_h1, rsi_btc_h1, ema_eth_h1, ema_btc_d1])
        self.assertEqual(self.store.count_series(), 4)

        # Invalidate specific feature across symbols/timeframes
        count = self.store.invalidate(feature_name="RSI_14")
        self.assertEqual(count, 1)
        self.assertIsNone(self.store.get_latest("BTCUSDT", Timeframe.H1, "RSI_14"))
        self.assertIsNotNone(self.store.get_latest("BTCUSDT", Timeframe.H1, "EMA_21"))

        # Invalidate by timeframe
        count = self.store.invalidate(timeframe=Timeframe.D1)
        self.assertEqual(count, 1)
        self.assertIsNone(self.store.get_latest("BTCUSDT", Timeframe.D1, "EMA_21"))

        # Invalidate all remaining
        count = self.store.invalidate()
        self.assertEqual(count, 2)
        self.assertEqual(self.store.count_series(), 0)

    def test_ttl_expiration_and_purge(self) -> None:
        # Store with 0.05s TTL
        short_ttl_store = InMemoryFeatureStore()
        ema = EMADTO("BTCUSDT", Timeframe.H1, self.t1, "EMA_21", 21, Decimal("81000"))
        short_ttl_store.store_feature(ema, ttl_seconds=0.05)

        # Immediately available
        self.assertIsNotNone(short_ttl_store.get_latest("BTCUSDT", Timeframe.H1, "EMA_21"))

        # Sleep past TTL
        time.sleep(0.08)

        # Passive eviction on get
        self.assertIsNone(short_ttl_store.get_latest("BTCUSDT", Timeframe.H1, "EMA_21"))
        self.assertIsNone(short_ttl_store.get_as_of("BTCUSDT", Timeframe.H1, "EMA_21", as_of=self.t2))

        # Active purge
        short_ttl_store.store_feature(ema, ttl_seconds=0.02)
        time.sleep(0.04)
        purged = short_ttl_store.purge_expired()
        self.assertGreaterEqual(purged, 1)
        self.assertEqual(short_ttl_store.count_series(), 0)

    def test_max_history_bound(self) -> None:
        """Verify that series history does not grow unbounded beyond max_history."""
        bounded_store = InMemoryFeatureStore(max_history_per_series=5)
        for i in range(10):
            ts = self.t0 + timedelta(hours=i)
            feat = EMADTO("BTCUSDT", Timeframe.H1, ts, "EMA_21", 21, Decimal(f"{80000 + i}"))
            bounded_store.store_feature(feat)

        self.assertEqual(bounded_store.total_observations(), 5)
        # Oldest observations (i < 5) should have been pruned
        self.assertIsNone(bounded_store.get_as_of("BTCUSDT", Timeframe.H1, "EMA_21", as_of=self.t0))
        # Newest observation (i=9) is present
        latest = bounded_store.get_latest("BTCUSDT", Timeframe.H1, "EMA_21")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.value, Decimal("80009"))  # type: ignore

    def test_thread_safety_concurrency(self) -> None:
        """Verify thread-safe reading and writing under concurrent load."""
        store = InMemoryFeatureStore()
        num_threads = 8
        items_per_thread = 50
        errors: list[Exception] = []

        def writer_task(thread_id: int) -> None:
            try:
                for i in range(items_per_thread):
                    ts = self.t0 + timedelta(seconds=thread_id * 1000 + i)
                    feat = EMADTO("BTCUSDT", Timeframe.H1, ts, f"EMA_{thread_id}", 21, Decimal("80000"))
                    store.store_feature(feat)
            except Exception as e:
                errors.append(e)

        def reader_task(thread_id: int) -> None:
            try:
                for _ in range(items_per_thread):
                    store.get_latest("BTCUSDT", Timeframe.H1, f"EMA_{thread_id}")
                    store.get_as_of("BTCUSDT", Timeframe.H1, f"EMA_{thread_id}", as_of=self.t3)
            except Exception as e:
                errors.append(e)

        threads: list[threading.Thread] = []
        for tid in range(num_threads):
            threads.append(threading.Thread(target=writer_task, args=(tid,)))
            threads.append(threading.Thread(target=reader_task, args=(tid,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertGreaterEqual(store.count_series(), 1)


class MockSMAComputer:
    """Mock deterministic FeatureComputer for protocol testing."""

    def __init__(self, period: int = 3) -> None:
        self._period = period

    @property
    def feature_name(self) -> str:
        return f"SMA_{self._period}"

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> list[SMADTO]:
        if len(data.candles) < self._period:
            return []

        results: list[SMADTO] = []
        for i in range(self._period, len(data.candles) + 1):
            window = data.candles[i - self._period : i]
            avg_close = sum(c.close for c in window) / Decimal(self._period)
            results.append(
                SMADTO(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=window[-1].timestamp,
                    feature_name=self.feature_name,
                    period=self._period,
                    value=avg_close,
                )
            )
        return results


class TestFeatureComputerProtocol(unittest.TestCase):
    """Test FeatureComputer protocol and pure deterministic computation."""

    def test_conforms_to_protocol(self) -> None:
        comp = MockSMAComputer(period=3)
        self.assertIsInstance(comp, FeatureComputer)

    def test_pure_deterministic_computation(self) -> None:
        t0 = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 11, 9, 11, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

        candles = [
            CandleDTO(t0, Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100"), Decimal("10")),
            CandleDTO(t1, Decimal("100"), Decimal("110"), Decimal("100"), Decimal("110"), Decimal("20")),
            CandleDTO(t2, Decimal("110"), Decimal("125"), Decimal("110"), Decimal("120"), Decimal("30")),
        ]
        series = OHLCVSeriesDTO("BTCUSDT", Timeframe.H1, tuple(candles))

        comp = MockSMAComputer(period=3)
        features = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(features), 1)
        sma = features[0]
        # (100 + 110 + 120) / 3 = 110
        self.assertEqual(sma.value, Decimal("110"))
        self.assertEqual(sma.timestamp, t2)
        self.assertEqual(sma.feature_name, "SMA_3")


if __name__ == "__main__":
    unittest.main()
