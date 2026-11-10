"""Dashboard Exporter: deterministic file export for dashboard snapshots in multiple formats."""

from __future__ import annotations

import os
from pathlib import Path

from tradingagents.dashboard.formatter import DashboardFormatter
from tradingagents.dashboard.models import DashboardSnapshotDTO


class DashboardExporter:
    """Exports DashboardSnapshotDTO to disk in text, markdown, json, or html formats."""

    @staticmethod
    def export(
        snapshot: DashboardSnapshotDTO,
        filepath: str | Path,
        file_format: str = "text",
    ) -> str:
        """Export snapshot to a file on disk.
        
        Supported formats: 'text', 'markdown' (or 'md'), 'json', 'html'.
        Returns the absolute path of the generated file.
        """
        path = Path(filepath).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        fmt = file_format.strip().lower()
        if fmt in ("json",):
            content = DashboardFormatter.format_json(snapshot)
        elif fmt in ("markdown", "md"):
            content = DashboardFormatter.format_markdown(snapshot)
        elif fmt in ("html", "htm"):
            content = DashboardFormatter.format_html(snapshot)
        else:
            content = DashboardFormatter.format_cli(snapshot)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return str(path)
