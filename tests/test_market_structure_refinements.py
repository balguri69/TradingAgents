"""Unit tests for Phase 8.1 Market Structure Engine Refinements."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from tradingagents.dataflows.dto.features import LiquiditySweepDTO, OrderBlockDTO
from tradingagents.dataflows.dto.market_data import CandleDTO, OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.features.structure.liquidity import LiquiditySweepComputer
from tradingagents.dataflows.features.structure.order_blocks import OrderBlockComputer


def make_candle(
    dt: datetime,
    open_p: str,
    high_p: str,
    low_p: str,
    close_p: str,
    volume: str = "100.0",
) -> CandleDTO:
    """Helper to create verified CandleDTO."""
    o = Decimal(open_p)
    h = Decimal(high_p)
    l = Decimal(low_p)
    c = Decimal(close_p)
    v = Decimal(volume)
    return CandleDTO(
        timestamp=dt,
        open=o,
        high=max(h, o, c),
        low=min(l, o, c),
        close=c,
        volume=v,
    )


class TestPhase81Refinements(unittest.TestCase):
    """Test Phase 8.1 targeted refinements for sweeps and zero-volume order blocks."""

    def setUp(self) -> None:
        self.base_dt = datetime(2026, 11, 9, 0, 0, 0, tzinfo=timezone.utc)

    def _build_series(
        self,
        specs: list[tuple[str, str, str, str, str]],
        symbol: str = "BTCUSDT",
        timeframe: Timeframe = Timeframe.H1,
    ) -> OHLCVSeriesDTO:
        candles = []
        for i, (o, h, l, c, v) in enumerate(specs):
            dt = self.base_dt + timedelta(hours=i)
            candles.append(make_candle(dt, o, h, l, c, v))
        return OHLCVSeriesDTO(symbol=symbol, timeframe=timeframe, candles=tuple(candles))

    def test_liquidity_sweep_deduplication(self) -> None:
        """Verify that a single liquidity level produces exactly ONE sweep even if multiple consecutive wicks penetrate it."""
        # Bar 2 forms a swing high at 120.00, confirmed at bar 4 (left=2, right=2)
        # Bar 5: High=121.00, Close=118.00 -> First sweep of 120.00!
        # Bar 6: High=120.80, Close=117.00 -> Second wick penetration! Must NOT emit duplicate sweep!
        # Bar 7: High=120.50, Close=116.00 -> Third wick penetration! Must NOT emit duplicate sweep!
        specs = [
            ("100", "105", "98", "102", "10"),    # 0
            ("102", "112", "100", "110", "10"),   # 1
            ("110", "120.00", "108", "115", "10"),# 2: Swing High at 120.00
            ("115", "116", "105", "108", "10"),   # 3
            ("108", "110", "102", "106", "10"),   # 4: Confirmation bar for SH at 120.00
            ("106", "121.00", "105", "118", "40"),# 5: First sweep of 120.00!
            ("118", "120.80", "107", "117", "30"),# 6: Consecutive wick -> MUST BE IGNORED
            ("117", "120.50", "106", "116", "20"),# 7: Consecutive wick -> MUST BE IGNORED
        ]
        series = self._build_series(specs)
        comp = LiquiditySweepComputer(left_bars=2, right_bars=2)
        sweeps = comp.compute("BTCUSDT", Timeframe.H1, series)

        # Must have exactly 1 sweep for level 120.00, NOT 3
        self.assertEqual(len(sweeps), 1)
        self.assertEqual(sweeps[0].swept_level, Decimal("120.00"))
        self.assertEqual(sweeps[0].rejection_price, Decimal("118.00"))
        self.assertEqual(sweeps[0].timestamp, self.base_dt + timedelta(hours=5))

    def test_new_swing_level_allows_new_sweep(self) -> None:
        """Verify that after a level is consumed, a newly confirmed swing creates a new active level that can be swept."""
        # 1. Bar 2: SH1 at 120.00, confirmed at bar 4
        # 2. Bar 5: Sweeps SH1 (High=121, Close=118) -> SH1 consumed
        # 3. Bar 6: Forms new local swing high at 121.00, confirmed at bar 8
        # 4. Bar 9: Sweeps SH2 (High=122, Close=119) -> Emits sweep for new level 121.00!
        specs = [
            ("100", "105", "98", "102", "10"),    # 0
            ("102", "112", "100", "110", "10"),   # 1
            ("110", "120.00", "108", "115", "10"),# 2: SH1 @ 120.00
            ("115", "116", "105", "108", "10"),   # 3
            ("108", "110", "102", "106", "10"),   # 4: Conf bar for SH1
            ("106", "121.00", "105", "118", "40"),# 5: Sweeps SH1 @ 120.00
            ("118", "121.00", "110", "115", "10"),# 6: SH2 candidate @ 121.00
            ("115", "117", "108", "110", "10"),   # 7
            ("110", "112", "104", "106", "10"),   # 8: Conf bar for SH2 @ 121.00
            ("106", "122.00", "105", "119", "40"),# 9: Sweeps SH2 @ 121.00!
        ]
        series = self._build_series(specs)
        comp = LiquiditySweepComputer(left_bars=2, right_bars=2)
        sweeps = comp.compute("BTCUSDT", Timeframe.H1, series)

        # Must have exactly 2 sweeps: one for 120.00, and one for 121.00
        self.assertEqual(len(sweeps), 2)
        self.assertEqual(sweeps[0].swept_level, Decimal("120.00"))
        self.assertEqual(sweeps[1].swept_level, Decimal("121.00"))

    def test_order_block_zero_volume_atr_fallback(self) -> None:
        """Verify that zero-volume forex feeds automatically fallback to ATR displacement and detect Order Blocks."""
        # 7 candles with volume = 0.0 (Forex feed simulation)
        # Prior 5 bars have range 2.0 (ATR = 2.0).
        # Bar 5: Bearish candle (102 -> 100).
        # Bar 6: Strong Bullish displacement candle (open 100, close 108 > 102). Body = 8.0 >= 1.5 * 2.0 (3.0).
        specs = [
            ("100", "102", "100", "101", "0.0"),  # 0: range 2.0
            ("101", "103", "101", "102", "0.0"),  # 1: range 2.0
            ("102", "104", "102", "103", "0.0"),  # 2: range 2.0
            ("103", "105", "103", "104", "0.0"),  # 3: range 2.0
            ("104", "105", "103", "104", "0.0"),  # 4: range 2.0
            ("104", "105", "99", "100", "0.0"),   # 5: Bearish OB candidate (H=105, L=99)
            ("100", "110", "100", "108", "0.0"),  # 6: Strong displacement body=8.0 (>= 1.5 * 2.0)
        ]
        series = self._build_series(specs, symbol="EURUSD")
        comp = OrderBlockComputer(volume_threshold=Decimal("1.2"), lookback_avg=5, displacement_atr_mult=Decimal("1.5"))
        obs = comp.compute("EURUSD", Timeframe.H1, series)

        # Must detect bullish order block via ATR displacement fallback
        self.assertEqual(len(obs), 1)
        ob = obs[0]
        self.assertTrue(ob.is_bullish)
        self.assertEqual(ob.top_price, Decimal("105"))
        self.assertEqual(ob.bottom_price, Decimal("99"))
        self.assertGreaterEqual(ob.volume_surge_ratio, Decimal("1.5"))

    def test_crypto_volume_order_block_identical_behavior(self) -> None:
        """Verify that feeds with volume continue to use volume surge logic without interference."""
        # Volume exists (10.0, surge 50.0 = 5x)
        specs = [
            ("100", "102", "98", "100", "10.0"),
            ("100", "103", "99", "102", "10.0"),
            ("102", "104", "100", "103", "10.0"),
            ("103", "105", "96", "98", "10.0"),   # Bar 3: Bearish OB candidate
            ("98", "122", "98", "120", "50.0"),   # Bar 4: Strong displacement surge 5x
        ]
        series = self._build_series(specs, symbol="BTCUSDT")
        comp = OrderBlockComputer(volume_threshold=Decimal("1.5"), lookback_avg=3)
        obs = comp.compute("BTCUSDT", Timeframe.H1, series)

        self.assertEqual(len(obs), 1)
        ob = obs[0]
        self.assertTrue(ob.is_bullish)
        self.assertEqual(ob.top_price, Decimal("105"))
        self.assertEqual(ob.bottom_price, Decimal("96"))
        self.assertEqual(ob.volume_surge_ratio, Decimal("5.0"))


if __name__ == "__main__":
    unittest.main()
