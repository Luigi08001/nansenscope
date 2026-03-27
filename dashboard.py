"""
NansenScope — Interactive Local Dashboard

Generates a self-contained HTML dashboard from scan results and opens
it in the default browser. Embeds charts as base64, includes interactive
Plotly charts, and presents the full report in a polished dark UI.
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
    """Convert image file to base64 data URI."""
    if not path.exists():
        return ""
    data = base64.b64encode(path.read_bytes()).decode()
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/svg+xml" if suffix == ".svg" else "image/jpeg"
    return f"data:{mime};base64,{data}"


def _read_html_chart(path: Path) -> str:
    """Read an interactive HTML chart file."""
    if not path.exists():
        return ""
    return path.read_text()


def _load_latest_results() -> dict:
    """Load latest scan results from JSON."""
    path = REPORTS_DIR / "latest_results.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _load_latest_report() -> str:
    """Find and load the most recent markdown report."""
    reports = sorted(REPORTS_DIR.glob("daily_*.md"), reverse=True)
    if not reports:
        reports = sorted(REPORTS_DIR.glob("scan_*.md"), reverse=True)
    if reports:
        return reports[0].read_text()
    return ""


def _build_chain_filters(signals: list) -> str:
    """Build HTML filter buttons for each chain."""
    chains = sorted(set(s.get("chain", "") for s in signals))
    buttons = []
    for c in chains:
        buttons.append(
            f'<button class="filter-btn" onclick="filterSignals(\'{c}\')">{c.title()}</button>'
        )
    return "".join(buttons)


def generate_dashboard(auto_open: bool = True) -> Path:
    """
    Generate an interactive HTML dashboard from the latest scan results.
    
    Args:
        auto_open: Open in default browser after generating.
    
    Returns:
        Path to the generated dashboard HTML file.
    """
    results = _load_latest_results()
    report_md = _load_latest_report()
    
    # Load chart images
    timeline_b64 = _img_to_base64(CHARTS_DIR / "signal_timeline.png")
    comparison_b64 = _img_to_base64(CHARTS_DIR / "chain_comparison.png")
    bubble_b64 = _img_to_base64(CHARTS_DIR / "syndicate_bubble_map.png")
    
    # Load interactive HTML charts
    network_html = _read_html_chart(CHARTS_DIR / "network_map.html")
    bubble_html = _read_html_chart(CHARTS_DIR / "syndicate_bubble_map.html")
    
    # Extract signal data for interactive table
    signals = results.get("signals", [])
    chains_scanned = results.get("chains", [])
    total_signals = results.get("total_signals", len(signals))
    timestamp = results.get("timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    
    # Build signal rows for the table
    signal_rows = ""
    for i, s in enumerate(signals, 1):
        sev = s.get("severity", "high").upper()
        sev_color = {
            "CRITICAL": "#FF0000",
            "HIGH": "#FF8C00", 
            "MEDIUM": "#FFD700",
            "LOW": "#4ECDC4",
        }.get(sev, "#FF8C00")
        
        signal_rows += f"""
        <tr class="signal-row" data-chain="{s.get('chain','')}" data-severity="{sev.lower()}">
            <td>{i}</td>
            <td><span class="severity-badge" style="background:{sev_color}">{sev}</span></td>
            <td><span class="chain-tag">{s.get('chain','')}</span></td>
            <td class="token-name">{s.get('token','')}</td>
            <td>{s.get('type','').replace('_',' ').title()}</td>
            <td class="signal-summary">{s.get('summary','')[:100]}</td>
            <td class="score">{s.get('score', 0):.0f}</td>
        </tr>"""

    # Chain summary cards
    chain_cards = ""
    chain_summary = results.get("chain_summary", [])
    if isinstance(chain_summary, list):
        for cs in chain_summary:
            if isinstance(cs, dict):
                chain_cards += f"""
                <div class="chain-card">
                    <div class="chain-name">{cs.get('chain','').upper()}</div>
                    <div class="chain-signals">{cs.get('total_signals', 0)} signals</div>
                </div>"""
    
    # Build the HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NansenScope Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'SF Mono', 'Fira Code', 'Courier New', monospace;
            background: #0D1117;
            color: #C9D1D9;
            min-height: 100vh;
        }}
        
        .header {{
            background: linear-gradient(135deg, #161B22 0%, #0D1117 100%);
            border-bottom: 1px solid #30363D;
            padding: 24px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .header h1 {{
            font-size: 24px;
            color: #58A6FF;
            font-weight: 700;
        }}
        
        .header .meta {{
            color: #8B949E;
            font-size: 13px;
        }}
        
        .stats-bar {{
            display: flex;
            gap: 32px;
            padding: 20px 40px;
            background: #161B22;
            border-bottom: 1px solid #30363D;
        }}
        
        .stat {{
            text-align: center;
        }}
        
        .stat .value {{
            font-size: 32px;
            font-weight: 700;
            color: #58A6FF;
        }}
        
        .stat .label {{
            font-size: 11px;
            color: #8B949E;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .chain-cards {{
            display: flex;
            gap: 12px;
            padding: 20px 40px;
            flex-wrap: wrap;
        }}
        
        .chain-card {{
            background: #161B22;
            border: 1px solid #30363D;
            border-radius: 8px;
            padding: 12px 20px;
            min-width: 120px;
            text-align: center;
            transition: border-color 0.2s;
        }}
        
        .chain-card:hover {{
            border-color: #58A6FF;
        }}
        
        .chain-name {{
            font-weight: 700;
            font-size: 14px;
            color: #E6EDF3;
        }}
        
        .chain-signals {{
            font-size: 12px;
            color: #8B949E;
            margin-top: 4px;
        }}
        
        .content {{
            padding: 24px 40px;
        }}
        
        .section {{
            margin-bottom: 40px;
        }}
        
        .section h2 {{
            font-size: 18px;
            color: #E6EDF3;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid #30363D;
        }}
        
        /* Filter bar */
        .filters {{
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
            flex-wrap: wrap;
        }}
        
        .filter-btn {{
            background: #21262D;
            border: 1px solid #30363D;
            color: #C9D1D9;
            padding: 6px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 12px;
            font-family: inherit;
            transition: all 0.2s;
        }}
        
        .filter-btn:hover, .filter-btn.active {{
            background: #58A6FF;
            color: #0D1117;
            border-color: #58A6FF;
        }}
        
        /* Signal table */
        .signal-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        
        .signal-table th {{
            background: #161B22;
            color: #8B949E;
            padding: 10px 12px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
            position: sticky;
            top: 0;
        }}
        
        .signal-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #21262D;
        }}
        
        .signal-row {{
            transition: background 0.15s;
        }}
        
        .signal-row:hover {{
            background: #161B22;
        }}
        
        .severity-badge {{
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
            color: #0D1117;
        }}
        
        .chain-tag {{
            background: #21262D;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
        }}
        
        .token-name {{
            font-weight: 700;
            color: #E6EDF3;
        }}
        
        .score {{
            font-weight: 700;
            color: #58A6FF;
        }}
        
        .signal-summary {{
            color: #8B949E;
            max-width: 400px;
        }}
        
        /* Charts */
        .charts-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        
        .chart-card {{
            background: #161B22;
            border: 1px solid #30363D;
            border-radius: 12px;
            overflow: hidden;
        }}
        
        .chart-card.full-width {{
            grid-column: 1 / -1;
        }}
        
        .chart-card img {{
            width: 100%;
            display: block;
        }}
        
        .chart-card h3 {{
            padding: 12px 16px;
            font-size: 14px;
            color: #E6EDF3;
            border-bottom: 1px solid #30363D;
        }}
        
        /* Interactive chart iframe */
        .interactive-chart {{
            width: 100%;
            border: none;
            min-height: 500px;
            background: #0D1117;
        }}
        
        /* Tabs */
        .tab-bar {{
            display: flex;
            gap: 0;
            border-bottom: 1px solid #30363D;
            margin-bottom: 20px;
        }}
        
        .tab {{
            padding: 10px 20px;
            cursor: pointer;
            color: #8B949E;
            border-bottom: 2px solid transparent;
            font-size: 13px;
            font-family: inherit;
            background: none;
            border-top: none;
            border-left: none;
            border-right: none;
            transition: all 0.2s;
        }}
        
        .tab:hover {{
            color: #C9D1D9;
        }}
        
        .tab.active {{
            color: #58A6FF;
            border-bottom-color: #58A6FF;
        }}
        
        .tab-content {{
            display: none;
        }}
        
        .tab-content.active {{
            display: block;
        }}
        
        /* Footer */
        .footer {{
            padding: 20px 40px;
            border-top: 1px solid #30363D;
            color: #8B949E;
            font-size: 11px;
            text-align: center;
        }}

        @media (max-width: 768px) {{
            .charts-grid {{ grid-template-columns: 1fr; }}
            .stats-bar {{ flex-wrap: wrap; gap: 16px; }}
            .content {{ padding: 16px; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>NansenScope Dashboard</h1>
        <div class="meta">Generated: {timestamp} | Chains: {', '.join(chains_scanned) if isinstance(chains_scanned, list) else chains_scanned}</div>
    </div>
    
    <div class="stats-bar">
        <div class="stat">
            <div class="value">{total_signals}</div>
            <div class="label">Signals Detected</div>
        </div>
        <div class="stat">
            <div class="value">{len(chains_scanned) if isinstance(chains_scanned, list) else 0}</div>
            <div class="label">Chains Scanned</div>
        </div>
        <div class="stat">
            <div class="value">{len([s for s in signals if s.get('severity') == 'high' or s.get('severity') == 'critical'])}</div>
            <div class="label">High Priority</div>
        </div>
        <div class="stat">
            <div class="value">{len(set(s.get('token','') for s in signals))}</div>
            <div class="label">Unique Tokens</div>
        </div>
    </div>
    
    <div class="chain-cards">
        {chain_cards}
    </div>
    
    <div class="content">
        <!-- Tabs -->
        <div class="tab-bar">
            <button class="tab active" onclick="showTab('signals')">Signals</button>
            <button class="tab" onclick="showTab('charts')">Charts</button>
            <button class="tab" onclick="showTab('network')">Network Map</button>
            <button class="tab" onclick="showTab('report')">Full Report</button>
        </div>
        
        <!-- Signals Tab -->
        <div id="tab-signals" class="tab-content active">
            <div class="section">
                <div class="filters">
                    <button class="filter-btn active" onclick="filterSignals('all')">All</button>
                    {_build_chain_filters(signals)}
                </div>
                
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
        
        <!-- Charts Tab -->
        <div id="tab-charts" class="tab-content">
            <div class="charts-grid">
                {'<div class="chart-card full-width"><h3>Signal Fusion — Top Signals by Conviction</h3><img src="' + timeline_b64 + '"></div>' if timeline_b64 else ''}
                {'<div class="chart-card"><h3>Chain Comparison</h3><img src="' + comparison_b64 + '"></div>' if comparison_b64 else ''}
                {'<div class="chart-card"><h3>Syndicate Bubble Map</h3><img src="' + bubble_b64 + '"></div>' if bubble_b64 else ''}
            </div>
        </div>
        
        <!-- Network Tab -->
        <div id="tab-network" class="tab-content">
            <div class="section">
                <h2>Interactive Network Map</h2>
                {f'<iframe class="interactive-chart" srcdoc="{network_html.replace(chr(34), "&quot;")}" sandbox="allow-scripts"></iframe>' if network_html else '<p style="color:#8B949E">No network map available. Run: nansenscope network --address &lt;wallet&gt;</p>'}
            </div>
        </div>
        
        <!-- Report Tab -->
        <div id="tab-report" class="tab-content">
            <div class="section">
                <h2>Intelligence Report</h2>
                <pre style="white-space: pre-wrap; line-height: 1.6; color: #C9D1D9; font-size: 13px;">{report_md}</pre>
            </div>
        </div>
    </div>
    
    <div class="footer">
        NansenScope v2.0 — Autonomous Smart Money Intelligence — Built with Nansen CLI + x402
    </div>
    
    <script>
        function showTab(name) {{
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById('tab-' + name).classList.add('active');
            event.target.classList.add('active');
        }}
        
        function filterSignals(chain) {{
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');
            
            document.querySelectorAll('.signal-row').forEach(row => {{
                if (chain === 'all' || row.dataset.chain === chain) {{
                    row.style.display = '';
                }} else {{
                    row.style.display = 'none';
                }}
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
