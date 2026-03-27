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
    margin=dict(l=100, r=50, t=80, b=60),
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
    Generate a horizontal bar chart of top signals ranked by conviction
    (wallet count extracted from summary). Clean, readable layout.
    """
    if not signals:
        log.warning("No signals for timeline")
        return ""

    import re

    fig = go.Figure()

    # Extract wallet count from summary for sizing, sort descending
    def _extract_wallets(s):
        m = re.search(r"(\d+)\s*smart money wallet", s.summary)
        return int(m.group(1)) if m else 0

    def _extract_usd(s):
        m = re.search(r"\$([0-9,]+)", s.summary)
        return float(m.group(1).replace(",", "")) if m else 0

    # Sort by wallet count descending, take top 15
    ranked = sorted(signals, key=_extract_wallets, reverse=True)[:15]
    ranked.reverse()  # bottom-to-top for horizontal bars

    chain_colors = {
        "ethereum": "#627EEA",
        "base": "#0052FF",
        "solana": "#9945FF",
        "arbitrum": "#28A0F0",
        "bnb": "#F0B90B",
        "polygon": "#8247E5",
        "optimism": "#FF0420",
        "avalanche": "#E84142",
    }

    tokens = [f"{s.token} ({s.chain})" for s in ranked]
    wallets = [_extract_wallets(s) for s in ranked]
    colors = [chain_colors.get(s.chain, "#4ECDC4") for s in ranked]
    usd_vals = [_extract_usd(s) for s in ranked]

    fig.add_trace(go.Bar(
        y=tokens,
        x=wallets,
        orientation="h",
        marker=dict(
            color=colors,
            line=dict(width=0),
            opacity=0.9,
        ),
        text=[f"  {w} wallets — ${u:,.0f}" for w, u in zip(wallets, usd_vals)],
        textposition="inside",
        insidetextanchor="end",
        textfont=dict(size=11, color="#E0E6ED"),
        hovertext=[
            f"<b>{s.token}</b> ({s.chain})<br>"
            f"Wallets: {_extract_wallets(s)}<br>"
            f"Score: {s.score:.0f}<br>"
            f"{s.summary[:80]}"
            for s in ranked
        ],
        hoverinfo="text",
    ))

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=dict(
            text="<b>Signal Fusion</b> — Top Smart Money Signals by Conviction",
            font=dict(size=18),
        ),
        xaxis=dict(
            title="Smart Money Wallets",
            showgrid=True,
            gridcolor="rgba(150,150,150,0.15)",
        ),
        yaxis=dict(
            showgrid=False,
            tickfont=dict(size=12),
        ),
        width=1100,
        height=max(400, len(ranked) * 38 + 120),
        showlegend=False,
    )
    fig.update_layout(margin=dict(l=160, r=160, t=80, b=60))

    return _save_chart(fig, "signal_timeline")


def chain_comparison(data: dict[str, dict[str, Any]]) -> str:
    """
    Generate a horizontal bar chart comparing SM signal counts across chains.
    Only shows chains with data. Clean, readable, competition-grade.
    """
    if not data:
        log.warning("No data for chain comparison")
        return ""

    # Filter to chains with actual signals and sort by total
    chains_with_data = {c: d for c, d in data.items() if d.get("total_signals", 0) > 0}
    if not chains_with_data:
        log.warning("No chains with signals for comparison")
        return ""

    # Sort by total signals descending
    sorted_chains = sorted(chains_with_data.keys(),
                           key=lambda c: chains_with_data[c].get("total_signals", 0))

    fig = go.Figure()

    # Stacked horizontal bars: HIGH, MEDIUM, CONVERGENCE
    categories = [
        ("high", "HIGH Severity", "#FF8C00"),
        ("medium", "MEDIUM Severity", "#FFD700"),
        ("convergence", "Convergence", "#00FF88"),
        ("critical", "CRITICAL", "#FF0000"),
    ]

    for key, label, color in categories:
        values = [chains_with_data.get(c, {}).get(key, 0) for c in sorted_chains]
        if any(v > 0 for v in values):
            fig.add_trace(go.Bar(
                name=label,
                y=sorted_chains,
                x=values,
                orientation="h",
                marker_color=color,
                opacity=0.9,
                text=[str(v) if v > 0 else "" for v in values],
                textposition="inside",
                textfont=dict(size=12, color="white"),
            ))

    # Add total annotations on the right
    for chain in sorted_chains:
        total = chains_with_data[chain].get("total_signals", 0)
        fig.add_annotation(
            x=total + 0.5, y=chain,
            text=f"<b>{total}</b>",
            showarrow=False,
            font=dict(size=13, color="#C9D1D9"),
            xanchor="left",
        )

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=dict(
            text="<b>Chain Sweep</b> — Smart Money Signals by Chain",
            font=dict(size=18),
        ),
        xaxis=dict(title="Signal Count", showgrid=True,
                    gridcolor="rgba(150,150,150,0.1)"),
        yaxis=dict(title=""),
        barmode="stack",
        width=950,
        height=max(350, len(sorted_chains) * 65 + 150),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    font=dict(size=11)),
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


# ── Syndicate Bubble Map (Network Graph) ─────────────────────────────────────

SM_LABELS = {"Fund", "Smart Trader", "30D Smart Trader",
             "90D Smart Trader", "180D Smart Trader",
             "Smart HL Perps Trader"}


def _build_bubble_map_data(nodes: dict, edges: list, title: str) -> dict:
    """
    Shared computation for both PNG and HTML bubble maps.
    Returns a dict with all computed layout data, traces, and stats.
    """
    import math
    import networkx as nx

    addr_list = list(nodes.keys())
    n = len(addr_list)

    # ── Build NetworkX graph for spring layout ──
    G = nx.DiGraph()
    for addr in addr_list:
        G.add_node(addr)
    for edge in edges:
        if edge.source in nodes and edge.target in nodes:
            w = getattr(edge, 'weight', 1.0) or 1.0
            G.add_edge(edge.source, edge.target, weight=w,
                       relation=getattr(edge, 'relation', ''))

    # Spring layout with seed for reproducibility; heavier edges pull tighter
    positions = nx.spring_layout(
        G, k=2.5 / math.sqrt(max(n, 1)), iterations=80,
        seed=42, weight='weight',
    )

    # ── Pre-compute node metrics ──
    node_meta: dict[str, dict] = {}
    for addr in addr_list:
        nd = nodes[addr]
        labels = nd.labels if hasattr(nd, 'labels') else []
        is_sm = bool(SM_LABELS & set(labels))
        is_seed = hasattr(nd, 'depth') and nd.depth == 0
        conn_count = len(nd.connections) if hasattr(nd, 'connections') else 0
        pnl = nd.pnl_usd if hasattr(nd, 'pnl_usd') else 0.0

        # Size: logarithmic scaling; prefer PnL, fall back to connections
        if pnl and abs(pnl) > 0:
            raw = math.log2(abs(pnl) + 1)
            size = max(18, min(raw * 4, 70))
        else:
            size = max(18, min(math.log2(conn_count + 1) * 12 + 14, 60))
        if is_seed:
            size = max(size, 55)
        if is_sm:
            size = max(size, 35)

        # Color gradient: red (seed) -> gold (SM) -> blue (connected) -> gray (edge)
        if is_seed:
            color = "#E63946"     # vivid red
        elif is_sm:
            color = "#FFB703"     # gold
        elif conn_count >= 3:
            color = "#219EBC"     # blue (well-connected)
        else:
            color = "#8D99AE"     # gray (edge nodes)

        node_meta[addr] = dict(
            labels=labels, is_sm=is_sm, is_seed=is_seed,
            conn_count=conn_count, pnl=pnl, size=size, color=color,
        )

    # ── Edge weight map (shared counterparties proxy = edge weight) ──
    edge_weights: dict[tuple, float] = {}
    for edge in edges:
        key = (edge.source, edge.target)
        w = getattr(edge, 'weight', 1.0) or 1.0
        edge_weights[key] = edge_weights.get(key, 0) + w
    max_ew = max(edge_weights.values()) if edge_weights else 1

    # ── Cluster detection (connected components on undirected) ──
    UG = G.to_undirected()
    clusters = list(nx.connected_components(UG))
    num_clusters = len([c for c in clusters if len(c) >= 2])

    # ── Stats ──
    sm_count = sum(1 for m in node_meta.values() if m['is_sm'])
    total_pnl = sum(m['pnl'] for m in node_meta.values())

    subtitle = (f"{num_clusters} cluster{'s' if num_clusters != 1 else ''} detected"
                f" | {sm_count} Smart Money node{'s' if sm_count != 1 else ''}"
                f" | ${total_pnl:,.0f} total PnL")

    return dict(
        positions=positions, node_meta=node_meta, edge_weights=edge_weights,
        max_ew=max_ew, addr_list=addr_list, subtitle=subtitle,
        num_clusters=num_clusters, sm_count=sm_count, total_pnl=total_pnl,
        G=G,
    )


def _build_bubble_fig(nodes: dict, edges: list, title: str, data: dict) -> go.Figure:
    """Build the Plotly figure from pre-computed data."""
    import math

    positions = data['positions']
    node_meta = data['node_meta']
    edge_weights = data['edge_weights']
    max_ew = data['max_ew']
    addr_list = data['addr_list']
    subtitle = data['subtitle']

    fig = go.Figure()

    # ── Edge traces (grouped by weight for varied thickness) ──
    # Bucket edges into thin / medium / thick
    for bucket_label, lo, hi, width, opacity in [
        ("weak", 0, 0.33, 0.6, 0.15),
        ("medium", 0.33, 0.66, 1.5, 0.30),
        ("strong", 0.66, 1.01, 3.0, 0.55),
    ]:
        ex, ey = [], []
        for edge in edges:
            if edge.source not in positions or edge.target not in positions:
                continue
            key = (edge.source, edge.target)
            norm_w = edge_weights.get(key, 1) / max_ew
            if lo <= norm_w < hi:
                x0, y0 = positions[edge.source]
                x1, y1 = positions[edge.target]
                ex.extend([x0, x1, None])
                ey.extend([y0, y1, None])
        if ex:
            fig.add_trace(go.Scatter(
                x=ex, y=ey, mode="lines",
                line=dict(width=width, color=f"rgba(150,180,220,{opacity})"),
                hoverinfo="none", showlegend=False,
            ))

    # ── Arrow annotations for fund flow direction ──
    arrow_annotations = []
    for edge in edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        x0, y0 = positions[edge.source]
        x1, y1 = positions[edge.target]
        # Place arrowhead 80% along the edge (so it doesn't overlap the target node)
        frac = 0.75
        ax = x0 + frac * (x1 - x0)
        ay = y0 + frac * (y1 - y0)
        key = (edge.source, edge.target)
        norm_w = edge_weights.get(key, 1) / max_ew
        arrow_annotations.append(dict(
            ax=x0 + 0.60 * (x1 - x0), ay=y0 + 0.60 * (y1 - y0),
            x=ax, y=ay,
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True,
            arrowhead=3, arrowsize=1.2,
            arrowwidth=max(0.8, norm_w * 2.5),
            arrowcolor=f"rgba(150,180,220,{0.2 + norm_w * 0.5})",
        ))

    # ── Node trace ──
    node_x, node_y = [], []
    node_sizes, node_colors, node_text, node_hover = [], [], [], []
    label_x, label_y, label_text = [], [], []

    for addr in addr_list:
        x, y = positions[addr]
        meta = node_meta[addr]
        node_x.append(x)
        node_y.append(y)
        node_sizes.append(meta['size'])
        node_colors.append(meta['color'])

        short = f"{addr[:6]}...{addr[-4:]}"
        lbl_str = ", ".join(meta['labels'][:2]) if meta['labels'] else ""
        pnl = meta['pnl']

        hover = (f"<b>{short}</b><br>"
                 f"Labels: {', '.join(meta['labels'][:3]) or 'none'}<br>"
                 f"PnL: ${pnl:,.0f}<br>"
                 f"Connections: {meta['conn_count']}<br>"
                 f"{'SMART MONEY' if meta['is_sm'] else ''}"
                 f"{'SEED' if meta['is_seed'] else ''}")
        node_hover.append(hover)

        # Only label nodes with 3+ connections or SM/seed
        if meta['conn_count'] >= 3 or meta['is_sm'] or meta['is_seed']:
            label_x.append(x)
            label_y.append(y + meta['size'] * 0.006 + 0.04)
            tag = lbl_str if lbl_str else short
            label_text.append(tag[:20])

    # Glow effect: larger faint circle behind each node
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers",
        marker=dict(
            size=[s * 1.6 for s in node_sizes],
            color=node_colors,
            opacity=0.08,
        ),
        hoverinfo="none", showlegend=False,
    ))

    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers",
        marker=dict(
            size=node_sizes,
            color=node_colors,
            line=dict(width=1.5, color="rgba(255,255,255,0.25)"),
            opacity=0.92,
        ),
        hovertext=node_hover,
        hoverinfo="text",
        name="Wallets",
    ))

    # Label trace (separate to avoid overlap with markers)
    if label_x:
        fig.add_trace(go.Scatter(
            x=label_x, y=label_y,
            mode="text",
            text=label_text,
            textfont=dict(size=9, color="#E0E6ED",
                          family="Courier New, monospace"),
            hoverinfo="none", showlegend=False,
        ))

    # ── Legend traces ──
    for name, color in [("Seed Wallet", "#E63946"), ("Smart Money", "#FFB703"),
                        ("Connected (3+)", "#219EBC"), ("Edge Node", "#8D99AE")]:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=10, color=color, symbol="circle"),
            name=name,
        ))

    # ── Layout ──
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0B0E13",
        plot_bgcolor="#0F1318",
        font=dict(family="Courier New, monospace", color="#C9D1D9"),
        title=dict(
            text=(f"<b>{title}</b><br>"
                  f"<span style='font-size:13px;color:#8B949E'>"
                  f"{len(nodes)} nodes · {len(edges)} edges · {subtitle}</span>"),
            font=dict(size=20, color="#E6EDF3"),
            x=0.5, xanchor="center",
        ),
        showlegend=True,
        legend=dict(
            x=0.01, y=0.99, bgcolor="rgba(11,14,19,0.85)",
            bordercolor="rgba(150,180,220,0.2)", borderwidth=1,
            font=dict(color="#C9D1D9", size=11),
        ),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                    showline=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                    showline=False, scaleanchor="x"),
        margin=dict(l=20, r=20, t=90, b=30),
        annotations=arrow_annotations[:200],  # cap annotations for performance
        width=1400, height=1000,
    )

    return fig


def syndicate_bubble_map(
    nodes: dict,  # {addr: WalletNode}
    edges: list,  # [NetworkEdge]
    title: str = "Syndicate Hunter — Wallet Network Map",
) -> str:
    """
    Generate a competition-grade bubble map of wallet connections.

    Features:
    - Force-directed (spring) layout via NetworkX
    - Edge thickness proportional to relationship weight
    - Directional arrows showing fund flow
    - Logarithmic node sizing (PnL or connection count fallback)
    - Smart label placement (only high-connectivity / SM nodes)
    - Cluster & stats subtitle
    - Color gradient: red (seed) -> gold (SM) -> blue -> gray
    - Also generates interactive HTML version

    Returns path to saved PNG.
    """
    if not nodes or len(nodes) < 2:
        log.warning("Not enough nodes for bubble map")
        return ""

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    data = _build_bubble_map_data(nodes, edges, title)
    fig = _build_bubble_fig(nodes, edges, title, data)

    # Save PNG
    png_path = str(CHARTS_DIR / "syndicate_bubble_map.png")
    try:
        fig.write_image(png_path, width=1400, height=1000, scale=2)
        log.info("Syndicate bubble map PNG saved: %s", png_path)
    except Exception as e:
        log.error("Failed to write PNG: %s", e)
        png_path = ""

    # Also generate HTML interactive version
    try:
        html_path = syndicate_bubble_map_html(nodes, edges, title, _precomputed=data)
        log.info("Syndicate bubble map HTML saved: %s", html_path)
    except Exception as e:
        log.error("Failed to write HTML: %s", e)

    return png_path


def syndicate_bubble_map_html(
    nodes: dict,
    edges: list,
    title: str = "Syndicate Hunter — Wallet Network Map",
    *,
    _precomputed: dict | None = None,
) -> str:
    """
    Generate an interactive HTML bubble map with hover details.
    Judges can explore the network in-browser.

    Returns path to saved HTML file.
    """
    if not nodes or len(nodes) < 2:
        log.warning("Not enough nodes for HTML bubble map")
        return ""

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    data = _precomputed or _build_bubble_map_data(nodes, edges, title)
    fig = _build_bubble_fig(nodes, edges, title, data)

    # Enhance for interactive: bigger hover labels, zoom/pan instructions
    fig.update_layout(
        dragmode="pan",
        modebar=dict(bgcolor="rgba(0,0,0,0)", color="#8B949E",
                     activecolor="#FFB703"),
    )

    html_path = str(CHARTS_DIR / "syndicate_bubble_map.html")
    try:
        fig.write_html(
            html_path,
            include_plotlyjs="cdn",
            full_html=True,
            config={"scrollZoom": True, "displayModeBar": True},
        )
    except Exception as e:
        log.error("Failed to write HTML: %s", e)
        return ""

    return html_path
