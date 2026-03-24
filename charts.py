"""
NansenScope — Visualization Module

Generates PNG charts from scan data using Plotly. All charts are saved
to the reports/ directory and return the file path of the saved image.
"""

import logging
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import DEFAULT_OUTPUT, Severity
from signals import Signal

log = logging.getLogger("nansenscope.charts")

CHARTS_DIR = Path("reports") / "charts"

# ── Color Palette ───────────────────────────────────────────────────────────

CHAIN_COLORS = {
    "ethereum": "#627EEA",
    "base": "#0052FF",
    "solana": "#9945FF",
    "arbitrum": "#28A0F0",
    "bnb": "#F0B90B",
    "polygon": "#8247E5",
    "optimism": "#FF0420",
    "avalanche": "#E84142",
}

SEVERITY_COLORS = {
    Severity.CRITICAL: "#FF0000",
    Severity.HIGH: "#FF8C00",
    Severity.MEDIUM: "#FFD700",
    Severity.LOW: "#808080",
}

LAYOUT_DEFAULTS = dict(
    template="plotly_dark",
    paper_bgcolor="#0D1117",
    plot_bgcolor="#161B22",
    font=dict(family="Courier New, monospace", color="#C9D1D9"),
    margin=dict(l=60, r=40, t=80, b=60),
)


# ── Chart Generators ────────────────────────────────────────────────────────

def flow_heatmap(data: dict[str, dict[str, float]]) -> str:
    """
    Generate a chain x token heatmap of netflows.

    Args:
        data: {chain: {token: netflow_usd}} mapping

    Returns:
        Path to saved PNG file.
    """
    if not data:
        log.warning("No data for flow heatmap")
        return ""

    # Collect all tokens across chains
    all_tokens: set[str] = set()
    for chain_data in data.values():
        all_tokens.update(chain_data.keys())

    tokens = sorted(all_tokens)[:30]  # Cap at 30 tokens
    chains = sorted(data.keys())

    # Build matrix
    z = []
    for chain in chains:
        row = [data.get(chain, {}).get(token, 0) for token in tokens]
        z.append(row)

    # Format hover text
    text = []
    for chain in chains:
        row = []
        for token in tokens:
            val = data.get(chain, {}).get(token, 0)
            direction = "inflow" if val >= 0 else "outflow"
            row.append(f"{chain}/{token}<br>${abs(val):,.0f} {direction}")
        text.append(row)

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=tokens,
        y=chains,
        text=text,
        hoverinfo="text",
        colorscale=[
            [0, "#FF4444"],
            [0.5, "#161B22"],
            [1, "#00FF88"],
        ],
        zmid=0,
        colorbar=dict(title="Net Flow (USD)"),
    ))

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=dict(text="Smart Money Net Flows: Chain x Token", font=dict(size=18)),
        xaxis=dict(title="Token", tickangle=45),
        yaxis=dict(title="Chain"),
        width=max(800, len(tokens) * 40),
        height=max(400, len(chains) * 80),
    )

    return _save_chart(fig, "flow_heatmap")


def signal_timeline(signals: list[Signal]) -> str:
    """
    Generate a timeline chart of signals by severity.

    Args:
        signals: List of Signal objects with timestamps.

    Returns:
        Path to saved PNG file.
    """
    if not signals:
        log.warning("No signals for timeline")
        return ""

    fig = go.Figure()

    for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
        sev_signals = [s for s in signals if s.severity == severity]
        if not sev_signals:
            continue

        fig.add_trace(go.Scatter(
            x=[s.timestamp for s in sev_signals],
            y=[s.score for s in sev_signals],
            mode="markers+text",
            name=severity.value.upper(),
            marker=dict(
                color=SEVERITY_COLORS[severity],
                size=[max(8, s.score / 5) for s in sev_signals],
                opacity=0.8,
                line=dict(width=1, color="#C9D1D9"),
            ),
            text=[s.token[:8] for s in sev_signals],
            textposition="top center",
            textfont=dict(size=9),
            hovertext=[
                f"{s.token} ({s.chain})<br>{s.type}<br>Score: {s.score:.0f}<br>{s.summary[:60]}"
                for s in sev_signals
            ],
            hoverinfo="text",
        ))

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=dict(text="Signal Timeline by Severity", font=dict(size=18)),
        xaxis=dict(title="Time"),
        yaxis=dict(title="Signal Score", range=[0, 105]),
        width=1000,
        height=500,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    return _save_chart(fig, "signal_timeline")


def chain_comparison(data: dict[str, dict[str, Any]]) -> str:
    """
    Generate a bar chart comparing SM activity across chains.

    Args:
        data: {chain: {metric: value}} — e.g. signal counts, volumes, etc.

    Returns:
        Path to saved PNG file.
    """
    if not data:
        log.warning("No data for chain comparison")
        return ""

    chains = sorted(data.keys())
    metrics = set()
    for chain_data in data.values():
        metrics.update(chain_data.keys())
    metrics = sorted(metrics)

    fig = go.Figure()

    bar_colors = ["#00FF88", "#FF8C00", "#627EEA", "#FFD700", "#FF4444"]

    for i, metric in enumerate(metrics[:5]):
        values = [data.get(chain, {}).get(metric, 0) for chain in chains]
        fig.add_trace(go.Bar(
            name=metric.replace("_", " ").title(),
            x=chains,
            y=values,
            marker_color=bar_colors[i % len(bar_colors)],
            opacity=0.85,
        ))

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=dict(text="Smart Money Activity by Chain", font=dict(size=18)),
        xaxis=dict(title="Chain"),
        yaxis=dict(title="Count / Volume"),
        barmode="group",
        width=900,
        height=500,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    return _save_chart(fig, "chain_comparison")


def wallet_treemap(holdings: list[dict[str, Any]]) -> str:
    """
    Generate a treemap of wallet positions by value.

    Args:
        holdings: List of {token, value_usd, chain} dicts.

    Returns:
        Path to saved PNG file.
    """
    if not holdings:
        log.warning("No holdings for treemap")
        return ""

    # Filter to entries with positive value
    valid = [h for h in holdings if _to_float(h.get("value_usd", 0)) > 0]
    if not valid:
        log.warning("No valid holdings for treemap")
        return ""

    # Sort by value descending, cap at 40
    valid.sort(key=lambda h: _to_float(h.get("value_usd", 0)), reverse=True)
    valid = valid[:40]

    labels = []
    parents = []
    values = []
    colors = []

    # Root
    labels.append("Portfolio")
    parents.append("")
    values.append(0)
    colors.append("#161B22")

    # Chain level
    chain_set: set[str] = set()
    for h in valid:
        chain = h.get("chain", "unknown")
        if chain not in chain_set:
            chain_set.add(chain)
            labels.append(chain.upper())
            parents.append("Portfolio")
            values.append(0)
            colors.append(CHAIN_COLORS.get(chain, "#4A5568"))

    # Token level
    for h in valid:
        token = h.get("token") or h.get("token_symbol") or h.get("symbol", "???")
        chain = h.get("chain", "unknown")
        val = _to_float(h.get("value_usd", 0))

        labels.append(f"{token}<br>${val:,.0f}")
        parents.append(chain.upper())
        values.append(val)
        colors.append(CHAIN_COLORS.get(chain, "#4A5568"))

    fig = go.Figure(go.Treemap(
        labels=labels,
        parents=parents,
        values=values,
        marker=dict(colors=colors, line=dict(width=1, color="#0D1117")),
        textinfo="label+percent parent",
        hovertemplate="<b>%{label}</b><br>Value: $%{value:,.0f}<extra></extra>",
        branchvalues="total",
    ))

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=dict(text="Smart Money Holdings Treemap", font=dict(size=18)),
        width=1000,
        height=600,
    )

    return _save_chart(fig, "wallet_treemap")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _save_chart(fig: go.Figure, name: str) -> str:
    """Save a Plotly figure as PNG and return the path."""
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHARTS_DIR / f"{name}.png"
    try:
        fig.write_image(str(path), scale=2)
        log.info("Chart saved: %s", path)
        return str(path)
    except Exception as e:
        log.error("Failed to save chart %s: %s", name, e)
        # Fallback: save as HTML
        html_path = CHARTS_DIR / f"{name}.html"
        try:
            fig.write_html(str(html_path))
            log.info("Chart saved as HTML fallback: %s", html_path)
            return str(html_path)
        except Exception as e2:
            log.error("Failed to save chart HTML %s: %s", name, e2)
            return ""


def _to_float(val: Any) -> float:
    """Safely convert to float."""
    if val is None:
        return 0.0
    try:
        return float(str(val).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return 0.0


# ── Convenience: Generate All Charts ────────────────────────────────────────

def generate_all_charts(
    scan_results: dict,
    all_signals: dict[str, list[Signal]],
) -> dict[str, str]:
    """
    Generate all available charts from scan data and signals.

    Returns dict of chart_name -> file_path.
    """
    charts: dict[str, str] = {}

    # 1. Flow heatmap from netflow data
    flow_data: dict[str, dict[str, float]] = {}
    for chain, results in scan_results.items():
        netflow_result = results.get("netflows")
        if netflow_result and hasattr(netflow_result, "success") and netflow_result.success:
            chain_flows = {}
            if isinstance(netflow_result.data, list):
                for item in netflow_result.data:
                    if isinstance(item, dict):
                        token = item.get("token_symbol") or item.get("symbol") or item.get("token", "???")
                        nf = _to_float(item.get("netflow_usd") or item.get("netflow") or item.get("net_flow", 0))
                        chain_flows[token] = nf
            if chain_flows:
                flow_data[chain] = chain_flows

    if flow_data:
        path = flow_heatmap(flow_data)
        if path:
            charts["flow_heatmap"] = path

    # 2. Signal timeline
    flat_signals = [s for sigs in all_signals.values() for s in sigs]
    if flat_signals:
        path = signal_timeline(flat_signals)
        if path:
            charts["signal_timeline"] = path

    # 3. Chain comparison
    chain_stats: dict[str, dict[str, Any]] = {}
    for chain, sigs in all_signals.items():
        chain_stats[chain] = {
            "total_signals": len(sigs),
            "critical": sum(1 for s in sigs if s.severity == Severity.CRITICAL),
            "high": sum(1 for s in sigs if s.severity == Severity.HIGH),
            "convergence": sum(1 for s in sigs if s.type == "convergence"),
        }
    if chain_stats:
        path = chain_comparison(chain_stats)
        if path:
            charts["chain_comparison"] = path

    # 4. Wallet treemap from holdings
    all_holdings: list[dict[str, Any]] = []
    for chain, results in scan_results.items():
        holdings_result = results.get("holdings")
        if holdings_result and hasattr(holdings_result, "success") and holdings_result.success:
            if isinstance(holdings_result.data, list):
                for item in holdings_result.data:
                    if isinstance(item, dict):
                        item_copy = dict(item)
                        item_copy["chain"] = chain
                        all_holdings.append(item_copy)

    if all_holdings:
        path = wallet_treemap(all_holdings)
        if path:
            charts["wallet_treemap"] = path

    log.info("Generated %d charts", len(charts))
    return charts
