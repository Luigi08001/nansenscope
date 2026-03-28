"""
NansenScope — Interactive Local Dashboard

Generates a self-contained HTML dashboard matching the landing page aesthetic.
Embeds charts as base64, includes an inline Canvas network map with force
simulation, signal table with chain filters, and the full intelligence report.
"""

import base64
import json
import logging
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

REPORTS_DIR = Path("reports")
CHARTS_DIR = REPORTS_DIR / "charts"
DASHBOARD_PATH = REPORTS_DIR / "dashboard.html"


def _img_to_base64(path: Path) -> str:
    if not path.exists():
        return ""
    data = base64.b64encode(path.read_bytes()).decode()
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/svg+xml" if suffix == ".svg" else "image/jpeg"
    return f"data:{mime};base64,{data}"


def _load_latest_results() -> dict:
    path = REPORTS_DIR / "latest_results.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _load_latest_report() -> str:
    reports = sorted(REPORTS_DIR.glob("daily_*.md"), reverse=True)
    if not reports:
        reports = sorted(REPORTS_DIR.glob("scan_*.md"), reverse=True)
    if reports:
        return reports[0].read_text()
    return ""


def _build_chain_filters(signals: list) -> str:
    chains = sorted(set(s.get("chain", "") for s in signals))
    buttons = []
    for c in chains:
        buttons.append(
            f'<button class="filter-btn" onclick="filterSignals(\'{c}\', this)">{c.title()}</button>'
        )
    return "".join(buttons)


def _build_signal_rows(signals: list) -> str:
    max_score = max((s.get("score", 0) for s in signals), default=1) or 1
    rows = ""
    for i, s in enumerate(signals, 1):
        sev = s.get("severity", "high").upper()
        sev_class = sev.lower()
        summary = s.get("summary", "")[:100].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        token = s.get("token", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        score = s.get("score", 0)
        bar_w = int((score / max_score) * 100) if max_score else 0
        delay = f"transition-delay: {0.04 * i:.2f}s;"
        rows += f"""
        <tr class="signal-row" data-chain="{s.get('chain','')}" data-severity="{sev.lower()}" style="position:relative;{delay}">
            <td class="row-num">{i}</td>
            <td><span class="sev-badge {sev_class}">{sev}</span></td>
            <td><span class="chain-pill">{s.get('chain','')}</span></td>
            <td class="token">{token}</td>
            <td class="type">{s.get('type','').replace('_',' ').title()}</td>
            <td class="summary">{summary}</td>
            <td class="score">{score:.0f}</td>
            <td style="position:absolute;left:0;top:0;right:0;bottom:0;padding:0;border:none;pointer-events:none;"><div class="vp-row-bar" data-width="{bar_w}" style="--bar-w:{bar_w};"></div></td>
        </tr>"""
    return rows


def _build_chain_cards(results: dict) -> str:
    chain_summary = results.get("chain_summary", [])
    cards = ""
    chain_colors = {
        "ethereum": "#627EEA", "base": "#0052FF", "solana": "#9945FF",
        "arbitrum": "#28A0F0", "bnb": "#F0B90B", "polygon": "#8247E5",
        "optimism": "#FF0420", "avalanche": "#E84142",
    }
    if isinstance(chain_summary, list):
        for cs in chain_summary:
            if isinstance(cs, dict):
                chain = cs.get("chain", "")
                color = chain_colors.get(chain, "#00E5A0")
                count = cs.get("total_signals", 0)
                cards += f"""
                <div class="chain-card" style="border-color: {color}40">
                    <div class="chain-dot" style="background: {color}"></div>
                    <div class="chain-info">
                        <div class="chain-name">{chain.upper()}</div>
                        <div class="chain-count">{count} signals</div>
                    </div>
                </div>"""
    return cards


def generate_dashboard(auto_open: bool = True) -> Path:
    results = _load_latest_results()
    report_md = _load_latest_report()

    timeline_b64 = _img_to_base64(CHARTS_DIR / "signal_timeline.png")
    comparison_b64 = _img_to_base64(CHARTS_DIR / "chain_comparison.png")
    bubble_b64 = _img_to_base64(CHARTS_DIR / "syndicate_bubble_map.png")

    signals = results.get("signals", [])
    chains_scanned = results.get("chains", [])
    total_signals = results.get("total_signals", len(signals))
    timestamp = results.get("timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    signal_rows = _build_signal_rows(signals)
    chain_filters = _build_chain_filters(signals)
    chain_cards = _build_chain_cards(results)

    high_count = len([s for s in signals if s.get("severity") in ("high", "critical")])
    unique_tokens = len(set(s.get("token", "") for s in signals))
    chain_count = len(chains_scanned) if isinstance(chains_scanned, list) else 0
    chains_str = ", ".join(chains_scanned) if isinstance(chains_scanned, list) else str(chains_scanned)

    report_escaped = (report_md
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NansenScope — Intelligence Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background: #060B14;
            color: #E8ECF2;
            min-height: 100vh;
            overflow-x: hidden;
        }}

        /* Intel grid background */
        .intel-grid {{
            position: fixed; inset: 0; pointer-events: none; z-index: 0; overflow: hidden;
        }}
        .intel-grid::before {{
            content: '';
            position: absolute; inset: 0;
            background-image:
                linear-gradient(rgba(0,229,160,0.025) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0,229,160,0.025) 1px, transparent 1px);
            background-size: 60px 60px;
        }}
        .intel-grid::after {{
            content: '';
            position: absolute; inset: 0;
            background: radial-gradient(ellipse at 50% 0%, rgba(0,229,160,0.04) 0%, transparent 50%),
                        radial-gradient(ellipse at 80% 80%, rgba(100,117,246,0.03) 0%, transparent 40%);
        }}

        /* Scan line */
        .scan-line {{
            position: fixed;
            top: 0; left: 0; right: 0;
            height: 2px;
            background: linear-gradient(90deg, transparent, rgba(0,229,160,0.4), transparent);
            animation: scanDown 8s ease-in-out infinite;
            z-index: 1;
            pointer-events: none;
        }}
        @keyframes scanDown {{
            0% {{ top: 0; opacity: 0; }}
            10% {{ opacity: 1; }}
            90% {{ opacity: 1; }}
            100% {{ top: 100%; opacity: 0; }}
        }}

        .wrapper {{ position: relative; z-index: 2; }}

        /* Header */
        .header {{
            padding: 32px 48px 24px;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 1px solid #1A2940;
        }}
        .header-left h1 {{
            font-size: 28px;
            font-weight: 800;
            letter-spacing: -0.5px;
        }}
        .header-left h1 .accent {{ color: #00E5A0; }}
        .header-left h1 .dim {{ color: #8895A7; font-weight: 500; }}
        .header-meta {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: #8895A7;
            margin-top: 6px;
        }}
        .header-meta .green {{ color: #00E5A0; }}
        .header-right {{ display: flex; gap: 8px; align-items: flex-start; }}
        .status-badge {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            padding: 4px 12px;
            border-radius: 4px;
            background: rgba(0,229,160,0.1);
            border: 1px solid rgba(0,229,160,0.2);
            color: #00E5A0;
            animation: livePulse 2s ease-in-out infinite;
        }}
        @keyframes livePulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.6; }}
        }}

        /* Stats bar */
        .stats {{
            display: flex;
            gap: 0;
            padding: 0 48px;
            border-bottom: 1px solid #1A2940;
        }}
        .stat {{
            flex: 1;
            padding: 20px 0;
            text-align: center;
            border-right: 1px solid #1A2940;
        }}
        .stat:last-child {{ border-right: none; }}
        .stat-value {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 36px;
            font-weight: 700;
            color: #00E5A0;
            line-height: 1;
        }}
        .stat-value.white {{ color: #E8ECF2; }}
        .stat-label {{
            font-size: 11px;
            color: #8895A7;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-top: 6px;
        }}

        /* Chain cards */
        .chain-bar {{
            display: flex;
            gap: 12px;
            padding: 20px 48px;
            border-bottom: 1px solid #1A2940;
            overflow-x: auto;
        }}
        .chain-card {{
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(26,41,64,0.4);
            border: 1px solid #1A2940;
            border-radius: 8px;
            padding: 10px 16px;
            min-width: 140px;
            transition: border-color 0.2s, background 0.2s;
        }}
        .chain-card:hover {{
            border-color: #00E5A040;
            background: rgba(0,229,160,0.03);
        }}
        .chain-dot {{
            width: 8px; height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
        }}
        .chain-name {{
            font-weight: 700;
            font-size: 13px;
            color: #E8ECF2;
        }}
        .chain-count {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            color: #8895A7;
        }}

        /* Content area */
        .content {{ padding: 28px 48px; }}

        /* Tabs */
        .tab-bar {{
            display: flex;
            gap: 0;
            border-bottom: 1px solid #1A2940;
            margin-bottom: 24px;
        }}
        .tab {{
            font-family: 'Inter', sans-serif;
            padding: 12px 24px;
            cursor: pointer;
            color: #8895A7;
            border: none;
            border-bottom: 2px solid transparent;
            font-size: 13px;
            font-weight: 500;
            background: none;
            transition: all 0.2s;
        }}
        .tab:hover {{ color: #E8ECF2; }}
        .tab.active {{
            color: #00E5A0;
            border-bottom-color: #00E5A0;
        }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}

        /* Filters */
        .filters {{
            display: flex;
            gap: 8px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        .filter-btn {{
            font-family: 'JetBrains Mono', monospace;
            background: rgba(26,41,64,0.4);
            border: 1px solid #1A2940;
            color: #8895A7;
            padding: 6px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
            transition: all 0.2s;
        }}
        .filter-btn:hover, .filter-btn.active {{
            background: rgba(0,229,160,0.1);
            color: #00E5A0;
            border-color: rgba(0,229,160,0.3);
        }}

        /* Signal table */
        .table-wrap {{
            border: 1px solid #1A2940;
            border-radius: 8px;
            overflow: hidden;
        }}
        .signal-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        .signal-table th {{
            background: rgba(26,41,64,0.6);
            color: #8895A7;
            padding: 12px 14px;
            text-align: left;
            font-weight: 600;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
            cursor: pointer;
            user-select: none;
            transition: color 0.2s;
        }}
        .signal-table th:hover {{ color: #00E5A0; }}
        .signal-table th .sort-arrow {{ opacity: 0.3; margin-left: 4px; font-size: 9px; }}
        .signal-table th.sorted .sort-arrow {{ opacity: 1; color: #00E5A0; }}
        .signal-table td {{
            padding: 10px 14px;
            border-bottom: 1px solid #1A294040;
        }}
        .signal-row {{ transition: background 0.15s; }}
        .signal-row:hover {{ background: rgba(0,229,160,0.03); }}
        .row-num {{
            font-family: 'JetBrains Mono', monospace;
            color: #8895A7;
            font-size: 11px;
        }}
        .sev-badge {{
            font-family: 'JetBrains Mono', monospace;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: 600;
        }}
        .sev-badge.critical {{ background: rgba(229,72,77,0.15); color: #FF6369; border: 1px solid rgba(229,72,77,0.3); }}
        .sev-badge.high {{ background: rgba(245,166,35,0.12); color: #F5A623; border: 1px solid rgba(245,166,35,0.25); }}
        .sev-badge.medium {{ background: rgba(255,215,0,0.1); color: #FFD700; border: 1px solid rgba(255,215,0,0.2); }}
        .sev-badge.low {{ background: rgba(0,229,160,0.1); color: #00E5A0; border: 1px solid rgba(0,229,160,0.2); }}
        .chain-pill {{
            font-family: 'JetBrains Mono', monospace;
            background: rgba(26,41,64,0.6);
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 11px;
            color: #8895A7;
        }}
        .token {{
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            color: #E8ECF2;
        }}
        .type {{ color: #8895A7; font-size: 12px; }}
        .summary {{ color: #8895A7; max-width: 360px; font-size: 12px; }}
        .score {{
            font-family: 'JetBrains Mono', monospace;
            font-weight: 700;
            color: #00E5A0;
        }}

        /* Charts */
        .charts-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
        }}
        .chart-card {{
            background: rgba(26,41,64,0.3);
            border: 1px solid #1A2940;
            border-radius: 8px;
            overflow: hidden;
        }}
        .chart-card h3 {{
            font-family: 'JetBrains Mono', monospace;
            padding: 14px 20px;
            font-size: 13px;
            color: #00E5A0;
            font-weight: 500;
            border-bottom: 1px solid #1A2940;
        }}
        .chart-card img {{
            width: 100%;
            display: block;
        }}
        .charts-2col {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}

        /* Network map container */
        #network-map-container {{
            position: relative;
            width: 100%;
            height: 520px;
            background: rgba(26,41,64,0.15);
            border: 1px solid #1A2940;
            border-radius: 8px;
            overflow: hidden;
            cursor: grab;
        }}
        #network-canvas {{
            display: block;
            width: 100%;
            height: 100%;
        }}
        #net-tooltip {{
            display: none;
            position: absolute;
            background: rgba(12,20,32,0.95);
            border: 1px solid #1A2940;
            border-radius: 6px;
            padding: 8px 12px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            color: #E8ECF2;
            pointer-events: none;
            z-index: 20;
            max-width: 250px;
            line-height: 1.5;
            backdrop-filter: blur(8px);
        }}
        .net-controls {{
            display: flex;
            gap: 6px;
            margin-bottom: 12px;
        }}
        .net-btn {{
            font-family: 'JetBrains Mono', monospace;
            background: rgba(26,41,64,0.5);
            border: 1px solid #1A2940;
            color: #8895A7;
            padding: 5px 14px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
            transition: all 0.2s;
        }}
        .net-btn:hover {{
            background: rgba(0,229,160,0.1);
            color: #00E5A0;
            border-color: rgba(0,229,160,0.3);
        }}
        .net-legend {{
            display: flex;
            gap: 16px;
            margin-top: 12px;
            flex-wrap: wrap;
        }}
        .net-legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 10px;
            color: #8895A7;
        }}
        .net-legend-dot {{
            width: 8px; height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
        }}
        .net-legend-sq {{
            width: 8px; height: 8px;
            border-radius: 2px;
            flex-shrink: 0;
        }}

        /* Report */
        .report-pre {{
            font-family: 'JetBrains Mono', monospace;
            white-space: pre-wrap;
            line-height: 1.7;
            color: #C9D1D9;
            font-size: 12px;
            background: rgba(26,41,64,0.3);
            border: 1px solid #1A2940;
            border-radius: 8px;
            padding: 24px;
            max-height: 70vh;
            overflow-y: auto;
        }}
        .report-pre::-webkit-scrollbar {{ width: 6px; }}
        .report-pre::-webkit-scrollbar-track {{ background: transparent; }}
        .report-pre::-webkit-scrollbar-thumb {{ background: #1A2940; border-radius: 3px; }}

        /* Footer */
        .footer {{
            padding: 24px 48px;
            border-top: 1px solid #1A2940;
            color: #8895A7;
            font-size: 11px;
            text-align: center;
            font-family: 'JetBrains Mono', monospace;
        }}
        .footer .accent {{ color: #00E5A0; }}

        /* No-data placeholder */
        .no-data {{
            color: #8895A7;
            padding: 60px 40px;
            text-align: center;
            font-size: 14px;
        }}
        .no-data code {{
            color: #00E5A0;
            font-family: 'JetBrains Mono', monospace;
            background: rgba(0,229,160,0.08);
            padding: 2px 6px;
            border-radius: 3px;
        }}

        /* --- Visual Panel Animations --- */
        .vp-stat-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }}
        .vp-stat-box {{
            background: rgba(26,41,64,0.3); border: 1px solid #1A2940; border-radius: 10px;
            padding: 16px; text-align: center;
            opacity: 0; transform: translateY(15px);
            transition: opacity 0.5s ease, transform 0.5s ease;
        }}
        .tab-content.animate .vp-stat-box {{ opacity: 1; transform: translateY(0); }}
        .tab-content.animate .vp-stat-box:nth-child(1) {{ transition-delay: 0s; }}
        .tab-content.animate .vp-stat-box:nth-child(2) {{ transition-delay: 0.08s; }}
        .tab-content.animate .vp-stat-box:nth-child(3) {{ transition-delay: 0.16s; }}
        .tab-content.animate .vp-stat-box:nth-child(4) {{ transition-delay: 0.24s; }}
        .vp-stat-val {{
            font-family: 'JetBrains Mono', monospace; font-size: 28px; font-weight: 800;
            color: #00E5A0; line-height: 1;
        }}
        .vp-stat-label {{
            font-family: 'JetBrains Mono', monospace; font-size: 11px;
            color: #8895A7; margin-top: 6px;
        }}
        .signal-row {{
            transition: background 0.15s, opacity 0.4s ease, transform 0.4s ease;
            opacity: 0; transform: translateX(-20px);
        }}
        .tab-content.animate .signal-row {{
            opacity: 1; transform: translateX(0);
        }}
        .signal-row td {{ position: relative; z-index: 1; }}
        .signal-row .vp-row-bar {{
            position: absolute; left: 0; top: 0; bottom: 0; width: 0;
            background: linear-gradient(90deg, rgba(0,229,160,0.08), rgba(0,229,160,0.03));
            transition: width 1s ease 0.3s;
            border-right: 2px solid rgba(0,229,160,0.15);
            z-index: 0;
        }}
        .tab-content.animate .signal-row .vp-row-bar {{
            width: calc(var(--bar-w, 0) * 1%);
        }}

        /* Responsive */
        @media (max-width: 768px) {{
            .stats {{ flex-wrap: wrap; }}
            .stat {{ min-width: 50%; }}
            .charts-2col {{ grid-template-columns: 1fr; }}
            .content, .header, .stats, .chain-bar {{ padding-left: 20px; padding-right: 20px; }}
            #network-map-container {{ height: 380px; }}
        }}
    </style>
</head>
<body>
    <div class="intel-grid"></div>
    <div class="scan-line"></div>

    <div class="wrapper">
        <!-- HEADER -->
        <div class="header">
            <div class="header-left">
                <h1><span class="accent">Nansen</span>Scope <span class="dim">Dashboard</span></h1>
                <div class="header-meta">
                    <span class="green">SCAN COMPLETE</span> &mdash; {timestamp} &mdash; Chains: {chains_str}
                </div>
            </div>
            <div class="header-right">
                <div class="status-badge">LIVE DATA</div>
            </div>
        </div>

        <!-- STATS BAR -->
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{total_signals}</div>
                <div class="stat-label">Signals Detected</div>
            </div>
            <div class="stat">
                <div class="stat-value white">{chain_count}</div>
                <div class="stat-label">Chains Scanned</div>
            </div>
            <div class="stat">
                <div class="stat-value">{high_count}</div>
                <div class="stat-label">High Priority</div>
            </div>
            <div class="stat">
                <div class="stat-value white">{unique_tokens}</div>
                <div class="stat-label">Unique Tokens</div>
            </div>
        </div>

        <!-- CHAIN CARDS -->
        <div class="chain-bar">
            {chain_cards}
        </div>

        <!-- TABBED CONTENT -->
        <div class="content">
            <div class="tab-bar">
                <button class="tab active" onclick="showTab('signals', this)">Signals</button>
                <button class="tab" onclick="showTab('charts', this)">Charts</button>
                <button class="tab" onclick="showTab('network', this)">Network Map</button>
                <button class="tab" onclick="showTab('report', this)">Full Report</button>
            </div>

            <!-- TAB: Signals -->
            <div id="tab-signals" class="tab-content active animate">
                <div class="vp-stat-grid">
                    <div class="vp-stat-box">
                        <div class="vp-stat-val" data-count-to="{total_signals}">0</div>
                        <div class="vp-stat-label">Total Signals</div>
                    </div>
                    <div class="vp-stat-box">
                        <div class="vp-stat-val" data-count-to="{chain_count}">0</div>
                        <div class="vp-stat-label">Chains</div>
                    </div>
                    <div class="vp-stat-box">
                        <div class="vp-stat-val" data-count-to="{high_count}">0</div>
                        <div class="vp-stat-label">High Priority</div>
                    </div>
                    <div class="vp-stat-box">
                        <div class="vp-stat-val" data-count-to="{unique_tokens}">0</div>
                        <div class="vp-stat-label">Unique Tokens</div>
                    </div>
                </div>
                <div class="filters">
                    <button class="filter-btn active" onclick="filterSignals('all', this)">All</button>
                    {chain_filters}
                </div>
                <div class="table-wrap">
                    <table class="signal-table">
                        <thead>
                            <tr>
                                <th onclick="sortTable(0)"># <span class="sort-arrow">&#9650;</span></th>
                                <th onclick="sortTable(1)">Severity <span class="sort-arrow">&#9650;</span></th>
                                <th onclick="sortTable(2)">Chain <span class="sort-arrow">&#9650;</span></th>
                                <th onclick="sortTable(3)">Token <span class="sort-arrow">&#9650;</span></th>
                                <th onclick="sortTable(4)">Type <span class="sort-arrow">&#9650;</span></th>
                                <th onclick="sortTable(5)">Signal <span class="sort-arrow">&#9650;</span></th>
                                <th onclick="sortTable(6)">Score <span class="sort-arrow">&#9650;</span></th>
                            </tr>
                        </thead>
                        <tbody id="signal-tbody">
                            {signal_rows}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TAB: Charts -->
            <div id="tab-charts" class="tab-content">
                {"<div class='charts-grid'><div class='chart-card'><h3>Signal Fusion &mdash; Top Signals by Conviction</h3><img src='" + timeline_b64 + "'></div></div>" if timeline_b64 else "<div class='no-data'>No signal timeline chart found.<br>Run <code>nansenscope charts</code> to generate.</div>"}
                <div class="charts-2col" style="margin-top: 20px;">
                    {"<div class='chart-card'><h3>Chain Comparison</h3><img src='" + comparison_b64 + "'></div>" if comparison_b64 else ""}
                    {"<div class='chart-card'><h3>Syndicate Bubble Map</h3><img src='" + bubble_b64 + "'></div>" if bubble_b64 else ""}
                </div>
            </div>

            <!-- TAB: Network Map (inline Canvas) -->
            <div id="tab-network" class="tab-content">
                <div class="net-controls">
                    <button class="net-btn" onclick="netZoom(1.3)">Zoom +</button>
                    <button class="net-btn" onclick="netZoom(0.7)">Zoom -</button>
                    <button class="net-btn" onclick="netReset()">Reset View</button>
                </div>
                <div id="network-map-container">
                    <canvas id="network-canvas"></canvas>
                    <div id="net-tooltip"></div>
                </div>
                <div class="net-legend">
                    <div class="net-legend-item"><div class="net-legend-dot" style="background:#00E5A0"></div> Hub / Smart Money</div>
                    <div class="net-legend-item"><div class="net-legend-dot" style="background:#F5A623"></div> Fund Deployer</div>
                    <div class="net-legend-item"><div class="net-legend-dot" style="background:#4B5563"></div> Known Wallet</div>
                    <div class="net-legend-item"><div class="net-legend-sq" style="background:#A855F7"></div> Exchange / DEX</div>
                    <div class="net-legend-item"><div class="net-legend-dot" style="background:#374151; width:5px; height:5px;"></div> Peripheral</div>
                </div>
            </div>

            <!-- TAB: Full Report -->
            <div id="tab-report" class="tab-content">
                {"<pre class='report-pre'>" + report_escaped + "</pre>" if report_escaped else "<div class='no-data'>No report available.<br>Run <code>nansenscope daily --chains ethereum,base,solana</code> to generate.</div>"}
            </div>
        </div>

        <!-- FOOTER -->
        <div class="footer">
            <span class="accent">NansenScope</span> v2.0 &mdash; Autonomous Smart Money Intelligence &mdash; Built with Nansen CLI + x402
        </div>
    </div>

    <script>
    /* ---- Animated counters ---- */
    function animateCounters(panel) {{
        panel.querySelectorAll('[data-count-to]').forEach(function(el) {{
            var target = parseInt(el.dataset.countTo, 10);
            var prefix = el.dataset.prefix || '';
            var suffix = el.dataset.suffix || '';
            if (isNaN(target) || target === 0) {{ el.textContent = prefix + '0' + suffix; return; }}
            var start = null;
            var duration = 1200;
            function easeOut(t) {{ return 1 - Math.pow(1 - t, 3); }}
            function step(ts) {{
                if (!start) start = ts;
                var progress = Math.min((ts - start) / duration, 1);
                var current = Math.floor(easeOut(progress) * target);
                el.textContent = prefix + current.toLocaleString() + suffix;
                if (progress < 1) requestAnimationFrame(step);
                else el.textContent = prefix + target.toLocaleString() + suffix;
            }}
            requestAnimationFrame(step);
        }});
    }}

    /* ---- Animated bars ---- */
    function animateBars(panel) {{
        panel.querySelectorAll('[data-width]').forEach(function(el) {{
            var w = el.dataset.width;
            el.style.width = '0';
            requestAnimationFrame(function() {{
                requestAnimationFrame(function() {{
                    el.style.width = w + '%';
                }});
            }});
        }});
    }}

    /* ---- Tab switching ---- */
    function showTab(name, el) {{
        /* Remove animate + active from all tabs */
        document.querySelectorAll('.tab-content').forEach(function(t) {{
            t.classList.remove('active', 'animate');
        }});
        document.querySelectorAll('.tab').forEach(function(t) {{ t.classList.remove('active'); }});

        var panel = document.getElementById('tab-' + name);
        panel.classList.add('active');
        el.classList.add('active');

        /* Set --bar-w on row bars */
        panel.querySelectorAll('.vp-row-bar').forEach(function(bar) {{
            bar.style.setProperty('--bar-w', bar.dataset.width || '0');
        }});

        /* Reset bars to 0 before animating */
        panel.querySelectorAll('[data-width]').forEach(function(bar) {{ bar.style.width = '0'; }});

        /* Force reflow then animate */
        void panel.offsetHeight;
        panel.classList.add('animate');

        animateCounters(panel);
        animateBars(panel);

        if (name === 'network') {{ setTimeout(initNetworkGraph, 60); }}
    }}

    /* ---- Chain filter ---- */
    function filterSignals(chain, el) {{
        document.querySelectorAll('.filter-btn').forEach(function(b) {{ b.classList.remove('active'); }});
        if (el) el.classList.add('active');
        document.querySelectorAll('.signal-row').forEach(function(row) {{
            row.style.display = (chain === 'all' || row.dataset.chain === chain) ? '' : 'none';
        }});
    }}

    /* ---- Column sorting ---- */
    var sortDir = {{}};
    function sortTable(col) {{
        var tbody = document.getElementById('signal-tbody');
        var rows = Array.from(tbody.querySelectorAll('tr'));
        sortDir[col] = !sortDir[col];
        var dir = sortDir[col] ? 1 : -1;
        rows.sort(function(a, b) {{
            var at = a.children[col].textContent.trim();
            var bt = b.children[col].textContent.trim();
            var an = parseFloat(at), bn = parseFloat(bt);
            if (!isNaN(an) && !isNaN(bn)) return (an - bn) * dir;
            return at.localeCompare(bt) * dir;
        }});
        rows.forEach(function(r) {{ tbody.appendChild(r); }});
        document.querySelectorAll('.signal-table th').forEach(function(th, i) {{
            th.classList.toggle('sorted', i === col);
            var arrow = th.querySelector('.sort-arrow');
            if (arrow) arrow.innerHTML = (i === col && sortDir[col]) ? '&#9660;' : '&#9650;';
        }});
    }}

    /* ---- Initial animation on load ---- */
    document.addEventListener('DOMContentLoaded', function() {{
        var panel = document.getElementById('tab-signals');
        if (panel) {{
            panel.querySelectorAll('.vp-row-bar').forEach(function(bar) {{
                bar.style.setProperty('--bar-w', bar.dataset.width || '0');
            }});
            panel.querySelectorAll('[data-width]').forEach(function(bar) {{ bar.style.width = '0'; }});
            void panel.offsetHeight;
            panel.classList.add('animate');
            animateCounters(panel);
            animateBars(panel);
        }}
    }});

    /* ========================================================
       INLINE CANVAS NETWORK MAP — force-directed graph
       Ported from NansenScope landing page (docs/index.html)
       ======================================================== */
    var _networkInitialized = false;

    function netZoom(factor) {{
        if (typeof window._netZoom === 'function') window._netZoom(factor);
    }}
    function netReset() {{
        if (typeof window._netReset === 'function') window._netReset();
    }}

    function initNetworkGraph() {{
        if (_networkInitialized) return;
        var canvas = document.getElementById('network-canvas');
        if (!canvas) return;
        var container = document.getElementById('network-map-container');
        if (!container || container.offsetWidth < 10) return;
        _networkInitialized = true;

        var tt = document.getElementById('net-tooltip');
        var ctx = canvas.getContext('2d');
        var dpr = window.devicePixelRatio || 1;
        var W = container.offsetWidth || 900;
        var H = container.offsetHeight || 520;
        var initialized = false;

        function resize() {{
            var rect = container.getBoundingClientRect();
            if (rect.width > 10 && rect.height > 10) {{
                var oldW = W, oldH = H;
                W = rect.width; H = rect.height;
                if (initialized && oldW > 10) {{
                    var sx = W / oldW, sy = H / oldH;
                    nodes.forEach(function(n) {{ n.x *= sx; n.y *= sy; }});
                }}
            }}
            canvas.width = W * dpr; canvas.height = H * dpr;
            canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }}

        function rAddr() {{
            return '0x' + Array.from({{length: 4}}, function() {{
                return Math.floor(Math.random() * 65536).toString(16).padStart(4, '0');
            }}).join('').slice(0, 4) + '...' + Math.floor(Math.random() * 65536).toString(16).padStart(4, '0');
        }}

        var nodes = [];
        var edges = [];
        var CX = W / 2, CY = H / 2;

        /* Hub nodes */
        var hub1X = CX - 120, hub1Y = CY;
        var hub2X = CX + 120, hub2Y = CY;
        nodes.push({{id:0, x:hub1X, y:hub1Y, vx:0, vy:0, r:16, label:'DeFi Whale #1', color:'#00E5A0', type:'hub', cluster:1, detail:'Accumulated $2.1M across 47 tokens'}});
        nodes.push({{id:1, x:hub2X, y:hub2Y, vx:0, vy:0, r:14, label:'Fund Deployer', color:'#F5A623', type:'hub', cluster:0, detail:'Deployed $450K to 4 wallets'}});

        /* Smart Money ring */
        var smLabels = [
            {{name:'DEX Buyer', detail:'$340K profit', cl:1}},
            {{name:'Yield Farmer', detail:'$1.2M deposited', cl:1}},
            {{name:'NFT Flipper', detail:'$890K PnL', cl:1}},
            {{name:'MEV Searcher', detail:'$45K/week', cl:1}},
            {{name:'DAO Treasury', detail:'8 DAOs', cl:0}},
            {{name:'Accumulator', detail:'18mo DCA', cl:0}}
        ];
        var smR = 80;
        var sm1 = smLabels.filter(function(s){{return s.cl===1;}});
        var sm0 = smLabels.filter(function(s){{return s.cl===0;}});

        sm1.forEach(function(s, i) {{
            var angle = (i / sm1.length) * Math.PI * 2 - Math.PI / 2;
            nodes.push({{id:nodes.length, x:hub1X+Math.cos(angle)*smR, y:hub1Y+Math.sin(angle)*smR, vx:0, vy:0, r:7, label:s.name, color:'#00E5A0', type:'sm', cluster:1, detail:s.detail}});
            edges.push({{s:0, t:nodes.length-1, type:'hub-sm'}});
        }});
        sm0.forEach(function(s, i) {{
            var angle = (i / sm0.length) * Math.PI * 2 - Math.PI / 2;
            nodes.push({{id:nodes.length, x:hub2X+Math.cos(angle)*smR, y:hub2Y+Math.sin(angle)*smR, vx:0, vy:0, r:7, label:s.name, color:'#00E5A0', type:'sm', cluster:0, detail:s.detail}});
            edges.push({{s:1, t:nodes.length-1, type:'hub-sm'}});
        }});

        /* Known wallets ring */
        var knownLabels = ['LP Provider','Staker','Bridge User','Holder','Hunter','Multi-Sig','Funder','Bot Wallet','OTC Desk','Mixer','Cold Storage','Hot Wallet','DAO Voter','Claimer','Liquidator','Flash Loan','Relayer','Gas Funder','Deployer','Admin Key'];
        var knownR1 = 150, knownR0 = 140;
        var known1 = knownLabels.slice(0, 12), known0 = knownLabels.slice(12);

        known1.forEach(function(lbl, i) {{
            var angle = (i / known1.length) * Math.PI * 2 - Math.PI / 4;
            nodes.push({{id:nodes.length, x:hub1X+Math.cos(angle)*knownR1, y:hub1Y+Math.sin(angle)*knownR1, vx:0, vy:0, r:4.5, label:lbl, color:'#4B5563', type:'known', cluster:1, detail:'Linked via on-chain transfers'}});
            edges.push({{s:0, t:nodes.length-1, type:'hub-known'}});
            if (Math.random() < 0.4) {{
                var smPool = nodes.filter(function(n){{return n.type==='sm' && n.cluster===1;}});
                if (smPool.length) edges.push({{s:smPool[Math.floor(Math.random()*smPool.length)].id, t:nodes.length-1, type:'hub-known'}});
            }}
        }});
        known0.forEach(function(lbl, i) {{
            var angle = (i / known0.length) * Math.PI * 2 + Math.PI / 4;
            nodes.push({{id:nodes.length, x:hub2X+Math.cos(angle)*knownR0, y:hub2Y+Math.sin(angle)*knownR0, vx:0, vy:0, r:4.5, label:lbl, color:'#4B5563', type:'known', cluster:0, detail:'Linked via on-chain transfers'}});
            edges.push({{s:1, t:nodes.length-1, type:'hub-known'}});
            if (Math.random() < 0.4) {{
                var smPool = nodes.filter(function(n){{return n.type==='sm' && n.cluster===0;}});
                if (smPool.length) edges.push({{s:smPool[Math.floor(Math.random()*smPool.length)].id, t:nodes.length-1, type:'hub-known'}});
            }}
        }});

        /* Entity nodes (exchanges/DEXs) */
        var entityData = [
            {{label:'Binance', angle:-Math.PI/2, dist:200}},
            {{label:'Coinbase', angle:Math.PI*0.15, dist:210}},
            {{label:'Uniswap V3', angle:Math.PI*0.65, dist:195}},
            {{label:'Aave', angle:Math.PI*0.85, dist:205}},
            {{label:'Lido', angle:-Math.PI*0.25, dist:205}}
        ];
        entityData.forEach(function(e) {{
            nodes.push({{id:nodes.length, x:CX+Math.cos(e.angle)*e.dist, y:CY+Math.sin(e.angle)*e.dist, vx:0, vy:0, r:12, label:e.label, color:'#A855F7', type:'entity', cluster:-1, isSquare:true}});
        }});

        /* Connect entities to SM/known nodes */
        var entIds = nodes.filter(function(n){{return n.type==='entity';}}).map(function(n){{return n.id;}});
        var smKnown = nodes.filter(function(n){{return n.type==='sm'||n.type==='known';}});
        entIds.forEach(function(eid) {{
            var count = 2 + Math.floor(Math.random() * 3);
            var used = {{}};
            for (var i = 0; i < count; i++) {{
                var t = smKnown[Math.floor(Math.random() * smKnown.length)];
                if (!used[t.id]) {{ used[t.id] = true; edges.push({{s:eid, t:t.id, type:'entity-link'}}); }}
            }}
            if (Math.random() < 0.6) edges.push({{s:eid, t:0, type:'entity-link'}});
            if (Math.random() < 0.4) edges.push({{s:eid, t:1, type:'entity-link'}});
        }});

        /* Peripherals */
        for (var pi = 0; pi < 40; pi++) {{
            var cl = Math.random() < 0.6 ? 1 : 0;
            var hubX = cl === 1 ? hub1X : hub2X, hubY = cl === 1 ? hub1Y : hub2Y;
            var angle = Math.random() * Math.PI * 2;
            var dist = 180 + Math.random() * 60;
            nodes.push({{id:nodes.length, x:hubX+Math.cos(angle)*dist, y:hubY+Math.sin(angle)*dist, vx:0, vy:0, r:1.5+Math.random()*1.2, label:rAddr(), color:'#374151', type:'peripheral', cluster:cl}});
            var pool = nodes.filter(function(n){{return n.type==='known'||n.type==='sm';}});
            var p = pool[Math.floor(Math.random() * pool.length)];
            edges.push({{s:p.id, t:nodes.length-1, type:'peripheral'}});
            if (Math.random() < 0.12) {{
                var o = pool[Math.floor(Math.random() * pool.length)];
                if (o.id !== p.id) edges.push({{s:o.id, t:nodes.length-1, type:'peripheral'}});
            }}
        }}

        /* Hub-to-hub edge */
        edges.push({{s:0, t:1, type:'hub-sm'}});

        /* Connection counts */
        nodes.forEach(function(n) {{ n.conn = 0; }});
        edges.forEach(function(e) {{ nodes[e.s].conn++; nodes[e.t].conn++; }});

        /* ---- Force simulation ---- */
        var iteration = 0, settled = false;
        function simulate() {{
            for (var i = 0; i < nodes.length; i++) {{
                for (var j = i + 1; j < nodes.length; j++) {{
                    var dx = nodes[j].x - nodes[i].x, dy = nodes[j].y - nodes[i].y;
                    var d2 = dx * dx + dy * dy; if (d2 < 1) d2 = 1;
                    var d = Math.sqrt(d2), f = 150 / d2;
                    var fx = dx / d * f, fy = dy / d * f;
                    if (!nodes[i]._pinned) {{ nodes[i].vx -= fx; nodes[i].vy -= fy; }}
                    if (!nodes[j]._pinned) {{ nodes[j].vx += fx; nodes[j].vy += fy; }}
                }}
            }}
            edges.forEach(function(e) {{
                var a = nodes[e.s], b = nodes[e.t];
                var dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx*dx+dy*dy) || 1;
                var rest = e.type === 'peripheral' ? 50 : e.type === 'hub-sm' ? smR : e.type === 'hub-known' ? knownR1 * 0.9 : 80;
                var f = 0.015 * (d - rest), fx = dx/d*f, fy = dy/d*f;
                if (!a._pinned) {{ a.vx += fx; a.vy += fy; }}
                if (!b._pinned) {{ b.vx -= fx; b.vy -= fy; }}
            }});
            nodes.forEach(function(n) {{
                if (n.type === 'hub') return;
                var hx = n.cluster === 1 ? hub1X : n.cluster === 0 ? hub2X : CX;
                var hy = n.cluster === 1 ? hub1Y : n.cluster === 0 ? hub2Y : CY;
                var grav = n.type === 'entity' ? 0.003 : 0.008;
                n.vx += (hx - n.x) * grav; n.vy += (hy - n.y) * grav;
            }});
            nodes.forEach(function(n) {{
                if (n.type === 'hub') return;
                n.vx += (CX - n.x) * 0.002; n.vy += (CY - n.y) * 0.002;
            }});
            nodes.forEach(function(n) {{
                if (n.type === 'hub') {{ n.vx = 0; n.vy = 0; return; }}
                n.vx *= 0.92; n.vy *= 0.92;
                n.x += n.vx; n.y += n.vy;
                n.x = Math.max(n.r + 8, Math.min(W - n.r - 8, n.x));
                n.y = Math.max(n.r + 8, Math.min(H - n.r - 8, n.y));
            }});
            iteration++;
        }}

        var settledPos = [];

        /* ---- Draw ---- */
        function draw(time) {{
            ctx.clearRect(0, 0, W, H);
            var t = time || 0;

            if (settled && settledPos.length) {{
                nodes.forEach(function(n, i) {{
                    var sp = settledPos[i];
                    if (!n._pinned) {{
                        n.x = sp.ox + Math.sin(t * 0.0008 * sp.sx + sp.px) * sp.ax;
                        n.y = sp.oy + Math.cos(t * 0.0006 * sp.sy + sp.py) * sp.ay;
                    }}
                }});
            }}

            ctx.save();
            ctx.translate(panX + W/2*(1-zoom), panY + H/2*(1-zoom));
            ctx.scale(zoom, zoom);

            /* Cluster zone backgrounds */
            ctx.beginPath();
            ctx.arc(hub1X, hub1Y, 170, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(0,229,160,0.025)';
            ctx.fill();
            ctx.strokeStyle = 'rgba(0,229,160,0.07)';
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 4]);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.beginPath();
            ctx.arc(hub2X, hub2Y, 160, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(245,166,35,0.02)';
            ctx.fill();
            ctx.strokeStyle = 'rgba(245,166,35,0.06)';
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 4]);
            ctx.stroke();
            ctx.setLineDash([]);

            /* Cluster labels */
            ctx.font = 'bold 9px JetBrains Mono, monospace';
            ctx.textAlign = 'center';
            ctx.fillStyle = 'rgba(0,229,160,0.35)';
            ctx.fillText('Cluster #1 — DeFi Whale', hub1X, hub1Y - 180);
            ctx.fillStyle = 'rgba(245,166,35,0.35)';
            ctx.fillText('Cluster #0 — Fund Deployer', hub2X, hub2Y - 170);

            /* Edges */
            var highlightNode = dragNode || null;
            edges.forEach(function(e) {{
                var a = nodes[e.s], b = nodes[e.t];
                var isH = highlightNode && (e.s === highlightNode.id || e.t === highlightNode.id);
                ctx.beginPath();
                if (e.type === 'hub-sm') {{
                    ctx.strokeStyle = isH ? 'rgba(0,229,160,0.95)' : 'rgba(0,229,160,0.5)';
                    ctx.lineWidth = isH ? 2.5 : 1.5;
                    var mx = (a.x+b.x)/2 + (a.y-b.y)*0.12, my = (a.y+b.y)/2 + (b.x-a.x)*0.12;
                    ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(mx, my, b.x, b.y);
                }} else if (e.type === 'hub-known') {{
                    ctx.strokeStyle = isH ? 'rgba(245,158,11,0.7)' : 'rgba(245,158,11,0.18)';
                    ctx.lineWidth = isH ? 1.8 : 0.7;
                    var mx = (a.x+b.x)/2 + (a.y-b.y)*0.06, my = (a.y+b.y)/2 + (b.x-a.x)*0.06;
                    ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(mx, my, b.x, b.y);
                }} else if (e.type === 'entity-link') {{
                    ctx.strokeStyle = isH ? 'rgba(168,85,247,0.7)' : 'rgba(168,85,247,0.15)';
                    ctx.lineWidth = isH ? 1.5 : 0.6;
                    ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
                }} else {{
                    ctx.strokeStyle = isH ? 'rgba(156,163,175,0.5)' : 'rgba(31,41,55,0.25)';
                    ctx.lineWidth = isH ? 0.8 : 0.3;
                    ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
                }}
                ctx.stroke();
            }});

            /* Nodes */
            nodes.forEach(function(n) {{
                if (n.type === 'hub') {{
                    ctx.beginPath();
                    var pulse = 1 + 0.12 * Math.sin(t * 0.003 + (n.cluster === 1 ? 0 : Math.PI));
                    var grad = ctx.createRadialGradient(n.x, n.y, n.r*0.3, n.x, n.y, n.r*3*pulse);
                    grad.addColorStop(0, n.color + '40'); grad.addColorStop(1, n.color + '00');
                    ctx.fillStyle = grad; ctx.arc(n.x, n.y, n.r*3*pulse, 0, Math.PI*2); ctx.fill();
                }}
                if (n.type === 'sm') {{
                    ctx.beginPath();
                    var grad = ctx.createRadialGradient(n.x, n.y, n.r*0.3, n.x, n.y, n.r*2);
                    grad.addColorStop(0, '#00E5A020'); grad.addColorStop(1, '#00E5A000');
                    ctx.fillStyle = grad; ctx.arc(n.x, n.y, n.r*2, 0, Math.PI*2); ctx.fill();
                }}
                if (n.isSquare) {{
                    var s = n.r * 1.4;
                    ctx.fillStyle = '#A855F7';
                    ctx.beginPath(); ctx.roundRect(n.x-s, n.y-s, s*2, s*2, 4); ctx.fill();
                    ctx.strokeStyle = 'rgba(168,85,247,0.5)'; ctx.lineWidth = 1.5; ctx.stroke();
                }} else {{
                    ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI*2);
                    if (n.type === 'hub') {{
                        ctx.fillStyle = n.color; ctx.strokeStyle = n.color + '80'; ctx.lineWidth = 2; ctx.fill(); ctx.stroke();
                    }} else if (n.type === 'sm') {{
                        ctx.fillStyle = '#00E5A0'; ctx.fill();
                    }} else if (n.type === 'known') {{
                        ctx.fillStyle = '#4B5563'; ctx.fill();
                    }} else {{
                        ctx.fillStyle = '#2A3040'; ctx.globalAlpha = 0.6; ctx.fill(); ctx.globalAlpha = 1;
                    }}
                }}
            }});

            /* Labels */
            ctx.textAlign = 'center';
            nodes.forEach(function(n) {{
                if (n.type === 'hub') {{
                    ctx.fillStyle = '#E5E7EB'; ctx.font = 'bold 10px JetBrains Mono, monospace';
                    ctx.fillText(n.label, n.x, n.y + n.r + 16);
                }} else if (n.type === 'sm') {{
                    ctx.fillStyle = '#00E5A0'; ctx.font = 'bold 8px JetBrains Mono, monospace';
                    ctx.fillText(n.label, n.x, n.y + n.r + 11);
                }} else if (n.type === 'entity') {{
                    ctx.fillStyle = '#E9D5FF'; ctx.font = 'bold 9px JetBrains Mono, monospace';
                    ctx.fillText(n.label, n.x, n.y + n.r + 14);
                }}
            }});

            ctx.restore();
        }}

        /* ---- Zoom / Pan state ---- */
        var zoom = 1, panX = 0, panY = 0;
        var dragging = false, dragStartX = 0, dragStartY = 0, dragPanX = 0, dragPanY = 0;
        var dragNode = null;

        window._netZoom = function(factor) {{
            zoom *= factor;
            zoom = Math.max(0.3, Math.min(5, zoom));
        }};
        window._netReset = function() {{
            zoom = 1; panX = 0; panY = 0;
        }};

        function screenToWorld(sx, sy) {{
            return {{
                x: (sx - panX - W/2*(1-zoom)) / zoom,
                y: (sy - panY - H/2*(1-zoom)) / zoom
            }};
        }}
        function findNodeAt(sx, sy) {{
            var p = screenToWorld(sx, sy);
            for (var i = nodes.length - 1; i >= 0; i--) {{
                var n = nodes[i], dx = p.x - n.x, dy = p.y - n.y;
                if (dx*dx + dy*dy < Math.max(n.r*n.r*4, 100)) return n;
            }}
            return null;
        }}

        /* Mouse events */
        container.addEventListener('wheel', function(ev) {{
            ev.preventDefault();
            var f = ev.deltaY > 0 ? 0.9 : 1.1;
            zoom *= f;
            zoom = Math.max(0.3, Math.min(5, zoom));
        }}, {{passive: false}});

        container.addEventListener('mousedown', function(ev) {{
            var rect = canvas.getBoundingClientRect();
            var sx = ev.clientX - rect.left, sy = ev.clientY - rect.top;
            var hit = findNodeAt(sx, sy);
            if (hit) {{
                dragNode = hit; dragNode._pinned = true;
                container.style.cursor = 'grabbing';
            }} else {{
                dragging = true;
                dragStartX = ev.clientX; dragStartY = ev.clientY;
                dragPanX = panX; dragPanY = panY;
                container.style.cursor = 'grabbing';
            }}
        }});

        window.addEventListener('mousemove', function(ev) {{
            if (dragNode) {{
                var rect = canvas.getBoundingClientRect();
                var p = screenToWorld(ev.clientX - rect.left, ev.clientY - rect.top);
                dragNode.x = p.x; dragNode.y = p.y;
                dragNode.vx = 0; dragNode.vy = 0;
                if (settled && settledPos[dragNode.id]) {{
                    settledPos[dragNode.id].ox = p.x;
                    settledPos[dragNode.id].oy = p.y;
                }}
            }} else if (dragging) {{
                panX = dragPanX + (ev.clientX - dragStartX);
                panY = dragPanY + (ev.clientY - dragStartY);
            }}
        }});

        window.addEventListener('mouseup', function() {{
            if (dragNode) {{ dragNode._pinned = false; dragNode = null; }}
            dragging = false;
            container.style.cursor = 'grab';
        }});

        /* Touch events */
        container.addEventListener('touchstart', function(ev) {{
            if (ev.touches.length !== 1) return;
            var t = ev.touches[0], rect = canvas.getBoundingClientRect();
            var sx = t.clientX - rect.left, sy = t.clientY - rect.top;
            var hit = findNodeAt(sx, sy);
            if (hit) {{ dragNode = hit; dragNode._pinned = true; ev.preventDefault(); }}
            else {{ dragging = true; dragStartX = t.clientX; dragStartY = t.clientY; dragPanX = panX; dragPanY = panY; }}
        }}, {{passive: false}});

        container.addEventListener('touchmove', function(ev) {{
            if (ev.touches.length !== 1) return;
            var t = ev.touches[0];
            if (dragNode) {{
                ev.preventDefault();
                var rect = canvas.getBoundingClientRect();
                var p = screenToWorld(t.clientX - rect.left, t.clientY - rect.top);
                dragNode.x = p.x; dragNode.y = p.y; dragNode.vx = 0; dragNode.vy = 0;
                if (settled && settledPos[dragNode.id]) {{ settledPos[dragNode.id].ox = p.x; settledPos[dragNode.id].oy = p.y; }}
            }} else if (dragging) {{
                panX = dragPanX + (t.clientX - dragStartX);
                panY = dragPanY + (t.clientY - dragStartY);
            }}
        }}, {{passive: false}});

        container.addEventListener('touchend', function() {{
            if (dragNode) {{ dragNode._pinned = false; dragNode = null; }}
            dragging = false;
        }});

        /* Hover tooltip */
        canvas.addEventListener('mousemove', function(ev) {{
            var rect = canvas.getBoundingClientRect();
            var rawX = ev.clientX - rect.left, rawY = ev.clientY - rect.top;
            var mx = (rawX - panX - W/2*(1-zoom)) / zoom;
            var my = (rawY - panY - H/2*(1-zoom)) / zoom;
            var found = null;
            for (var i = nodes.length - 1; i >= 0; i--) {{
                var n = nodes[i], dx = mx - n.x, dy = my - n.y;
                if (dx*dx + dy*dy < Math.max(n.r*n.r*4, 64)) {{ found = n; break; }}
            }}
            if (found) {{
                var n = found;
                var lbl = n.type === 'hub' ? 'Cluster Hub' : n.type === 'sm' ? 'Tracked Wallet' : n.type === 'known' ? 'Related Wallet' : n.type === 'entity' ? 'Exchange / DEX' : 'Peripheral';
                var det = n.detail ? '<br><span style="color:#8895A7;font-size:10px">' + n.detail + '</span>' : '';
                tt.innerHTML = '<span style="color:' + n.color + '">' + n.label + '</span><br>' + lbl + ' &middot; ' + n.conn + ' connections' + det;
                var screenX = n.x * zoom + panX + W/2*(1-zoom);
                var screenY = n.y * zoom + panY + H/2*(1-zoom);
                tt.style.display = 'block';
                tt.style.left = Math.min(screenX + 15, W - 170) + 'px';
                tt.style.top = Math.max(screenY - 55, 4) + 'px';
                canvas.style.cursor = 'pointer';
            }} else {{
                tt.style.display = 'none';
                canvas.style.cursor = dragging ? 'grabbing' : 'grab';
            }}
        }});
        canvas.addEventListener('mouseleave', function() {{ tt.style.display = 'none'; }});

        /* ---- Animation loop ---- */
        function loop(time) {{
            if (!settled) {{
                for (var s = 0; s < 2; s++) simulate();
                if (iteration >= 100) {{
                    settled = true;
                    settledPos = nodes.map(function(n) {{
                        return {{
                            ox: n.x, oy: n.y,
                            px: Math.random()*6.28, py: Math.random()*6.28,
                            sx: 0.3+Math.random()*0.5, sy: 0.25+Math.random()*0.4,
                            ax: 0.3+Math.random()*0.5, ay: 0.3+Math.random()*0.5
                        }};
                    }});
                }}
            }}
            draw(time);
            requestAnimationFrame(loop);
        }}

        resize();
        initialized = true;
        loop(0);
        window.addEventListener('resize', function() {{ resize(); }});
    }}
    </script>
</body>
</html>"""

    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(html)
    log.info("Dashboard saved to %s", DASHBOARD_PATH)

    if auto_open:
        webbrowser.open(f"file://{DASHBOARD_PATH.resolve()}")
        log.info("Dashboard opened in browser")

    return DASHBOARD_PATH
