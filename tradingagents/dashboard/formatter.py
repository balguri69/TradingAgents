"""Institutional formatters for CLI text, Markdown, JSON, and HTML dashboards."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from tradingagents.dashboard.models import DashboardSnapshotDTO


def _progress_bar(pct: Decimal, width: int = 20) -> str:
    """Generate an ASCII progress bar for probabilities and scores."""
    try:
        val = float(pct)
        clamped = max(0.0, min(100.0, val))
        filled_len = int(round(width * clamped / 100.0))
        empty_len = width - filled_len
        return f"[{'█' * filled_len}{'░' * empty_len}] {clamped:5.1f}%"
    except Exception:
        return f"[{'░' * width}]   0.0%"


def _format_decimal(val: Decimal | None, precision: int = 2) -> str:
    if val is None:
        return "N/A"
    return f"{val:.{precision}f}"


class DashboardFormatter:
    """Multi-format presenter transforming DashboardSnapshotDTO into text, Markdown, JSON, or HTML."""

    @staticmethod
    def format_cli(snap: DashboardSnapshotDTO) -> str:
        """Render a clean, high-density ASCII terminal dashboard."""
        sep = "═" * 78
        sub_sep = "─" * 78

        lines = [
            sep,
            f" INSTITUTIONAL TRADING SYSTEM — MARKET STATE DASHBOARD",
            f" Symbol: {snap.symbol:<12} Timeframe: {snap.timeframe.value:<8} As Of: {snap.as_of.isoformat()}",
            f" Reference Price: {_format_decimal(snap.reference_price, 4):<16} Generated: {snap.generated_at.isoformat()}",
            sep,
            "",
            " 1. DIRECTIONAL PROBABILITY & CONFIDENCE",
            sub_sep,
            f"  Bullish:  {_progress_bar(snap.probability.bullish_pct)}",
            f"  Bearish:  {_progress_bar(snap.probability.bearish_pct)}",
            f"  Neutral:  {_progress_bar(snap.probability.neutral_pct)}",
            f"  Dominant: {snap.probability.dominant_direction:<12} Edge: {_format_decimal(snap.probability.directional_edge)}%   Confidence: {_format_decimal(snap.probability.confidence_score)}%",
            f"  Reasoning: {snap.probability.reasoning or 'N/A'}",
            "",
            " 2. INSTITUTIONAL RISK ASSESSMENT & REGIME",
            sub_sep,
            f"  Risk Level:        {snap.risk.risk_level:<14} Volatility Regime: {snap.risk.volatility_regime}",
            f"  Tradeable Regime:  {'YES (ALLOW TRADE)' if snap.risk.regime_tradeable else 'NO (GATED)' :<14} Invalidation Risk: {snap.risk.invalidation_risk}",
            f"  Conflict Ratio:    {_format_decimal(snap.risk.signal_conflict_ratio):<14} Drawdown Risk:    {snap.risk.drawdown_risk}",
            f"  Suitability:       {snap.risk.position_suitability:<14} Regime Quality:   {_format_decimal(snap.risk.regime_quality_score)}",
            f"  Risk Reasoning:    {snap.risk.explanatory_reasoning or 'Risk context orderly.'}",
            "",
            " 3. MULTI-AGENT SYNTHESIS",
            sub_sep,
            f"  Directional Bias:  {snap.synthesis.directional_bias:<14} Conviction Tier:  {snap.synthesis.conviction_tier}",
            f"  Composite Conf:    {_format_decimal(snap.synthesis.composite_confidence)}%{'':<9} Actionable:       {'YES' if snap.synthesis.is_actionable else 'NO'}",
            f"  Agent Agreement:   {_format_decimal(snap.synthesis.agent_agreement_ratio * Decimal('100.0'))}%",
            f"  Evidence:          {', '.join(snap.synthesis.evidence_summary) if snap.synthesis.evidence_summary else 'None'}",
            f"  Synthesis Reason:  {snap.synthesis.final_reasoning or 'N/A'}",
            "",
            " 4. TECHNICAL INDICATORS",
            sub_sep,
            f"  EMA 9:   {_format_decimal(snap.indicators.ema_9):<12} SMA 20:   {_format_decimal(snap.indicators.sma_20):<12} RSI 14:  {_format_decimal(snap.indicators.rsi_14)}",
            f"  EMA 21:  {_format_decimal(snap.indicators.ema_21):<12} SMA 50:   {_format_decimal(snap.indicators.sma_50):<12} MACD:    {_format_decimal(snap.indicators.macd_line)}",
            f"  VWAP:    {_format_decimal(snap.indicators.vwap):<12} SMA 200:  {_format_decimal(snap.indicators.sma_200):<12} ATR 14:  {_format_decimal(snap.indicators.atr_14)}",
            f"  BB Mid:  {_format_decimal(snap.indicators.bb_middle):<12} BB Upper: {_format_decimal(snap.indicators.bb_upper):<12} BB Low:  {_format_decimal(snap.indicators.bb_lower)}",
            "",
            " 5. SMART MONEY MARKET STRUCTURE",
            sub_sep,
            f"  Swing High:     {_format_decimal(snap.structure.swing_high):<14} Swing Low:      {_format_decimal(snap.structure.swing_low)}",
            f"  Last BOS:       {snap.structure.last_bos_type or 'None':<14} BOS Price:      {_format_decimal(snap.structure.last_bos_price)}",
            f"  Last CHoCH:     {snap.structure.last_choch_type or 'None':<14} CHoCH Price:    {_format_decimal(snap.structure.last_choch_price)}",
            f"  Dealing Range:  {snap.structure.current_dealing_range or 'N/A':<14} Percentile:     {_format_decimal(snap.structure.dealing_range_percentile)}%",
            f"  Order Blocks:   {snap.structure.active_order_blocks_count:<14} Unmitigated FVG: {snap.structure.unmitigated_fvgs_count}",
            f"  Sweeps:         {', '.join(snap.structure.recent_liquidity_sweeps) if snap.structure.recent_liquidity_sweeps else 'None'}",
            "",
            " 6. EXECUTION & PORTFOLIO LEDGER",
            sub_sep,
            f"  Net Position:   {_format_decimal(snap.execution.position_qty, 4):<14} Avg Entry Price: {_format_decimal(snap.execution.average_entry_price, 4)}",
            f"  Realized PnL:   ${_format_decimal(snap.execution.realized_pnl):<13} Unrealized PnL:  ${_format_decimal(snap.execution.unrealized_pnl)}",
            f"  Open Orders:    {snap.execution.active_open_orders_count}",
        ]

        if snap.execution.active_orders:
            lines.append("  Active Open Orders:")
            for o in snap.execution.active_orders:
                lines.append(
                    f"    - ID: {o.order_id} | {o.side} {o.order_type} | Qty: {o.requested_qty} (Filled: {o.filled_qty}) | State: {o.state}"
                )

        lines.append(sep)
        return "\n".join(lines)

    @staticmethod
    def format_markdown(snap: DashboardSnapshotDTO) -> str:
        """Render a structured GitHub Flavored Markdown document."""
        md = [
            f"# Institutional Market State Report — `{snap.symbol}` [{snap.timeframe.value}]",
            "",
            f"- **Observation Point-in-Time (as_of)**: `{snap.as_of.isoformat()}`",
            f"- **Snapshot Generated**: `{snap.generated_at.isoformat()}`",
            f"- **Reference Price**: `{_format_decimal(snap.reference_price, 4)}`",
            "",
            "## 1. Directional Probability Distribution",
            "",
            "| Direction | Probability | Progress |",
            "| :--- | :--- | :--- |",
            f"| **Bullish** | `{_format_decimal(snap.probability.bullish_pct)}%` | {_progress_bar(snap.probability.bullish_pct, 15)} |",
            f"| **Bearish** | `{_format_decimal(snap.probability.bearish_pct)}%` | {_progress_bar(snap.probability.bearish_pct, 15)} |",
            f"| **Neutral** | `{_format_decimal(snap.probability.neutral_pct)}%` | {_progress_bar(snap.probability.neutral_pct, 15)} |",
            "",
            f"- **Dominant Direction**: `{snap.probability.dominant_direction}`",
            f"- **Directional Edge**: `{_format_decimal(snap.probability.directional_edge)}%`",
            f"- **Confidence Score**: `{_format_decimal(snap.probability.confidence_score)}%`",
            f"- **Analytical Reasoning**: {snap.probability.reasoning or 'N/A'}",
            "",
            "## 2. Institutional Risk & Regime Safeguards",
            "",
            "| Risk Metric | Classification / Value | Status |",
            "| :--- | :--- | :--- |",
            f"| **Risk Level** | `{snap.risk.risk_level}` | {'Safe' if snap.risk.risk_level in ('LOW', 'MODERATE') else 'Elevated'} |",
            f"| **Volatility Regime** | `{snap.risk.volatility_regime}` | {'Normal' if snap.risk.volatility_regime in ('COMPRESSED', 'NORMAL') else 'High Volatility'} |",
            f"| **Tradeable Regime** | `{snap.risk.regime_tradeable}` | {'Trade Allowed' if snap.risk.regime_tradeable else 'GATED BY RISK'} |",
            f"| **Invalidation Risk** | `{snap.risk.invalidation_risk}` | Invalidation proximity |",
            f"| **Drawdown Risk** | `{snap.risk.drawdown_risk}` | Adverse excursion risk |",
            f"| **Signal Conflict Ratio** | `{_format_decimal(snap.risk.signal_conflict_ratio)}` | Divergence factor |",
            f"| **Regime Quality** | `{_format_decimal(snap.risk.regime_quality_score)}` | Trend smoothness |",
            f"| **Position Suitability** | `{snap.risk.position_suitability}` | Suitability score |",
            "",
            f"> **Risk Reasoning**: {snap.risk.explanatory_reasoning or 'Risk context orderly.'}",
            "",
            "## 3. Multi-Agent Synthesis",
            "",
            f"- **Directional Bias**: `{snap.synthesis.directional_bias}`",
            f"- **Composite Confidence**: `{_format_decimal(snap.synthesis.composite_confidence)}%`",
            f"- **Conviction Tier**: `{snap.synthesis.conviction_tier}`",
            f"- **Agent Agreement Ratio**: `{_format_decimal(snap.synthesis.agent_agreement_ratio * Decimal('100.0'))}%`",
            f"- **Actionable**: `{'YES' if snap.synthesis.is_actionable else 'NO'}`",
            f"- **Evidence Summary**: {', '.join(snap.synthesis.evidence_summary) if snap.synthesis.evidence_summary else 'None'}",
            f"- **Synthesis Reasoning**: {snap.synthesis.final_reasoning or 'N/A'}",
            "",
            "## 4. Technical Indicators & Market Structure",
            "",
            "| Indicator | Value | Structure Element | Value |",
            "| :--- | :--- | :--- | :--- |",
            f"| **EMA 9** | `{_format_decimal(snap.indicators.ema_9)}` | **Swing High** | `{_format_decimal(snap.structure.swing_high)}` |",
            f"| **EMA 21** | `{_format_decimal(snap.indicators.ema_21)}` | **Swing Low** | `{_format_decimal(snap.structure.swing_low)}` |",
            f"| **SMA 20** | `{_format_decimal(snap.indicators.sma_20)}` | **Last BOS** | `{snap.structure.last_bos_type or 'None'} @ {_format_decimal(snap.structure.last_bos_price)}` |",
            f"| **SMA 50** | `{_format_decimal(snap.indicators.sma_50)}` | **Last CHoCH** | `{snap.structure.last_choch_type or 'None'} @ {_format_decimal(snap.structure.last_choch_price)}` |",
            f"| **RSI 14** | `{_format_decimal(snap.indicators.rsi_14)}` | **Dealing Range** | `{snap.structure.current_dealing_range or 'N/A'} ({_format_decimal(snap.structure.dealing_range_percentile)}%)` |",
            f"| **MACD** | `{_format_decimal(snap.indicators.macd_line)}` | **Active Order Blocks** | `{snap.structure.active_order_blocks_count}` |",
            f"| **ATR 14** | `{_format_decimal(snap.indicators.atr_14)}` | **Unmitigated FVGs** | `{snap.structure.unmitigated_fvgs_count}` |",
            f"| **VWAP** | `{_format_decimal(snap.indicators.vwap)}` | **Liquidity Sweeps** | `{len(snap.structure.recent_liquidity_sweeps)}` |",
            "",
            "## 5. Execution State & Portfolio Position",
            "",
            f"- **Net Position**: `{_format_decimal(snap.execution.position_qty, 4)} {snap.symbol}`",
            f"- **Average Entry Price**: `${_format_decimal(snap.execution.average_entry_price, 4)}`",
            f"- **Realized PnL**: `${_format_decimal(snap.execution.realized_pnl)}`",
            f"- **Unrealized PnL**: `${_format_decimal(snap.execution.unrealized_pnl)}`",
            f"- **Active Open Orders Count**: `{snap.execution.active_open_orders_count}`",
            "",
        ]

        if snap.execution.active_orders:
            md.extend([
                "### Active Open Orders",
                "",
                "| Order ID | Side | Type | Qty | Filled | State |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ])
            for o in snap.execution.active_orders:
                md.append(f"| `{o.order_id}` | `{o.side}` | `{o.order_type}` | `{o.requested_qty}` | `{o.filled_qty}` | `{o.state}` |")
            md.append("")

        return "\n".join(md)

    @staticmethod
    def format_json(snap: DashboardSnapshotDTO, indent: int = 2) -> str:
        """Render formatted JSON string."""
        return snap.to_json(indent=indent)

    @staticmethod
    def format_html(snap: DashboardSnapshotDTO) -> str:
        """Render a clean, responsive, dark-mode institutional HTML dashboard."""
        bull_pct = float(snap.probability.bullish_pct)
        bear_pct = float(snap.probability.bearish_pct)
        neut_pct = float(snap.probability.neutral_pct)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TradingAgents Dashboard — {snap.symbol} [{snap.timeframe.value}]</title>
  <style>
    :root {{
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --text: #c9d1d9;
      --text-muted: #8b949e;
      --accent: #58a6ff;
      --green: #3fb950;
      --red: #f85149;
      --yellow: #d29922;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 24px;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
      padding-bottom: 16px;
      margin-bottom: 24px;
    }}
    .title {{ font-size: 24px; font-weight: bold; color: #fff; }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: bold;
      font-size: 13px;
    }}
    .badge-tradeable {{ background: #238636; color: #fff; }}
    .badge-gated {{ background: #da3633; color: #fff; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 20px;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
    }}
    .card-title {{
      font-size: 16px;
      font-weight: 600;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 8px;
      color: #fff;
    }}
    .metric-row {{
      display: flex;
      justify-content: space-between;
      margin-bottom: 10px;
      font-size: 14px;
    }}
    .metric-label {{ color: var(--text-muted); }}
    .metric-val {{ font-weight: 600; }}
    .bar-container {{
      background: #21262d;
      border-radius: 4px;
      height: 12px;
      overflow: hidden;
      margin-bottom: 8px;
      display: flex;
    }}
    .bar-bull {{ background: var(--green); width: {bull_pct}%; }}
    .bar-bear {{ background: var(--red); width: {bear_pct}%; }}
    .bar-neut {{ background: var(--yellow); width: {neut_pct}%; }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <div class="title">{snap.symbol} &bull; {snap.timeframe.value}</div>
      <div style="color: var(--text-muted); font-size: 13px; margin-top: 4px;">
        As Of: {snap.as_of.isoformat()} | Ref Price: {_format_decimal(snap.reference_price, 4)}
      </div>
    </div>
    <div>
      <span class="badge {'badge-tradeable' if snap.risk.regime_tradeable else 'badge-gated'}">
        {'REGIME TRADEABLE' if snap.risk.regime_tradeable else 'GATED BY RISK'}
      </span>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-title">1. Directional Probabilities</div>
      <div class="bar-container">
        <div class="bar-bull"></div>
        <div class="bar-bear"></div>
        <div class="bar-neut"></div>
      </div>
      <div class="metric-row"><span class="metric-label">Bullish</span><span class="metric-val" style="color: var(--green);">{_format_decimal(snap.probability.bullish_pct)}%</span></div>
      <div class="metric-row"><span class="metric-label">Bearish</span><span class="metric-val" style="color: var(--red);">{_format_decimal(snap.probability.bearish_pct)}%</span></div>
      <div class="metric-row"><span class="metric-label">Neutral</span><span class="metric-val" style="color: var(--yellow);">{_format_decimal(snap.probability.neutral_pct)}%</span></div>
      <div class="metric-row"><span class="metric-label">Dominant</span><span class="metric-val">{snap.probability.dominant_direction}</span></div>
      <div class="metric-row"><span class="metric-label">Confidence</span><span class="metric-val">{_format_decimal(snap.probability.confidence_score)}%</span></div>
    </div>

    <div class="card">
      <div class="card-title">2. Risk Safeguards & Regime</div>
      <div class="metric-row"><span class="metric-label">Risk Level</span><span class="metric-val">{snap.risk.risk_level}</span></div>
      <div class="metric-row"><span class="metric-label">Volatility Regime</span><span class="metric-val">{snap.risk.volatility_regime}</span></div>
      <div class="metric-row"><span class="metric-label">Invalidation Risk</span><span class="metric-val">{snap.risk.invalidation_risk}</span></div>
      <div class="metric-row"><span class="metric-label">Signal Conflict</span><span class="metric-val">{_format_decimal(snap.risk.signal_conflict_ratio)}</span></div>
      <div class="metric-row"><span class="metric-label">Suitability</span><span class="metric-val">{snap.risk.position_suitability}</span></div>
    </div>

    <div class="card">
      <div class="card-title">3. Multi-Agent Synthesis</div>
      <div class="metric-row"><span class="metric-label">Directional Bias</span><span class="metric-val">{snap.synthesis.directional_bias}</span></div>
      <div class="metric-row"><span class="metric-label">Composite Confidence</span><span class="metric-val">{_format_decimal(snap.synthesis.composite_confidence)}%</span></div>
      <div class="metric-row"><span class="metric-label">Conviction Tier</span><span class="metric-val">{snap.synthesis.conviction_tier}</span></div>
      <div class="metric-row"><span class="metric-label">Actionable</span><span class="metric-val">{'YES' if snap.synthesis.is_actionable else 'NO'}</span></div>
      <div class="metric-row"><span class="metric-label">Agreement Ratio</span><span class="metric-val">{_format_decimal(snap.synthesis.agent_agreement_ratio * Decimal('100.0'))}%</span></div>
    </div>

    <div class="card">
      <div class="card-title">4. Position & Execution</div>
      <div class="metric-row"><span class="metric-label">Net Position</span><span class="metric-val">{_format_decimal(snap.execution.position_qty, 4)} {snap.symbol}</span></div>
      <div class="metric-row"><span class="metric-label">Avg Entry Price</span><span class="metric-val">${_format_decimal(snap.execution.average_entry_price, 4)}</span></div>
      <div class="metric-row"><span class="metric-label">Realized PnL</span><span class="metric-val">${_format_decimal(snap.execution.realized_pnl)}</span></div>
      <div class="metric-row"><span class="metric-label">Unrealized PnL</span><span class="metric-val">${_format_decimal(snap.execution.unrealized_pnl)}</span></div>
      <div class="metric-row"><span class="metric-label">Open Orders</span><span class="metric-val">{snap.execution.active_open_orders_count}</span></div>
    </div>
  </div>
</body>
</html>"""
        return html
