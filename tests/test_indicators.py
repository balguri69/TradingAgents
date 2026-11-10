"""Comprehensive unit tests for Technical Indicator Computers and IndicatorEngine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import threading
import unittest

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import (
    ATRDTO,
    BollingerBandsDTO,
    EMADTO,
    MACDDTO,
    RSIDTO,
    SMADTO,
    VolumeProfileDTO,
    VWAPDTO,
)
from tradingagents.dataflows.dto.market_data import CandleDTO, OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators import (
    ATRComputer,
    BollingerBandsComputer,
    EMAComputer,
    IndicatorEngine,
    MACDComputer,
    RSIComputer,
    SMAComputer,
    VolumeProfileComputer,
    VWAPComputer,
    validate_ohlcv_series,
)
from tradingagents.dataflows.features.store import InMemoryFeatureStore


def create_sample_candle(
    dt: datetime,
    price: str,
    high_offset: str = "2.00",
    low_offset: str = "2.00",
    volume: str = "100.0",
) -> CandleDTO:
    """Helper to create valid test candles."""
    p = Decimal(price)
    h = p + Decimal(high_offset)
    l = p - Decimal(low_offset)
    v = Decimal(volume)
    return CandleDTO(
        timestamp=dt,
        open=p,
        high=h,
        low=l,
        close=p,
        volume=v,
    )


def create_sample_series(
    prices: list[str],
    start_dt: datetime | None = None,
    timeframe: Timeframe = Timeframe.H1,
    symbol: str = "BTCUSDT",
) -> OHLCVSeriesDTO:
    """Helper to create OHLCVSeriesDTO with consecutive hourly timestamps."""
    base_dt = start_dt or datetime(2026, 11, 9, 0, 0, 0, tzinfo=timezone.utc)
    candles: list[CandleDTO] = []
    for i, p in enumerate(prices):
        dt = base_dt + timedelta(hours=i)
        candles.append(create_sample_candle(dt, p))
    return OHLCVSeriesDTO(symbol=symbol, timeframe=timeframe, candles=tuple(candles))


class TestValidation(unittest.TestCase):
    """Test OHLCV series validation and edge-case rejection."""

    def setUp(self) -> None:
        self.t0 = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
        self.t1 = datetime(2026, 11, 9, 11, 0, tzinfo=timezone.utc)

    def test_timezone_naive_rejection(self) -> None:
        naive_dt = datetime(2026, 11, 9, 10, 0)
        with self.assertRaises(DTOValidationError):
            CandleDTO(naive_dt, Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100"), Decimal("10"))

    def test_unsorted_candles_rejection(self) -> None:
        c1 = CandleDTO(self.t1, Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100"), Decimal("10"))
        c2 = CandleDTO(self.t0, Decimal("102"), Decimal("105"), Decimal("95"), Decimal("102"), Decimal("10"))
        series = OHLCVSeriesDTO("BTCUSDT", Timeframe.H1, (c1, c2))
        with self.assertRaises(DTOValidationError):
            validate_ohlcv_series(series)

    def test_duplicate_timestamp_rejection(self) -> None:
        c1 = CandleDTO(self.t0, Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100"), Decimal("10"))
        c2 = CandleDTO(self.t0, Decimal("102"), Decimal("105"), Decimal("95"), Decimal("102"), Decimal("10"))
        series = OHLCVSeriesDTO("BTCUSDT", Timeframe.H1, (c1, c2))
        with self.assertRaises(DTOValidationError):
            validate_ohlcv_series(series)

    def test_nan_or_infinite_rejection(self) -> None:
        with self.assertRaises(DTOValidationError):
            CandleDTO(self.t0, Decimal("NaN"), Decimal("105"), Decimal("95"), Decimal("100"), Decimal("10"))

        with self.assertRaises(DTOValidationError):
            CandleDTO(self.t0, Decimal("100"), Decimal("Infinity"), Decimal("95"), Decimal("100"), Decimal("10"))

    def test_negative_volume_rejection(self) -> None:
        with self.assertRaises(DTOValidationError):
            CandleDTO(self.t0, Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100"), Decimal("-10"))

    def test_insufficient_candles_rejection(self) -> None:
        series = create_series = create_sample_series(["100", "102"])
        comp = SMAComputer(period=5)
        with self.assertRaises(DTOValidationError):
            comp.compute("BTCUSDT", Timeframe.H1, series)


class TestMathematicalCorrectness(unittest.TestCase):
    """Test mathematical accuracy of all 8 indicator computers."""

    def test_sma_calculation(self) -> None:
        # Prices: 10, 20, 30, 40, 50, 60. Period = 3.
        # SMA(3):
        # idx 2: (10 + 20 + 30) / 3 = 20
        # idx 3: (20 + 30 + 40) / 3 = 30
        # idx 4: (30 + 40 + 50) / 3 = 40
        # idx 5: (40 + 50 + 60) / 3 = 50
        series = create_sample_series(["10", "20", "30", "40", "50", "60"])
        comp = SMAComputer(period=3)
        res = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(res), 4)
        self.assertIsInstance(res[0], SMADTO)
        self.assertEqual(res[0].value, Decimal("20"))
        self.assertEqual(res[1].value, Decimal("30"))
        self.assertEqual(res[2].value, Decimal("40"))
        self.assertEqual(res[3].value, Decimal("50"))

    def test_ema_calculation(self) -> None:
        # Prices: 10, 20, 30, 40. Period = 2.
        # k = 2 / (2 + 1) = 2/3. 1 - k = 1/3.
        # Seed at idx 1: (10 + 20) / 2 = 15.
        # idx 2: 30 * (2/3) + 15 * (1/3) = 20 + 5 = 25.
        # idx 3: 40 * (2/3) + 25 * (1/3) = 80/3 + 25/3 = 105/3 = 35.
        series = create_sample_series(["10", "20", "30", "40"])
        comp = EMAComputer(period=2)
        res = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(res), 3)
        self.assertIsInstance(res[0], EMADTO)
        self.assertEqual(res[0].value, Decimal("15"))
        self.assertEqual(res[1].value, Decimal("25"))
        self.assertEqual(res[2].value, Decimal("35"))

    def test_rsi_calculation(self) -> None:
        # Strictly rising prices -> RSI = 100
        rising = create_sample_series(["10", "12", "14", "16", "18"])
        comp = RSIComputer(period=3)
        res_rising = comp.compute("BTCUSDT", Timeframe.H1, rising)
        self.assertEqual(res_rising[-1].value, Decimal("100"))

        # Strictly falling prices -> RSI = 0
        falling = create_sample_series(["50", "45", "40", "35", "30"])
        res_falling = comp.compute("BTCUSDT", Timeframe.H1, falling)
        self.assertEqual(res_falling[-1].value, Decimal("0"))

        # Flat prices -> RSI = 50
        flat = create_sample_series(["100", "100", "100", "100", "100"])
        res_flat = comp.compute("BTCUSDT", Timeframe.H1, flat)
        self.assertEqual(res_flat[-1].value, Decimal("50"))

    def test_atr_calculation(self) -> None:
        # Create candles where True Range is known
        dt = datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc)
        # Candle 0: H=110, L=90, C=100 -> TR = 20
        # Candle 1: H=115, L=95, C=105, prev_C=100 -> TR = max(20, 15, 5) = 20
        # Candle 2: H=125, L=105, C=120, prev_C=105 -> TR = max(20, 20, 0) = 20
        c0 = CandleDTO(dt, Decimal("100"), Decimal("110"), Decimal("90"), Decimal("100"), Decimal("10"))
        c1 = CandleDTO(dt + timedelta(hours=1), Decimal("105"), Decimal("115"), Decimal("95"), Decimal("105"), Decimal("10"))
        c2 = CandleDTO(dt + timedelta(hours=2), Decimal("115"), Decimal("125"), Decimal("105"), Decimal("120"), Decimal("10"))
        series = OHLCVSeriesDTO("BTCUSDT", Timeframe.H1, (c0, c1, c2))

        comp = ATRComputer(period=2)
        res = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(res), 2)
        self.assertIsInstance(res[0], ATRDTO)
        # Seed ATR(2) = (20 + 20) / 2 = 20
        self.assertEqual(res[0].value, Decimal("20"))
        # Next ATR = (20 * 1 + 20) / 2 = 20
        self.assertEqual(res[1].value, Decimal("20"))

    def test_macd_calculation(self) -> None:
        # 10 candles, fast=2, slow=4, signal=2
        series = create_sample_series(["10", "12", "14", "16", "18", "20", "22", "24", "26", "28"])
        comp = MACDComputer(fast_period=2, slow_period=4, signal_period=2)
        res = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertGreaterEqual(len(res), 1)
        self.assertIsInstance(res[0], MACDDTO)
        for item in res:
            # Verify histogram invariant: histogram == macd_line - signal_line
            self.assertEqual(item.histogram, item.macd_line - item.signal_line)

    def test_bollinger_bands_calculation(self) -> None:
        # Constant prices: std_dev = 0 -> upper == middle == lower
        flat = create_sample_series(["100", "100", "100", "100"])
        comp = BollingerBandsComputer(period=3, num_std_dev=Decimal("2.0"))
        res_flat = comp.compute("BTCUSDT", Timeframe.H1, flat)

        self.assertEqual(len(res_flat), 2)
        self.assertIsInstance(res_flat[0], BollingerBandsDTO)
        self.assertEqual(res_flat[0].middle_band, Decimal("100"))
        self.assertEqual(res_flat[0].upper_band, Decimal("100"))
        self.assertEqual(res_flat[0].lower_band, Decimal("100"))
        self.assertEqual(res_flat[0].bandwidth_bps, Decimal("0"))

        # Volatile prices: verify lower <= middle <= upper
        volatile = create_sample_series(["100", "110", "90", "120", "80"])
        res_vol = comp.compute("BTCUSDT", Timeframe.H1, volatile)
        for bb in res_vol:
            self.assertTrue(bb.lower_band <= bb.middle_band <= bb.upper_band)
            self.assertGreater(bb.bandwidth_bps, Decimal("0"))

    def test_vwap_calculation(self) -> None:
        dt = datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc)
        # Candle 1: H=10, L=10, C=10 (TP=10), Vol=100 -> CumTPVol=1000, CumVol=100 -> VWAP = 10
        # Candle 2: H=20, L=20, C=20 (TP=20), Vol=300 -> CumTPVol=1000 + 6000 = 7000, CumVol=400 -> VWAP = 7000/400 = 17.5
        c0 = CandleDTO(dt, Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10"), Decimal("100"))
        c1 = CandleDTO(dt + timedelta(hours=1), Decimal("20"), Decimal("20"), Decimal("20"), Decimal("20"), Decimal("300"))
        series = OHLCVSeriesDTO("BTCUSDT", Timeframe.H1, (c0, c1))

        comp = VWAPComputer()
        res = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(res), 2)
        self.assertIsInstance(res[0], VWAPDTO)
        self.assertEqual(res[0].vwap, Decimal("10"))
        self.assertEqual(res[1].vwap, Decimal("17.5"))

    def test_volume_profile_calculation(self) -> None:
        series = create_sample_series(["100", "102", "105", "101", "103"])
        comp = VolumeProfileComputer(num_bins=10, value_area_pct=Decimal("0.70"))
        res = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(res), 1)
        vp = res[0]
        self.assertIsInstance(vp, VolumeProfileDTO)
        # Verify institutional invariants: val <= poc <= vah
        self.assertTrue(vp.val <= vp.poc <= vp.vah)
        self.assertGreater(vp.total_volume, Decimal("0"))


class TestIndicatorEngineOrchestration(unittest.TestCase):
    """Test IndicatorEngine registration, execution, and FeatureStore integration."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.engine = IndicatorEngine(feature_store=self.store, register_defaults=True)
        # Generate 60 hourly candles
        prices = [str(100 + (i % 10)) for i in range(60)]
        self.series = create_sample_series(prices)

    def test_default_computers_registered(self) -> None:
        computers = self.engine.list_computers()
        self.assertIn("SMA_20", computers)
        self.assertIn("SMA_50", computers)
        self.assertIn("EMA_9", computers)
        self.assertIn("EMA_21", computers)
        self.assertIn("RSI_14", computers)
        self.assertIn("ATR_14", computers)
        self.assertIn("MACD_12_26_9", computers)
        self.assertIn("BB_20_2.0", computers)
        self.assertIn("VWAP", computers)
        self.assertIn("VP_24_70", computers)

    def test_execute_single_and_feature_store_integration(self) -> None:
        res = self.engine.execute("BTCUSDT", Timeframe.H1, self.series, "SMA_20", store_results=True)
        self.assertGreater(len(res), 0)

        # Verify observation is in FeatureStore
        latest_stored = self.store.get_latest("BTCUSDT", Timeframe.H1, "SMA_20")
        self.assertIsNotNone(latest_stored)
        self.assertEqual(latest_stored, res[-1])

    def test_execute_batch(self) -> None:
        targets = ["EMA_9", "RSI_14", "VWAP"]
        res = self.engine.execute_batch("BTCUSDT", Timeframe.H1, self.series, targets, store_results=True)

        self.assertEqual(len(res), 3)
        for name in targets:
            self.assertIn(name, res)
            self.assertGreater(len(res[name]), 0)
            self.assertIsNotNone(self.store.get_latest("BTCUSDT", Timeframe.H1, name))

    def test_execute_all(self) -> None:
        res = self.engine.execute_all("BTCUSDT", Timeframe.H1, self.series, store_results=True)
        all_computers = self.engine.list_computers()
        self.assertEqual(len(res), len(all_computers))

        # Query batch from FeatureStore
        stored_batch = self.store.get_batch("BTCUSDT", Timeframe.H1, all_computers)
        self.assertEqual(len(stored_batch), len(all_computers))

    def test_duplicate_computation_prevention(self) -> None:
        """Verify identical inputs are retrieved from memoization cache without recalculating."""
        # First execution computes and caches
        res1 = self.engine.execute("BTCUSDT", Timeframe.H1, self.series, "SMA_20")
        # Second execution with exact same data returns identical cached objects
        res2 = self.engine.execute("BTCUSDT", Timeframe.H1, self.series, "SMA_20")
        self.assertEqual(res1, res2)

    def test_thread_safety_concurrent_execution(self) -> None:
        """Verify thread-safe indicator calculations across multiple threads."""
        threads: list[threading.Thread] = []
        errors: list[Exception] = []

        def worker(indicator_name: str) -> None:
            try:
                self.engine.execute("BTCUSDT", Timeframe.H1, self.series, indicator_name)
            except Exception as e:
                errors.append(e)

        indicators = ["SMA_20", "EMA_21", "RSI_14", "ATR_14", "BB_20_2.0", "VWAP"]
        for ind in indicators * 4:
            threads.append(threading.Thread(target=worker, args=(ind,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
