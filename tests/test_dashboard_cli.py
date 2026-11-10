"""Comprehensive unit, scenario, and regression test suite for Phase 13: Dashboard & CLI."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from decimal import Decimal

if "dotenv" not in sys.modules:
    _d = types.ModuleType("dotenv")
    _d.find_dotenv = lambda *a, **k: ""
    _d.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = _d

from tradingagents.dashboard.cli import parse_iso_datetime, run_cli
from tradingagents.dashboard.exporter import DashboardExporter
from tradingagents.dashboard.formatter import DashboardFormatter
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
from tradingagents.dashboard.service import DashboardService
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
    VWAPDTO,
)
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.features.store import InMemoryFeatureStore
from tradingagents.execution.adapters.paper import PaperBrokerAdapter
from tradingagents.execution.dto import OrderIntentDTO
from tradingagents.execution.engine import ExecutionEngine
from tradingagents.execution.enums import OrderSide, OrderType, TradeDirection
from tradingagents.risk.dto import RiskAssessmentDTO
from tradingagents.risk.enums import RiskLevel, VolatilityRegime


class TestDashboardModels(unittest.TestCase):
    """Test serialization, invariants, and defaults of dashboard models."""

    def setUp(self) -> None:
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_indicator_view_serialization(self) -> None:
        ind = IndicatorViewDTO(
            ema_9=Decimal("80000.50"),
            ema_21=Decimal("79500.25"),
            rsi_14=Decimal("62.50"),
        )
        d = ind.to_dict()
        self.assertEqual(d["ema_9"], "80000.50")
        self.assertEqual(d["ema_21"], "79500.25")
        self.assertEqual(d["rsi_14"], "62.50")
        self.assertIsNone(d["sma_200"])

    def test_dashboard_snapshot_json(self) -> None:
        snap = DashboardSnapshotDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            as_of=self.ts,
            generated_at=self.ts,
            reference_price=Decimal("80000.00"),
            probability=ProbabilityViewDTO(
                bullish_pct=Decimal("70.00"),
                bearish_pct=Decimal("15.00"),
                neutral_pct=Decimal("15.00"),
                confidence_score=Decimal("80.00"),
                dominant_direction="BULLISH",
            ),
            risk=RiskViewDTO(
                risk_level="LOW",
                volatility_regime="NORMAL",
                regime_tradeable=True,
            ),
        )
        json_str = snap.to_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["symbol"], "BTCUSDT")
        self.assertEqual(parsed["timeframe"], "1h")
        self.assertEqual(parsed["probability"]["bullish_pct"], "70.00")
        self.assertEqual(parsed["risk"]["risk_level"], "LOW")
        self.assertTrue(parsed["risk"]["regime_tradeable"])


class TestDashboardService(unittest.TestCase):
    """Test point-in-time querying, FeatureStore integration, and empty state handling."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.service = DashboardService(feature_store=self.store)
        self.t1 = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
        self.t2 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def test_empty_feature_store_state(self) -> None:
        """Dashboard gracefully handles empty state without errors."""
        snap = self.service.get_snapshot("ETHUSDT", "1h")
        self.assertEqual(snap.symbol, "ETHUSDT")
        self.assertEqual(snap.timeframe, Timeframe.H1)
        self.assertEqual(snap.probability.dominant_direction, "NEUTRAL")
        self.assertEqual(snap.risk.risk_level, "LOW")
        self.assertTrue(snap.risk.regime_tradeable)
        self.assertIsNone(snap.indicators.ema_9)

    def test_timeframe_normalization(self) -> None:
        self.assertEqual(DashboardService.normalize_timeframe("1h"), Timeframe.H1)
        self.assertEqual(DashboardService.normalize_timeframe("H1"), Timeframe.H1)
        self.assertEqual(DashboardService.normalize_timeframe("1d"), Timeframe.D1)
        self.assertEqual(DashboardService.normalize_timeframe("D1"), Timeframe.D1)
        self.assertEqual(DashboardService.normalize_timeframe("15m"), Timeframe.M15)
        self.assertEqual(DashboardService.normalize_timeframe(Timeframe.H4), Timeframe.H4)

    def test_point_in_time_feature_query(self) -> None:
        """Verify strict point-in-time correctness with zero future leakage."""
        # Store EMA at t1 = 500, and at t2 = 550
        self.store.store_feature(EMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.t1, feature_name="ema_9", period=9, value=Decimal("500.00")))
        self.store.store_feature(EMADTO(symbol="SPY", timeframe=Timeframe.H1, timestamp=self.t2, feature_name="ema_9", period=9, value=Decimal("550.00")))

        # Query as of t1: must see 500.00, not 550.00
        snap_t1 = self.service.get_snapshot("SPY", "1h", as_of=self.t1)
        self.assertEqual(snap_t1.indicators.ema_9, Decimal("500.00"))

        # Query as of t2: must see 550.00
        snap_t2 = self.service.get_snapshot("SPY", "1h", as_of=self.t2)
        self.assertEqual(snap_t2.indicators.ema_9, Decimal("550.00"))

    def test_comprehensive_features_extraction(self) -> None:
        """Verify that indicators, SMC structure, and risk are properly aggregated."""
        self.store.store_feature(EMADTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.t1, feature_name="ema_9", period=9, value=Decimal("80000.00")))
        self.store.store_feature(SMADTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.t1, feature_name="sma_20", period=20, value=Decimal("79500.00")))
        self.store.store_feature(RSIDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.t1, feature_name="rsi_14", period=14, value=Decimal("65.00")))
        self.store.store_feature(BollingerBandsDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.t1, feature_name="bollinger", upper_band=Decimal("82000.00"), middle_band=Decimal("80000.00"), lower_band=Decimal("78000.00")))
        self.store.store_feature(ATRDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.t1, feature_name="atr_14", period=14, value=Decimal("1200.00")))
        self.store.store_feature(VWAPDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.t1, feature_name="vwap", vwap=Decimal("80100.00")))

        # Smart money features
        self.store.store_feature(BreakOfStructureDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.t1, feature_name="break_of_structure", is_bullish=True, broken_level=Decimal("79800.00"), displacement_volume=Decimal("150.00")))
        self.store.store_feature(LiquiditySweepDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.t1, feature_name="liquidity_sweep", is_buy_side=True, swept_level=Decimal("80400.00"), rejection_price=Decimal("80200.00")))
        self.store.store_feature(PremiumDiscountDTO(symbol="BTCUSDT", timeframe=Timeframe.H1, timestamp=self.t1, feature_name="premium_discount", zone="PREMIUM", equilibrium=Decimal("79000.00"), range_low=Decimal("76000.00"), range_high=Decimal("82000.00"), current_price=Decimal("80000.00"), percentile=Decimal("66.67")))

        snap = self.service.get_snapshot("BTCUSDT", "1h", as_of=self.t1)
        self.assertEqual(snap.indicators.ema_9, Decimal("80000.00"))
        self.assertEqual(snap.indicators.sma_20, Decimal("79500.00"))
        self.assertEqual(snap.indicators.rsi_14, Decimal("65.00"))
        self.assertEqual(snap.indicators.bb_upper, Decimal("82000.00"))
        self.assertEqual(snap.indicators.vwap, Decimal("80100.00"))
        self.assertEqual(snap.structure.last_bos_type, "BULLISH")
        self.assertEqual(snap.structure.last_bos_price, Decimal("79800.00"))
        self.assertEqual(snap.structure.current_dealing_range, "PREMIUM")
        self.assertEqual(len(snap.structure.recent_liquidity_sweeps), 1)

    def test_execution_engine_integration(self) -> None:
        """Verify position and order state querying from ExecutionEngine."""
        broker = PaperBrokerAdapter(initial_balances={"USD": Decimal("200000.00")})
        broker.set_market_price("BTCUSDT", Decimal("80000.00"))
        exec_engine = ExecutionEngine(broker=broker, feature_store=self.store)

        # Place a market order
        intent = OrderIntentDTO(
            intent_id="i1",
            client_order_id="co1",
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            timestamp=self.t1,
            direction=TradeDirection.LONG,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1.5"),
            is_executable=True,
        )
        exec_engine.execute(intent)

        service_with_exec = DashboardService(
            feature_store=self.store,
            execution_engine=exec_engine,
        )

        snap = service_with_exec.get_snapshot("BTCUSDT", "1h")
        self.assertEqual(snap.execution.position_qty, Decimal("1.5"))
        self.assertGreater(snap.execution.average_entry_price, Decimal("0.00"))
        self.assertEqual(snap.execution.active_open_orders_count, 0)


class TestDashboardFormattersAndExporter(unittest.TestCase):
    """Test text, Markdown, JSON, and HTML output rendering and file export."""

    def setUp(self) -> None:
        self.ts = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        self.snap = DashboardSnapshotDTO(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            as_of=self.ts,
            generated_at=self.ts,
            reference_price=Decimal("80000.00"),
            indicators=IndicatorViewDTO(
                ema_9=Decimal("80100.00"),
                rsi_14=Decimal("65.50"),
                vwap=Decimal("80000.00"),
            ),
            structure=StructureViewDTO(
                swing_high=Decimal("82000.00"),
                swing_low=Decimal("78000.00"),
                last_bos_type="BULLISH",
                last_bos_price=Decimal("79500.00"),
            ),
            probability=ProbabilityViewDTO(
                bullish_pct=Decimal("65.00"),
                bearish_pct=Decimal("15.00"),
                neutral_pct=Decimal("20.00"),
                dominant_direction="BULLISH",
                directional_edge=Decimal("50.00"),
                confidence_score=Decimal("80.00"),
            ),
            risk=RiskViewDTO(
                risk_level="LOW",
                volatility_regime="NORMAL",
                regime_tradeable=True,
            ),
            synthesis=SynthesisViewDTO(
                directional_bias="BULLISH",
                composite_confidence=Decimal("80.00"),
                conviction_tier="HIGH",
                is_actionable=True,
            ),
            execution=ExecutionViewDTO(
                symbol="BTCUSDT",
                position_qty=Decimal("2.0"),
                average_entry_price=Decimal("79500.00"),
                realized_pnl=Decimal("1000.00"),
            ),
        )

    def test_cli_text_format(self) -> None:
        text = DashboardFormatter.format_cli(self.snap)
        self.assertIn("INSTITUTIONAL TRADING SYSTEM — MARKET STATE DASHBOARD", text)
        self.assertIn("BTCUSDT", text)
        self.assertIn("BULLISH", text)
        self.assertIn("LOW", text)
        self.assertIn("ALLOW TRADE", text)

    def test_markdown_format(self) -> None:
        md = DashboardFormatter.format_markdown(self.snap)
        self.assertIn("# Institutional Market State Report — `BTCUSDT`", md)
        self.assertIn("| **Bullish** | `65.00%` |", md)
        self.assertIn("| **Risk Level** | `LOW` |", md)
        self.assertIn("## 5. Execution State & Portfolio Position", md)

    def test_json_format(self) -> None:
        json_str = DashboardFormatter.format_json(self.snap)
        data = json.loads(json_str)
        self.assertEqual(data["symbol"], "BTCUSDT")
        self.assertEqual(data["probability"]["dominant_direction"], "BULLISH")
        self.assertEqual(data["execution"]["position_qty"], "2.0")

    def test_html_format(self) -> None:
        html = DashboardFormatter.format_html(self.snap)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("BTCUSDT", html)
        self.assertIn("REGIME TRADEABLE", html)
        self.assertIn("bar-bull", html)

    def test_file_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Export Text
            txt_path = os.path.join(tmpdir, "report.txt")
            DashboardExporter.export(self.snap, txt_path, file_format="text")
            self.assertTrue(os.path.exists(txt_path))
            with open(txt_path, "r", encoding="utf-8") as f:
                self.assertIn("BTCUSDT", f.read())

            # Export Markdown
            md_path = os.path.join(tmpdir, "report.md")
            DashboardExporter.export(self.snap, md_path, file_format="markdown")
            self.assertTrue(os.path.exists(md_path))
            with open(md_path, "r", encoding="utf-8") as f:
                self.assertIn("# Institutional Market State Report", f.read())

            # Export JSON
            json_path = os.path.join(tmpdir, "report.json")
            DashboardExporter.export(self.snap, json_path, file_format="json")
            self.assertTrue(os.path.exists(json_path))
            with open(json_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                self.assertEqual(loaded["symbol"], "BTCUSDT")

            # Export HTML
            html_path = os.path.join(tmpdir, "report.html")
            DashboardExporter.export(self.snap, html_path, file_format="html")
            self.assertTrue(os.path.exists(html_path))
            with open(html_path, "r", encoding="utf-8") as f:
                self.assertIn("<title>TradingAgents Dashboard — BTCUSDT [1h]</title>", f.read())


class TestDashboardCLI(unittest.TestCase):
    """Test CLI commands, argument parsing, timestamp handling, and error states."""

    def setUp(self) -> None:
        self.store = InMemoryFeatureStore()
        self.service = DashboardService(feature_store=self.store)

    def test_cli_snapshot_text(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run_cli(["snapshot", "-s", "BTCUSDT"], service=self.service, stdout=stdout, stderr=stderr)
        self.assertEqual(code, 0)
        out = stdout.getvalue()
        self.assertIn("BTCUSDT", out)
        self.assertIn("DIRECTIONAL PROBABILITY", out)

    def test_cli_snapshot_json(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run_cli(["snapshot", "-s", "SPY", "-t", "1d", "-f", "json"], service=self.service, stdout=stdout, stderr=stderr)
        self.assertEqual(code, 0)
        data = json.loads(stdout.getvalue())
        self.assertEqual(data["symbol"], "SPY")
        self.assertEqual(data["timeframe"], "1d")

    def test_cli_point_in_time_as_of(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run_cli(
            ["snapshot", "-s", "EURUSD", "--as-of", "2026-11-10T12:00:00Z"],
            service=self.service,
            stdout=stdout,
            stderr=stderr,
        )
        self.assertEqual(code, 0)
        self.assertIn("2026-11-10T12:00:00+00:00", stdout.getvalue())

    def test_cli_export_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "cli_report.md")
            stdout = io.StringIO()
            stderr = io.StringIO()
            code = run_cli(
                ["export", "-s", "BTCUSDT", "-o", out_file, "-f", "markdown"],
                service=self.service,
                stdout=stdout,
                stderr=stderr,
            )
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(out_file))
            self.assertIn("Exported snapshot to:", stdout.getvalue())
            self.assertIn("cli_report.md", stdout.getvalue())

    def test_cli_invalid_as_of_format(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run_cli(
            ["snapshot", "-s", "BTCUSDT", "--as-of", "not-a-date"],
            service=self.service,
            stdout=stdout,
            stderr=stderr,
        )
        self.assertEqual(code, 2)
        self.assertIn("Invalid timestamp format", stderr.getvalue())

    def test_cli_empty_command(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run_cli([], service=self.service, stdout=stdout, stderr=stderr)
        self.assertEqual(code, 1)

    def test_parse_iso_datetime_utility(self) -> None:
        self.assertIsNone(parse_iso_datetime(None))
        self.assertIsNone(parse_iso_datetime(""))
        dt = parse_iso_datetime("2026-11-10T15:30:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
