"""
NansenScope — Interactive Local Dashboard

Generates a self-contained HTML dashboard matching the landing page aesthetic.
Embeds charts as base64, includes interactive Plotly charts, signal table
with chain filters, and the full intelligence report.
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


def _read_html_chart(path: Path) -> str:
    if not path.exists():
        return ""
    content = path.read_text()
    return content.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')


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
            f'<button class="filter-btn" onclick="filterSignals(\'{c}\')">{c.title()}</button>'
        )
    return "".join(buttons)


def _build_signal_rows(signals: list) -> str:
    rows = ""
    for i, s in enumerate(signals, 1):
        sev = s.get("severity", "high").upper()
        sev_class = sev.lower()
        rows += f"""
        <tr class="signal-row" data-chain="{s.get('chain','')}" data-severity="{sev.lower()}">
            <td class="row-num">{i}</td>
            <td><span class="sev-badge {sev_class}">{sev}</span></td>
            <td><span class="chain-pill">{s.get('chain','')}</span></td>
            <td class="token">{s.get('token','')}</td>
            <td class="type">{s.get('type','').replace('_',' ').title()}</td>
            <td class="summary">{s.get('summary','')[:100]}</td>
            <td class="score">{s.get('score', 0):.0f}</td>
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
    
    network_html_raw = ""
    network_path = CHARTS_DIR / "network_map.html"
    if network_path.exists():
        network_html_raw = network_path.read_text()
    
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
    
    # Escape report for safe HTML embedding
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
        
        .header-right {{
            display: flex;
            gap: 8px;
        }}
        .status-badge {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            padding: 4px 12px;
            border-radius: 4px;
            background: rgba(0,229,160,0.1);
            border: 1px solid rgba(0,229,160,0.2);
            color: #00E5A0;
        }}

        /* Stats */
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

        /* Content */
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
        }}
        .signal-table td {{
            padding: 10px 14px;
            border-bottom: 1px solid #1A294040;
        }}
        .signal-row {{
            transition: background 0.15s;
        }}
        .signal-row:hover {{
            background: rgba(0,229,160,0.03);
        }}
        
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
        .type {{
            color: #8895A7;
            font-size: 12px;
        }}
        .summary {{
            color: #8895A7;
            max-width: 360px;
            font-size: 12px;
        }}
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

        /* Network iframe */
        .interactive-frame {{
            width: 100%;
            border: none;
            min-height: 550px;
            background: #060B14;
            border-radius: 8px;
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

        /* Responsive */
        @media (max-width: 768px) {{
            .stats {{ flex-wrap: wrap; }}
            .stat {{ min-width: 50%; }}
            .charts-2col {{ grid-template-columns: 1fr; }}
            .content, .header, .stats, .chain-bar {{ padding-left: 20px; padding-right: 20px; }}
        }}
    </style>
</head>
<body>
    <div class="intel-grid"></div>
    <div class="scan-line"></div>
    
    <div class="wrapper">
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
        
        <div class="chain-bar">
            {chain_cards}
        </div>
        
        <div class="content">
            <div class="tab-bar">
                <button class="tab active" onclick="showTab('signals', this)">Signals</button>
                <button class="tab" onclick="showTab('charts', this)">Charts</button>
                <button class="tab" onclick="showTab('network', this)">Network Map</button>
                <button class="tab" onclick="showTab('report', this)">Full Report</button>
            </div>
            
            <div id="tab-signals" class="tab-content active">
                <div class="filters">
                    <button class="filter-btn active" onclick="filterSignals('all', this)">All</button>
                    {chain_filters}
                </div>
                <div class="table-wrap">
                    <table class="signal-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Severity</th>
                                <th>Chain</th>
                                <th>Token</th>
                                <th>Type</th>
                                <th>Signal</th>
                                <th>Score</th>
                            </tr>
                        </thead>
                        <tbody>
                            {signal_rows}
                        </tbody>
                    </table>
                </div>
            </div>
            
            <div id="tab-charts" class="tab-content">
                <div class="charts-grid">
                    {"<div class='chart-card'><h3>Signal Fusion &mdash; Top Signals by Conviction</h3><img src='" + timeline_b64 + "'></div>" if timeline_b64 else ""}
                </div>
                <div class="charts-2col" style="margin-top: 20px;">
                    {"<div class='chart-card'><h3>Chain Comparison</h3><img src='" + comparison_b64 + "'></div>" if comparison_b64 else ""}
                    {"<div class='chart-card'><h3>Syndicate Bubble Map</h3><img src='" + bubble_b64 + "'></div>" if bubble_b64 else ""}
                </div>
            </div>
            
            <div id="tab-network" class="tab-content">
                {"<iframe class='interactive-frame' srcdoc='" + network_html_raw.replace("'", "&#39;") + "' sandbox='allow-scripts'></iframe>" if network_html_raw else "<p style='color:#8895A7; padding: 40px; text-align: center;'>No network map available. Run: <code style=\"color:#00E5A0\">nansenscope network --address &lt;wallet&gt;</code></p>"}
            </div>
            
            <div id="tab-report" class="tab-content">
                <pre class="report-pre">{report_escaped}</pre>
            </div>
        </div>
        
        <div class="footer">
            <span class="accent">NansenScope</span> v2.0 &mdash; Autonomous Smart Money Intelligence &mdash; Built with Nansen CLI + x402
        </div>
    </div>
    
    <script>
        function showTab(name, el) {{
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById('tab-' + name).classList.add('active');
            el.classList.add('active');
        }}
        
        function filterSignals(chain, el) {{
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            el.classList.add('active');
            document.querySelectorAll('.signal-row').forEach(row => {{
                row.style.display = (chain === 'all' || row.dataset.chain === chain) ? '' : 'none';
            }});
        }}
    </script>
</body>
</html>"""
    
    DASHBOARD_PATH.write_text(html)
    log.info("Dashboard saved to %s", DASHBOARD_PATH)
    
    if auto_open:
        webbrowser.open(f"file://{DASHBOARD_PATH.resolve()}")
        log.info("Dashboard opened in browser")
    
    return DASHBOARD_PATH
