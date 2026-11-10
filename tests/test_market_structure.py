"""Comprehensive unit tests for MarketStructureEngine and Smart Money Concepts computers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import threading
import unittest

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import (
    BreakOfStructureDTO,
    ChangeOfCharacterDTO,
    FairValueGapDTO,
    LiquidityPoolDTO,
    LiquiditySweepDTO,
    OrderBlockDTO,
    PremiumDiscountDTO,
    SwingPointDTO,
)
from tradingagents.dataflows.dto.market_data import CandleDTO, OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.store import InMemoryFeatureStore
from tradingagents.dataflows.features.structure import (
    BreakOfStructureComputer,
    ChangeOfCharacterComputer,
    FairValueGapComputer,
    LiquidityPoolComputer,
    LiquiditySweepComputer,
    MarketStructureEngine,
    OrderBlockComputer,
    PremiumDiscountComputer,
    SwingComputer,
    detect_swings,
)


def make_candle(
    dt: datetime,
    open_p: str,
    high_p: str,
    low_p: str,
    close_p: str,
    volume: str = "100.0",
) -> CandleDTO:
    """Helper to construct verified CandleDTO."""
    return CandleDTO(
        timestamp=dt,
        open=Decimal(open_p),
        high=Decimal(high_p),
        low=Decimal(low_p),
        close=Decimal(close_p),
        volume=Decimal(volume),
    )


class TestSmartMoneyDTOs(unittest.TestCase):
    """Test validation and invariants of new SMC DTOs."""

    def setUp(self) -> None:
        self.now = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)

    def test_swing_point_dto(self) -> None:
        sp = SwingPointDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.now,
            feature_name="SWING_MINOR",
            is_high=True,
            price=Decimal("85000.00"),
            is_major=False,
        )
        self.assertTrue(sp.is_high)
        self.assertEqual(sp.price, Decimal("85000.00"))

        with self.assertRaises(DTOValidationError):
            SwingPointDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.now,
                feature_name="SWING_MINOR",
                is_high=True,
                price=Decimal("-10.00"),  # Negative price
            )

    def test_liquidity_pool_dto(self) -> None:
        lp = LiquidityPoolDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.now,
            feature_name="LIQUIDITY_POOL",
            is_high=True,
            level=Decimal("85500.00"),
            touch_count=2,
            tolerance_bps=Decimal("10.0"),
            swept=False,
        )
        self.assertEqual(lp.touch_count, 2)

        with self.assertRaises(DTOValidationError):
            LiquidityPoolDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.now,
                feature_name="LIQUIDITY_POOL",
                is_high=True,
                level=Decimal("85500.00"),
                touch_count=1,  # < 2 touches is not a pool
            )

    def test_premium_discount_dto(self) -> None:
        pd_dto = PremiumDiscountDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.now,
            feature_name="PD_20",
            range_high=Decimal("90000.00"),
            range_low=Decimal("80000.00"),
            equilibrium=Decimal("85000.00"),
            current_price=Decimal("88000.00"),
            zone="PREMIUM",
            percentile=Decimal("80.0"),
        )
        self.assertEqual(pd_dto.zone, "PREMIUM")

        # Range low > Range high
        with self.assertRaises(DTOValidationError):
            PremiumDiscountDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.now,
                feature_name="PD_20",
                range_high=Decimal("80000.00"),
                range_low=Decimal("90000.00"),
                equilibrium=Decimal("85000.00"),
                current_price=Decimal("88000.00"),
                zone="PREMIUM",
            )

        # Invalid zone string
        with self.assertRaises(DTOValidationError):
            PremiumDiscountDTO(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                timestamp=self.now,
                feature_name="PD_20",
                range_high=Decimal("90000.00"),
                range_low=Decimal("80000.00"),
                equilibrium=Decimal("85000.00"),
                current_price=Decimal("88000.00"),
                zone="INVALID_ZONE",
            )


class TestStructureComputers(unittest.TestCase):
    """Test individual Smart Money Concepts structural computers."""

    def setUp(self) -> None:
        self.base_dt = datetime(2026, 11, 9, 0, 0, 0, tzinfo=timezone.utc)

    def _build_series(self, candle_specs: list[tuple[str, str, str, str, str]]) -> OHLCVSeriesDTO:
        candles = []
        for i, (o, h, l, c, v) in enumerate(candle_specs):
            dt = self.base_dt + timedelta(hours=i)
            candles.append(make_candle(dt, o, h, l, c, v))
        return OHLCVSeriesDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, candles=tuple(candles))

    def test_swing_detection_and_no_lookahead(self) -> None:
        # Create clear V-top at index 2 (H=120) and V-bottom at index 5 (L=80)
        # left_bars=2, right_bars=2
        specs = [
            ("100", "105", "95", "100", "10"),   # 0
            ("100", "110", "98", "108", "10"),   # 1
            ("108", "120", "105", "115", "10"),  # 2: Swing High at H=120, confirmed at idx 4 (2+2)
            ("108", "112", "102", "105", "10"),  # 3: Valid bounds
            ("105", "106", "94", "96", "10"),    # 4: Confirmation bar for idx 2 swing high
            ("96", "98", "80", "85", "10"),      # 5: Swing Low at L=80, confirmed at idx 7 (5+2)
            ("85", "92", "84", "90", "10"),      # 6
            ("90", "96", "88", "94", "10"),      # 7: Confirmation bar for idx 5 swing low
        ]
        series = self._build_series(specs)
        comp = SwingComputer(left_bars=2, right_bars=2, is_major=False)
        swings = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(swings), 2)
        # First swing is high at 120, confirmed at bar 4
        self.assertTrue(swings[0].is_high)
        self.assertEqual(swings[0].price, Decimal("120"))
        self.assertEqual(swings[0].timestamp, self.base_dt + timedelta(hours=4))

        # Second swing is low at 80, confirmed at bar 7
        self.assertFalse(swings[1].is_high)
        self.assertEqual(swings[1].price, Decimal("80"))
        self.assertEqual(swings[1].timestamp, self.base_dt + timedelta(hours=7))

    def test_fair_value_gap_detection(self) -> None:
        # Bullish FVG: candle 0 high=105, candle 1 large green, candle 2 low=112 (> 105)
        specs = [
            ("100", "105", "98", "102", "10"),   # 0: High = 105
            ("102", "125", "102", "124", "50"),  # 1: Displacement candle
            ("124", "130", "112", "128", "20"),  # 2: Low = 112 -> Gap: [105, 112]
            ("128", "129", "120", "122", "10"),  # 3: Low = 120 (unmitigated)
        ]
        series = self._build_series(specs)
        comp = FairValueGapComputer()
        fvgs = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(fvgs), 1)
        fvg = fvgs[0]
        self.assertTrue(fvg.is_bullish)
        self.assertEqual(fvg.lower_bound, Decimal("105"))
        self.assertEqual(fvg.upper_bound, Decimal("112"))
        self.assertFalse(fvg.mitigated)

        # Extend with candle 4 mitigating the gap (Low = 104 <= 105)
        specs_mitigated = specs + [("122", "123", "104", "110", "15")]
        series_mitigated = self._build_series(specs_mitigated)
        fvgs_mitigated = comp.compute("BTCUSDT", Timeframe.H1, series_mitigated)
        self.assertTrue(fvgs_mitigated[0].mitigated)

    def test_break_of_structure(self) -> None:
        # Swing high at bar 2 (H=115, confirmed at bar 4).
        # Bar 5 closes at 122 (> 115) -> Bullish BOS!
        specs = [
            ("100", "105", "98", "102", "10"),   # 0
            ("102", "110", "101", "109", "10"),  # 1
            ("109", "115", "106", "112", "10"),  # 2: Swing High H=115
            ("112", "113", "104", "108", "10"),  # 3
            ("108", "110", "102", "106", "10"),  # 4: Confirmation bar for bar 2
            ("106", "125", "105", "122", "80"),  # 5: Closes above 115 -> Bullish BOS!
        ]
        series = self._build_series(specs)
        comp = BreakOfStructureComputer(left_bars=2, right_bars=2)
        bos_events = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(bos_events), 1)
        bos = bos_events[0]
        self.assertTrue(bos.is_bullish)
        self.assertEqual(bos.broken_level, Decimal("115"))
        self.assertEqual(bos.displacement_volume, Decimal("80"))

    def test_change_of_character(self) -> None:
        # 1. Bar 2: Swing High at 110 (confirmed at bar 4)
        # 2. Bar 4: Swing Low at 90 (confirmed at bar 6)
        # 3. Bar 5: Closes at 115 (> 110) -> establishes uptrend
        # 4. Bar 7: Closes at 86 (< 90) -> breaks prior swing low -> Bearish CHoCH!
        specs = [
            ("100", "105", "98", "102", "10"),   # 0
            ("102", "108", "100", "106", "10"),  # 1
            ("106", "110", "104", "108", "10"),  # 2: Swing High H=110 (confirmed at bar 4)
            ("108", "109", "95", "96", "10"),    # 3
            ("96", "98", "90", "94", "10"),      # 4: Swing Low L=90 (confirmed at bar 6)
            ("94", "116", "94", "115", "40"),    # 5: Closes at 115 > 110 -> establishes bullish trend
            ("115", "116", "100", "102", "10"),  # 6: Confirmation of bar 4 swing low
            ("102", "104", "84", "86", "50"),    # 7: Closes at 86 < 90 -> Bearish CHoCH!
        ]
        series = self._build_series(specs)
        comp = ChangeOfCharacterComputer(left_bars=2, right_bars=2)
        choch_events = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(choch_events), 1)
        choch = choch_events[0]
        self.assertFalse(choch.is_bullish)
        self.assertEqual(choch.pivot_level, Decimal("90"))

    def test_order_block_detection(self) -> None:
        # Lookback avg=3, volume surge >= 1.5
        # Bars 0, 1, 2 volume=10.
        # Bar 3: Red candle (close < open: 105 -> 100).
        # Bar 4: Strong green displacement candle (open=100, close=120 > 105, vol=50, surge=5x).
        specs = [
            ("100", "102", "98", "100", "10"),
            ("100", "103", "99", "102", "10"),
            ("102", "104", "100", "103", "10"),
            ("103", "105", "96", "98", "10"),   # Bar 3: Bearish OB candidate
            ("98", "122", "98", "120", "50"),   # Bar 4: Strong displacement surge
        ]
        series = self._build_series(specs)
        comp = OrderBlockComputer(volume_threshold=Decimal("1.5"), lookback_avg=3)
        obs = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(obs), 1)
        ob = obs[0]
        self.assertTrue(ob.is_bullish)
        self.assertEqual(ob.top_price, Decimal("105"))
        self.assertEqual(ob.bottom_price, Decimal("96"))
        self.assertEqual(ob.volume_surge_ratio, Decimal("5.0"))
        self.assertFalse(ob.mitigated)

    def test_liquidity_pool_and_sweep(self) -> None:
        # Create Equal Highs (EQH) at price 120 within tolerance:
        # Swing High 1 at bar 2 (H=120.00, confirmed at 4)
        # Swing High 2 at bar 6 (H=120.05, confirmed at 8)
        # Bar 9 wicks to 121 (> 120.05) but closes at 118 (< 120.00) -> Liquidity Sweep!
        specs = [
            ("100", "105", "98", "102", "10"),    # 0
            ("102", "112", "100", "110", "10"),   # 1
            ("110", "120.00", "108", "115", "10"),# 2: Swing High 1
            ("115", "116", "105", "108", "10"),   # 3
            ("108", "110", "102", "106", "10"),   # 4: Confirmation bar for SH1
            ("106", "115", "104", "112", "10"),   # 5
            ("112", "120.05", "110", "116", "10"),# 6: Swing High 2 (EQH with SH1)
            ("116", "117", "108", "110", "10"),   # 7
            ("110", "112", "104", "106", "10"),   # 8: Confirmation bar for SH2
            ("106", "121.00", "105", "118", "40"),# 9: Sweep! High=121, Close=118
        ]
        series = self._build_series(specs)

        # 1. Test Liquidity Pool
        pool_comp = LiquidityPoolComputer(left_bars=2, right_bars=2, tolerance_bps=Decimal("10.0"))
        pools = pool_comp.compute("BTCUSDT", Timeframe.H1, series)
        self.assertEqual(len(pools), 1)
        self.assertTrue(pools[0].is_high)
        self.assertAlmostEqual(float(pools[0].level), 120.025, places=2)

        # 2. Test Liquidity Sweep
        sweep_comp = LiquiditySweepComputer(left_bars=2, right_bars=2)
        sweeps = sweep_comp.compute("BTCUSDT", Timeframe.H1, series)
        self.assertGreaterEqual(len(sweeps), 1)
        # Verify the bar 9 sweep of the equal high
        latest_sweep = sweeps[-1]
        self.assertTrue(latest_sweep.is_buy_side)
        self.assertEqual(latest_sweep.swept_level, Decimal("120.05"))
        self.assertEqual(latest_sweep.rejection_price, Decimal("118"))

    def test_premium_discount_calculation(self) -> None:
        # 5 candles: Lows min=80, Highs max=120. Equilibrium = 100.
        # Candle 4 close = 115 (> 100) -> Zone = PREMIUM, Percentile = (115-80)/40 = 87.5%
        specs = [
            ("85", "90", "80", "85", "10"),
            ("85", "100", "84", "95", "10"),
            ("95", "110", "92", "105", "10"),
            ("105", "120", "102", "110", "10"),
            ("110", "118", "108", "115", "10"),
        ]
        series = self._build_series(specs)
        comp = PremiumDiscountComputer(lookback_period=5)
        pds = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(pds), 1)
        pd_val = pds[0]
        self.assertEqual(pd_val.range_high, Decimal("120"))
        self.assertEqual(pd_val.range_low, Decimal("80"))
        self.assertEqual(pd_val.equilibrium, Decimal("100"))
        self.assertEqual(pd_val.zone, "PREMIUM")
        self.assertEqual(pd_val.percentile, Decimal("87.5"))


class TestMarketStructureEngine(unittest.TestCase):
    """Test MarketStructureEngine orchestration, deduplication, and FeatureStore integration."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.engine = MarketStructureEngine(feature_store=self.store, register_defaults=True)
        # Create 30 candles with oscillating swings
        self.base_dt = datetime(2026, 11, 9, 0, 0, 0, tzinfo=timezone.utc)
        candles = []
        for i in range(30):
            p = Decimal(f"{100 + (10 if i % 4 == 2 else (-10 if i % 4 == 0 else 0))}")
            dt = self.base_dt + timedelta(hours=i)
            candles.append(make_candle(dt, str(p), str(p + Decimal("5")), str(p - Decimal("5")), str(p), "20"))
        self.series = OHLCVSeriesDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, candles=tuple(candles))

    def test_default_computers_registered(self) -> None:
        computers = self.engine.list_computers()
        self.assertIn("SWING_MINOR_2_2", computers)
        self.assertIn("SWING_MAJOR_5_5", computers)
        self.assertIn("FVG", computers)
        self.assertIn("BOS", computers)
        self.assertIn("CHOCH", computers)
        self.assertIn("ORDER_BLOCK", computers)
        self.assertIn("LIQUIDITY_POOL", computers)
        self.assertIn("LIQUIDITY_SWEEP", computers)
        self.assertIn("PREMIUM_DISCOUNT_20", computers)

    def test_execute_and_feature_store_integration(self) -> None:
        res = self.engine.execute("BTCUSDT", Timeframe.H1, self.series, "SWING_MINOR_2_2", store_results=True)
        self.assertGreater(len(res), 0)

        # Verify FeatureStore received the computed features
        latest = self.store.get_latest("BTCUSDT", Timeframe.H1, "SWING_MINOR_2_2")
        self.assertIsNotNone(latest)
        self.assertEqual(latest, res[-1])

    def test_execute_batch(self) -> None:
        targets = ["SWING_MINOR_2_2", "PREMIUM_DISCOUNT_20"]
        batch = self.engine.execute_batch("BTCUSDT", Timeframe.H1, self.series, targets, store_results=True)

        self.assertEqual(len(batch), 2)
        for name in targets:
            self.assertIn(name, batch)
            self.assertIsNotNone(self.store.get_latest("BTCUSDT", Timeframe.H1, name))

    def test_execute_all(self) -> None:
        all_results = self.engine.execute_all("BTCUSDT", Timeframe.H1, self.series, store_results=True)
        self.assertEqual(len(all_results), len(self.engine.list_computers()))

    def test_deduplication_memo_cache(self) -> None:
        # First execution computes
        res1 = self.engine.execute("BTCUSDT", Timeframe.H1, self.series, "SWING_MINOR_2_2")
        # Second execution retrieves from memoization cache
        res2 = self.engine.execute("BTCUSDT", Timeframe.H1, self.series, "SWING_MINOR_2_2")
        self.assertEqual(res1, res2)

    def test_thread_safety_concurrency(self) -> None:
        threads: list[threading.Thread] = []
        errors: list[Exception] = []

        def worker(feat_name: str) -> None:
            try:
                self.engine.execute("BTCUSDT", Timeframe.H1, self.series, feat_name)
            except Exception as e:
                errors.append(e)

        features = ["SWING_MINOR_2_2", "PREMIUM_DISCOUNT_20", "FVG"]
        for feat in features * 4:
            threads.append(threading.Thread(target=worker, args=(feat,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
