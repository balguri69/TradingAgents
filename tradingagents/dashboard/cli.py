"""Command-line operator interface for viewing market state, risk, and execution reports."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from tradingagents.dashboard.exporter import DashboardExporter
from tradingagents.dashboard.formatter import DashboardFormatter
from tradingagents.dashboard.service import DashboardService


def parse_iso_datetime(dt_str: str | None) -> datetime | None:
    """Safely parse an ISO 8601 datetime string into a UTC datetime."""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        raise ValueError(f"Invalid timestamp format '{dt_str}'. Expected ISO 8601 (e.g. '2026-11-10T12:00:00Z')")


def create_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with subcommands and flags."""
    parser = argparse.ArgumentParser(
        prog="tradingagents-dashboard",
        description="Institutional Operator CLI: Deterministic Market State, Risk & Execution Monitor",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available dashboard commands")

    # Common arguments
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-s", "--symbol", required=True, type=str, help="Ticker symbol (e.g. BTCUSDT, SPY, EURUSD)"
    )
    common.add_argument(
        "-t", "--timeframe", default="1h", type=str, help="Aggregation timeframe (e.g. 1m, 5m, 15m, 1h, 4h, 1d)"
    )
    common.add_argument(
        "--as-of", type=str, default=None, help="Point-in-time ISO timestamp (e.g. '2026-11-10T12:00:00Z')"
    )
    common.add_argument(
        "-f", "--format", choices=["text", "json", "markdown", "html"], default="text", help="Output format"
    )
    common.add_argument(
        "-o", "--output", type=str, default=None, help="Optional filepath to write output report to"
    )

    # Subcommands
    subparsers.add_parser("snapshot", parents=[common], help="Display unified market state snapshot")
    subparsers.add_parser("technical", parents=[common], help="Display technical indicator observations")
    subparsers.add_parser("structure", parents=[common], help="Display Smart Money market structure")
    subparsers.add_parser("probability", parents=[common], help="Display directional probability distribution")
    subparsers.add_parser("risk", parents=[common], help="Display institutional risk assessment and regimes")
    subparsers.add_parser("synthesis", parents=[common], help="Display multi-agent synthesis assessment")
    subparsers.add_parser("execution", parents=[common], help="Display execution history and portfolio positions")
    subparsers.add_parser("export", parents=[common], help="Export full report to specified output path")

    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    service: DashboardService | None = None,
    stdout=sys.stdout,
    stderr=sys.stderr,
) -> int:
    """Execute the dashboard CLI application."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help(stderr)
        return 1

    try:
        as_of_dt = parse_iso_datetime(args.as_of)
    except ValueError as e:
        stderr.write(f"Error: {e}\n")
        return 2

    srv = service or DashboardService()

    try:
        snapshot = srv.get_snapshot(
            symbol=args.symbol,
            timeframe=args.timeframe,
            as_of=as_of_dt,
        )

        fmt = args.format.lower()
        if fmt == "json":
            output_content = DashboardFormatter.format_json(snapshot)
        elif fmt in ("markdown", "md"):
            output_content = DashboardFormatter.format_markdown(snapshot)
        elif fmt == "html":
            output_content = DashboardFormatter.format_html(snapshot)
        else:
            output_content = DashboardFormatter.format_cli(snapshot)

        # Handle file export if requested
        if args.output or args.command == "export":
            dest = args.output or f"{args.symbol.lower()}_{args.timeframe}_snapshot.{'md' if fmt in ('markdown', 'md') else ('html' if fmt == 'html' else ('json' if fmt == 'json' else 'txt'))}"
            written_path = DashboardExporter.export(snapshot, dest, file_format=fmt)
            stdout.write(f"Exported snapshot to: {written_path}\n")
        else:
            stdout.write(output_content + "\n")

        return 0

    except Exception as e:
        stderr.write(f"Execution Error: {e}\n")
        return 3


if __name__ == "__main__":
    sys.exit(run_cli())
