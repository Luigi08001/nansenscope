#!/usr/bin/env python3
"""
NansenScope — Autonomous Smart Money Intelligence Agent

Scans Nansen's smart money data across multiple chains, detects actionable
signals through cross-referencing, and generates intelligence reports.

Usage:
    nansenscope scan   --chains ethereum,base,solana
    nansenscope profile --address 0x... --chain ethereum
    nansenscope signals
    nansenscope report  --output report.md
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from config import DEFAULT_CHAINS, DEFAULT_OUTPUT, DEFAULT_THRESHOLDS, Severity, api_tracker
from alerts import AlertEngine
from charts import generate_all_charts
from reporter import (
    generate_scan_report,
    generate_signals_report,
    generate_wallet_report,
    save_report,
)
from scanner import (
    ScanResult, profile_wallet, scan_all_chains,
    get_wallet_labels, get_wallet_balance, get_wallet_profile,
    get_prediction_markets, get_prediction_events,
)
from history import record_signals, load_history, detect_trends, format_trend_table
from signals import Signal, analyze_all_chains, rank_signals

import json

console = Console()


def save_latest_results(signals: list, chains: list, scan_data=None):
    """Save latest scan results as JSON for landing page rendering."""
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "chains": chains,
        "total_signals": len(signals),
        "signals": [
            {
                "chain": s.chain,
                "token": s.token,
                "severity": s.severity.value,
                "score": s.score,
                "type": s.type,
                "summary": s.summary,
            }
            for s in sorted(signals, key=lambda x: x.score, reverse=True)[:20]
        ],
        "chain_summary": {
            chain: {
                "signal_count": len([s for s in signals if s.chain == chain]),
                "top_token": next(
                    (s.token for s in sorted(signals, key=lambda x: x.score, reverse=True) if s.chain == chain),
                    None,
                ),
            }
            for chain in chains
        },
    }

    output = Path("reports/latest_results.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2))

SEVERITY_STYLES = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "bold yellow",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "dim",
}

# ── Banner ───────────────────────────────────────────────────────────────────

BANNER = r"""
 _   _                            ____
| \ | | __ _ _ __  ___  ___ _ __ / ___|  ___ ___  _ __   ___
|  \| |/ _` | '_ \/ __|/ _ \ '_ \\___ \ / __/ _ \| '_ \ / _ \
| |\  | (_| | | | \__ \  __/ | | |___) | (_| (_) | |_) |  __/
|_| \_|\__,_|_| |_|___/\___|_| |_|____/ \___\___/| .__/ \___|
                                                  |_|
"""


def show_banner():
    console.print(Panel(
        BANNER + "\n  [bold]Autonomous Smart Money Intelligence[/bold]\n",
        border_style="cyan",
        padding=(0, 2),
    ))


# ── CLI Argument Parser ──────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nansenscope",
        description="NansenScope — Smart Money Intelligence Agent",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "-V", "--version", action="version",
        version="%(prog)s 1.0.0",
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ── scan ──
    scan_p = sub.add_parser("scan", help="Run a full smart money scan across chains")
    scan_p.add_argument(
        "--chains", type=str, default=",".join(DEFAULT_CHAINS),
        help=f"Comma-separated chains to scan (default: {','.join(DEFAULT_CHAINS)})",
    )
    scan_p.add_argument(
        "--all-chains", action="store_true", default=False,
        help="Scan ALL 18 supported chains (overrides --chains)",
    )
    scan_p.add_argument(
        "--output", "-o", type=str, default=None,
        help="Save report to file (default: reports/scan_YYYY-MM-DD.md)",
    )

    # ── profile ──
    prof_p = sub.add_parser("profile", help="Deep-dive a wallet address")
    prof_p.add_argument("--address", "-a", required=True, help="Wallet address")
    prof_p.add_argument("--chain", "-c", default="ethereum", help="Chain (default: ethereum)")
    prof_p.add_argument("--days", "-d", type=int, default=30, help="Lookback days (default: 30)")
    prof_p.add_argument("--output", "-o", type=str, default=None, help="Save report to file")

    # ── signals ──
    sig_p = sub.add_parser("signals", help="Detect and rank signals from last scan")
    sig_p.add_argument(
        "--chains", type=str, default=",".join(DEFAULT_CHAINS),
        help="Comma-separated chains to scan",
    )
    sig_p.add_argument("--top", type=int, default=20, help="Show top N signals")
    sig_p.add_argument("--output", "-o", type=str, default=None, help="Save report to file")

    # ── report ──
    rep_p = sub.add_parser("report", help="Generate a full intelligence report")
    rep_p.add_argument(
        "--chains", type=str, default=",".join(DEFAULT_CHAINS),
        help="Comma-separated chains to scan",
    )
    rep_p.add_argument(
        "--output", "-o", type=str,
        default=None,
        help="Output path (default: reports/report_YYYY-MM-DD.md)",
    )

    # ── alerts ──
    alert_p = sub.add_parser("alerts", help="Run alert engine, show triggered alerts")
    alert_p.add_argument(
        "--chains", type=str, default=",".join(DEFAULT_CHAINS),
        help="Comma-separated chains to scan",
    )

    # ── charts ──
    chart_p = sub.add_parser("charts", help="Generate visualizations from scan data")
    chart_p.add_argument(
        "--chains", type=str, default=",".join(DEFAULT_CHAINS),
        help="Comma-separated chains to scan",
    )

    # ── network ──
    net_p = sub.add_parser("network", help="Wallet network & cluster analysis (KILLER FEATURE)")
    net_p.add_argument("--address", "-a", nargs="+", required=True, help="One or more seed wallet addresses")
    net_p.add_argument("--chain", "-c", default="ethereum", help="Chain (default: ethereum)")
    net_p.add_argument("--hops", type=int, default=2, help="Network expansion depth (default: 2)")
    net_p.add_argument("--max-nodes", type=int, default=30, help="Max nodes to discover (default: 30)")
    net_p.add_argument("--output", "-o", type=str, default=None, help="Save report to file")

    # ── perps ──
    perp_p = sub.add_parser("perps", help="Smart Money perpetual trading intelligence (Hyperliquid)")
    perp_p.add_argument("--limit", type=int, default=50, help="Number of recent trades (default: 50)")
    perp_p.add_argument("--output", "-o", type=str, default=None, help="Save report to file")

    # ── watch ──
    watch_p = sub.add_parser("watch", help="Continuous monitoring — scans every N minutes, alerts on new signals")
    watch_p.add_argument(
        "--chains", type=str, default=",".join(DEFAULT_CHAINS),
        help=f"Comma-separated chains to scan (default: {','.join(DEFAULT_CHAINS)})",
    )
    watch_p.add_argument(
        "--interval", type=int, default=5,
        help="Minutes between scan cycles (default: 5)",
    )
    watch_p.add_argument(
        "--webhook", type=str, default=None,
        help="Webhook URL to POST new signal alerts to",
    )
    watch_p.add_argument(
        "--output", "-o", type=str, default=None,
        help="File to append new signals to (one per line)",
    )

    # ── portfolio ──
    port_p = sub.add_parser("portfolio", help="Deep-dive wallet portfolio — holdings, labels, PnL")
    port_p.add_argument("--address", "-a", required=True, help="Wallet address")
    port_p.add_argument("--chain", "-c", default="ethereum", help="Chain (default: ethereum)")
    port_p.add_argument("--top", type=int, default=20, help="Max tokens to show (default: 20)")

    # ── quote ──
    quote_p = sub.add_parser("quote", help="Get DEX trade quotes via Nansen")
    quote_p.add_argument(
        "--from-token", required=True,
        help="Source token (symbol like ETH, SOL, or contract address)",
    )
    quote_p.add_argument(
        "--to-token", required=True,
        help="Destination token (symbol like USDC, or contract address)",
    )
    quote_p.add_argument(
        "--amount", required=True,
        help="Amount in human-readable token units (e.g. 1.5)",
    )
    quote_p.add_argument(
        "--chain", "-c", default="base",
        choices=["base", "solana"],
        help="Chain (default: base). Only base and solana support trade quotes.",
    )
    quote_p.add_argument(
        "--slippage", type=float, default=None,
        help="Slippage tolerance as decimal (e.g. 0.03 for 3%%)",
    )

    # ── daily ──
    daily_p = sub.add_parser("daily", help="Full daily pipeline: scan -> signals -> alerts -> charts -> AI analysis -> report")
    daily_p.add_argument(
        "--chains", type=str, default=",".join(DEFAULT_CHAINS),
        help="Comma-separated chains to scan",
    )
    daily_p.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output path (default: reports/daily_YYYY-MM-DD.md)",
    )
    daily_p.add_argument(
        "--no-ai", action="store_true", default=False,
        help="Skip AI narrative analysis step",
    )
    daily_p.add_argument(
        "--ai-mode", type=str, default="fast", choices=["fast", "expert"],
        help="AI agent mode: fast (default) or expert (deeper analysis)",
    )

    # ── analyze ──
    analyze_p = sub.add_parser("analyze", help="Scan chains and synthesize a narrative with Nansen AI agent")
    analyze_p.add_argument(
        "--chains", type=str, default=",".join(DEFAULT_CHAINS),
        help="Comma-separated chains to scan",
    )
    analyze_p.add_argument(
        "--mode", type=str, default="fast", choices=["fast", "expert"],
        help="AI agent mode: fast (default) or expert (deeper analysis)",
    )
    analyze_p.add_argument(
        "--top", type=int, default=10,
        help="Number of top signals to send to AI (default: 10)",
    )
    analyze_p.add_argument(
        "--output", "-o", type=str, default=None,
        help="Save report to file",
    )

    # ── exit-signals ──
    exit_p = sub.add_parser("exit-signals", help="Detect smart money EXIT signals (tokens being dumped)")
    exit_p.add_argument(
        "--chains", type=str, default=",".join(DEFAULT_CHAINS),
        help=f"Comma-separated chains to scan (default: {','.join(DEFAULT_CHAINS)})",
    )
    exit_p.add_argument(
        "--top", type=int, default=10,
        help="Show top N exit signals (default: 10)",
    )

    # ── defi ──
    defi_p = sub.add_parser("defi", help="DeFi positions analysis for a wallet")
    defi_p.add_argument("--address", "-a", required=True, help="Wallet address")
    defi_p.add_argument("--chain", "-c", default="ethereum", help="Chain (default: ethereum)")

    # ── search ──
    search_p = sub.add_parser("search", help="Search tokens and entities across Nansen")
    search_p.add_argument("query", help="Search query (e.g. 'ethereum whale buying ONDO')")
    search_p.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")

    # ── history ──
    hist_p = sub.add_parser("history", help="Signal history and trend detection")
    hist_p.add_argument(
        "--days", type=int, default=7,
        help="Lookback window in days (default: 7)",
    )
    hist_p.add_argument(
        "--min", type=int, default=3, dest="min_appearances",
        help="Minimum appearances to count as trending (default: 3)",
    )
    hist_p.add_argument(
        "--chain", type=str, default=None,
        help="Filter history to a specific chain",
    )
    hist_p.add_argument(
        "--record", action="store_true", default=False,
        help="Run a scan and record signals to history before displaying trends",
    )

    # ── prediction ──
    pred_p = sub.add_parser("prediction", help="Prediction market intelligence (Polymarket)")
    pred_p.add_argument(
        "--top", type=int, default=10,
        help="Number of markets/events to display (default: 10)",
    )
    pred_p.add_argument(
        "--sort", type=str, default="volume",
        choices=["volume", "probability", "name"],
        help="Sort results by (default: volume)",
    )
    pred_p.add_argument(
        "--query", "-q", type=str, default="",
        help="Search query to filter markets/events",
    )
    pred_p.add_argument(
        "--events", action="store_true", default=False,
        help="Show event-level screener instead of individual markets",
    )

    return parser


# ── Command Handlers ─────────────────────────────────────────────────────────

async def cmd_scan(args: argparse.Namespace):
    """Run a full multi-chain smart money scan."""
    if args.all_chains:
        from config import ALL_CHAINS
        chains = ALL_CHAINS
    else:
        chains = [c.strip() for c in args.chains.split(",") if c.strip()]
    show_banner()

    console.print(f"[bold cyan]Scanning {len(chains)} chains:[/bold cyan] {', '.join(chains)}\n")

    # Run scans with progress
    all_results = {}
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        for chain in chains:
            task = progress.add_task(f"Scanning {chain}...", total=None)
            chain_results = await _scan_chain_with_display(chain)
            all_results[chain] = chain_results
            progress.update(task, completed=True, description=f"[green]{chain} done")

    # Analyze signals
    console.print("\n[bold cyan]Analyzing signals...[/bold cyan]")
    all_signals = analyze_all_chains(all_results)
    ranked = rank_signals(all_signals)

    # Display results
    _display_signal_table(ranked)
    _display_api_stats()

    # Record signals to history
    flat_signals = [sig for sigs in all_signals.values() for sig in sigs]
    record_signals(flat_signals)

    # Save latest results JSON for landing page
    save_latest_results(flat_signals, chains)

    # Save report if requested
    if args.output or True:  # Always save by default
        output_path = args.output or _default_report_path("scan")
        report = generate_scan_report(all_signals, all_results, chains)
        saved = save_report(report, output_path)
        console.print(f"\n[bold green]Report saved:[/bold green] {saved}")


async def cmd_profile(args: argparse.Namespace):
    """Run a wallet deep-dive."""
    show_banner()

    console.print(f"[bold cyan]Profiling wallet:[/bold cyan] {args.address}")
    console.print(f"[bold cyan]Chain:[/bold cyan] {args.chain} | [bold cyan]Days:[/bold cyan] {args.days}\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching wallet data...", total=None)
        results = await profile_wallet(args.address, args.chain, args.days)
        progress.update(task, completed=True, description="[green]Profile complete")

    # Display results summary
    _display_profile_summary(results, args.address)
    _display_api_stats()

    # Save report
    if args.output or True:
        output_path = args.output or _default_report_path(f"profile_{args.address[:8]}")
        report = generate_wallet_report(args.address, args.chain, results)
        saved = save_report(report, output_path)
        console.print(f"\n[bold green]Report saved:[/bold green] {saved}")


async def cmd_signals(args: argparse.Namespace):
    """Scan and detect signals, display ranked."""
    chains = [c.strip() for c in args.chains.split(",") if c.strip()]
    show_banner()

    console.print(f"[bold cyan]Signal detection across:[/bold cyan] {', '.join(chains)}\n")

    # Scan first
    all_results = {}
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        for chain in chains:
            task = progress.add_task(f"Scanning {chain}...", total=None)
            chain_results = await _scan_chain_with_display(chain)
            all_results[chain] = chain_results
            progress.update(task, completed=True, description=f"[green]{chain} done")

    # Detect signals
    console.print("\n[bold cyan]Detecting signals...[/bold cyan]\n")
    all_signals = analyze_all_chains(all_results)
    ranked = rank_signals(all_signals, args.top)

    # Display
    _display_signal_table(ranked)
    _display_api_stats()

    # Save if requested
    if args.output:
        report = generate_signals_report(ranked)
        saved = save_report(report, args.output)
        console.print(f"\n[bold green]Report saved:[/bold green] {saved}")


async def cmd_report(args: argparse.Namespace):
    """Full scan + signal detection + report generation."""
    chains = [c.strip() for c in args.chains.split(",") if c.strip()]
    show_banner()

    console.print("[bold cyan]Generating full intelligence report...[/bold cyan]\n")

    # Scan
    all_results = {}
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        for chain in chains:
            task = progress.add_task(f"Scanning {chain}...", total=None)
            chain_results = await _scan_chain_with_display(chain)
            all_results[chain] = chain_results
            progress.update(task, completed=True, description=f"[green]{chain} done")

    # Analyze
    console.print("\n[bold cyan]Analyzing signals...[/bold cyan]")
    all_signals = analyze_all_chains(all_results)
    ranked = rank_signals(all_signals)

    # Display summary
    _display_signal_table(ranked[:10])

    # Generate and save report
    output_path = args.output or _default_report_path("report")
    report = generate_scan_report(all_signals, all_results, chains)
    saved = save_report(report, output_path)

    _display_api_stats()
    console.print(f"\n[bold green]Full report saved:[/bold green] {saved}")


async def cmd_alerts(args: argparse.Namespace):
    """Run the alert engine and display triggered alerts."""
    chains = [c.strip() for c in args.chains.split(",") if c.strip()]
    show_banner()

    console.print(f"[bold cyan]Running alert engine across:[/bold cyan] {', '.join(chains)}\n")

    # Scan
    all_results = {}
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        for chain in chains:
            task = progress.add_task(f"Scanning {chain}...", total=None)
            chain_results = await _scan_chain_with_display(chain)
            all_results[chain] = chain_results
            progress.update(task, completed=True, description=f"[green]{chain} done")

    # Signals
    console.print("\n[bold cyan]Detecting signals...[/bold cyan]")
    all_signals = analyze_all_chains(all_results)

    # Alerts
    console.print("[bold cyan]Checking alert rules...[/bold cyan]\n")
    engine = AlertEngine()
    alerts = await engine.run(
        chains=chains,
        scan_results=all_results,
        all_signals=all_signals,
    )

    # Display
    if alerts:
        table = Table(title="Triggered Alerts", title_style="bold red")
        table.add_column("#", style="dim", width=3)
        table.add_column("Severity", width=10)
        table.add_column("Rule", style="cyan", width=24)
        table.add_column("Summary", min_width=50)

        severity_icons = {
            Severity.CRITICAL: "[bold red]CRIT[/bold red]",
            Severity.HIGH: "[bold yellow]HIGH[/bold yellow]",
            Severity.MEDIUM: "[yellow]MED[/yellow]",
            Severity.LOW: "[dim]LOW[/dim]",
        }

        for i, alert in enumerate(alerts, 1):
            table.add_row(
                str(i),
                severity_icons.get(alert.severity, ""),
                alert.rule_name,
                alert.summary,
            )

        console.print(table)
    else:
        console.print("[dim]No alerts triggered (all rules within cooldown or no matches).[/dim]")

    _display_api_stats()


async def cmd_charts(args: argparse.Namespace):
    """Generate visualizations from scan data."""
    chains = [c.strip() for c in args.chains.split(",") if c.strip()]
    show_banner()

    console.print(f"[bold cyan]Generating charts for:[/bold cyan] {', '.join(chains)}\n")

    # Scan
    all_results = {}
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        for chain in chains:
            task = progress.add_task(f"Scanning {chain}...", total=None)
            chain_results = await _scan_chain_with_display(chain)
            all_results[chain] = chain_results
            progress.update(task, completed=True, description=f"[green]{chain} done")

    # Signals (needed for some charts)
    console.print("\n[bold cyan]Analyzing signals...[/bold cyan]")
    all_signals = analyze_all_chains(all_results)

    # Generate charts
    console.print("[bold cyan]Generating charts...[/bold cyan]\n")
    chart_paths = generate_all_charts(all_results, all_signals)

    if chart_paths:
        for name, path in chart_paths.items():
            console.print(f"  [green]✓[/green] {name}: {path}")
        console.print(f"\n[bold green]{len(chart_paths)} charts generated.[/bold green]")
    else:
        console.print("[dim]No charts generated (insufficient data).[/dim]")

    _display_api_stats()


async def cmd_watch(args: argparse.Namespace):
    """Continuous monitoring — scans every N minutes, alerts on new signals."""
    chains = [c.strip() for c in args.chains.split(",") if c.strip()]
    interval = args.interval
    show_banner()

    console.print(Panel(
        "[bold]Watch Mode — Continuous Smart Money Monitoring[/bold]\n"
        f"Chains: {', '.join(chains)} | Interval: {interval}min\n"
        "Press Ctrl+C to stop",
        border_style="green",
    ))

    previous_signal_keys: set[tuple[str, str, str]] = set()  # (chain, token, type)
    cycle = 0
    total_signals_seen = 0
    start_time = datetime.now(timezone.utc)

    while True:
        cycle += 1
        now = datetime.now(timezone.utc)
        uptime = now - start_time
        uptime_str = str(uptime).split(".")[0]  # strip microseconds

        console.print(f"\n[cyan]{'━' * 60}[/cyan]")
        console.print(
            f"[cyan]Cycle {cycle}[/cyan] — "
            f"{now.strftime('%H:%M:%S UTC')} — "
            f"[dim]uptime {uptime_str}[/dim]"
        )
        console.print(f"[cyan]{'━' * 60}[/cyan]")

        # Run scan
        all_results = {}
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            for chain in chains:
                task = progress.add_task(f"Scanning {chain}...", total=None)
                chain_results = await _scan_chain_with_display(chain)
                all_results[chain] = chain_results
                progress.update(task, completed=True, description=f"[green]{chain} done")

        # Detect signals
        all_signals = analyze_all_chains(all_results)
        flat_signals = [sig for sigs in all_signals.values() for sig in sigs]
        total_signals_seen += len(flat_signals)

        # Find NEW signals not in previous set
        current_signal_keys = {(sig.chain, sig.token, sig.type) for sig in flat_signals}
        new_signals = [
            sig for sig in flat_signals
            if (sig.chain, sig.token, sig.type) not in previous_signal_keys
        ]

        # Dashboard summary
        console.print(
            f"Scanned {len(chains)} chains | "
            f"{len(flat_signals)} total signals | "
            f"[bold green]{len(new_signals)} NEW[/bold green] | "
            f"[dim]lifetime: {total_signals_seen}[/dim]"
        )

        if new_signals:
            # Sort new signals by score
            new_signals.sort(key=lambda s: s.score, reverse=True)

            table = Table(title="New Signals Detected", title_style="bold green")
            table.add_column("#", style="dim", width=3)
            table.add_column("Sev", width=4)
            table.add_column("Chain", style="cyan", width=10)
            table.add_column("Token", style="bold", width=10)
            table.add_column("Type", width=16)
            table.add_column("Signal", min_width=40)
            table.add_column("Score", justify="right", width=6)

            severity_icons = {
                Severity.CRITICAL: "[bold red]CRIT[/bold red]",
                Severity.HIGH: "[bold yellow]HIGH[/bold yellow]",
                Severity.MEDIUM: "[yellow]MED[/yellow]",
                Severity.LOW: "[dim]LOW[/dim]",
            }

            for i, sig in enumerate(new_signals, 1):
                style = SEVERITY_STYLES.get(sig.severity, "")
                table.add_row(
                    str(i),
                    severity_icons.get(sig.severity, ""),
                    sig.chain,
                    sig.token[:10],
                    sig.type,
                    sig.summary[:80],
                    f"{sig.score:.0f}",
                    style=style if sig.severity == Severity.CRITICAL else "",
                )

            console.print(table)

            # Optional: append to file
            if args.output:
                try:
                    with open(args.output, "a") as f:
                        for sig in new_signals:
                            f.write(
                                f"{now.isoformat()} | {sig.chain} | {sig.token} | "
                                f"{sig.severity.value} | {sig.type} | {sig.summary}\n"
                            )
                    console.print(f"[dim]Appended {len(new_signals)} signals to {args.output}[/dim]")
                except Exception as e:
                    console.print(f"[red]File write error: {e}[/red]")

            # Optional: webhook
            if args.webhook:
                try:
                    import aiohttp
                    payload = {
                        "text": f"NansenScope: {len(new_signals)} new signals detected",
                        "cycle": cycle,
                        "signals": [
                            {
                                "chain": sig.chain,
                                "token": sig.token,
                                "type": sig.type,
                                "severity": sig.severity.value,
                                "summary": sig.summary,
                                "score": sig.score,
                            }
                            for sig in new_signals
                        ],
                    }
                    async with aiohttp.ClientSession() as session:
                        await session.post(
                            args.webhook,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=10),
                        )
                    console.print("[dim]Webhook delivered[/dim]")
                except Exception as e:
                    console.print(f"[red]Webhook error: {e}[/red]")
        else:
            console.print("[dim]No new signals this cycle[/dim]")

        previous_signal_keys = current_signal_keys

        # Wait
        _display_api_stats()
        console.print(f"[dim]Next scan in {interval} minutes...[/dim]")
        await asyncio.sleep(interval * 60)


async def ask_nansen_agent(prompt: str, mode: str = "fast") -> str | None:
    """
    Ask Nansen's AI agent a question.

    Args:
        prompt: The question/prompt to send to Nansen agent.
        mode: 'fast' (default, cheaper) or 'expert' (deeper analysis).

    Returns:
        The agent's response text, or None if the call failed.
    """
    from scanner import _run_nansen

    cmd_args = ["agent", prompt]
    if mode == "expert":
        cmd_args.append("--expert")

    result = await _run_nansen(args=cmd_args, endpoint="agent")

    if not result.success:
        log.warning("Nansen agent call failed: %s", result.error)
        return None

    # The agent returns text (not JSON), so result.data is a string
    if isinstance(result.data, str):
        return result.data.strip() if result.data.strip() else None
    elif isinstance(result.data, dict):
        # If it returns JSON, extract the response text
        return result.data.get("response", result.data.get("answer", str(result.data)))
    return str(result.data) if result.data else None


def _format_signals_for_prompt(signals: list[Signal], chains: list[str], max_signals: int = 10) -> str:
    """Format top signals into a prompt for Nansen AI agent."""
    signal_lines = []
    for sig in signals[:max_signals]:
        signal_lines.append(
            f"- [{sig.severity.value.upper()}] {sig.chain}/{sig.token}: "
            f"{sig.type} — {sig.summary} (score: {sig.score:.0f})"
        )
    signal_list = "\n".join(signal_lines)
    chain_str = ", ".join(chains)

    return (
        f"Analyze these smart money signals detected across {chain_str}:\n\n"
        f"{signal_list}\n\n"
        f"What's the narrative? What are smart money traders positioning for? "
        f"Identify key themes, correlations between signals, and actionable insights."
    )


async def cmd_analyze(args: argparse.Namespace):
    """Scan chains and synthesize a narrative with Nansen AI agent."""
    chains = [c.strip() for c in args.chains.split(",") if c.strip()]
    show_banner()

    console.print(Panel(
        "[bold]AI-Powered Signal Analysis[/bold]\n"
        f"scan → signals → Nansen AI ({args.mode} mode)",
        border_style="cyan",
    ))
    console.print(f"[bold cyan]Chains:[/bold cyan] {', '.join(chains)}\n")

    # Step 1: Scan
    console.print("[bold cyan]Step 1/3:[/bold cyan] Scanning chains...")
    all_results = {}
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        for chain in chains:
            task = progress.add_task(f"Scanning {chain}...", total=None)
            chain_results = await _scan_chain_with_display(chain)
            all_results[chain] = chain_results
            progress.update(task, completed=True, description=f"[green]{chain} done")

    # Step 2: Signals
    console.print("\n[bold cyan]Step 2/3:[/bold cyan] Detecting signals...")
    all_signals = analyze_all_chains(all_results)
    ranked = rank_signals(all_signals, args.top)
    _display_signal_table(ranked)

    if not ranked:
        console.print("[yellow]No signals to analyze. Skipping AI synthesis.[/yellow]")
        _display_api_stats()
        return

    # Step 3: AI Analysis
    console.print(f"\n[bold cyan]Step 3/3:[/bold cyan] AI narrative synthesis ({args.mode} mode)...")
    prompt = _format_signals_for_prompt(ranked, chains, max_signals=args.top)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Asking Nansen AI agent...", total=None)
        narrative = await ask_nansen_agent(prompt, mode=args.mode)
        progress.update(task, completed=True, description="[green]AI analysis complete")

    if narrative:
        console.print(Panel(
            narrative,
            title="Nansen AI — Narrative Analysis",
            title_align="left",
            border_style="cyan",
            padding=(1, 2),
        ))
    else:
        console.print("[yellow]AI agent unavailable or returned no response. Skipping narrative.[/yellow]")

    _display_api_stats()

    # Save report if requested
    if args.output:
        report_parts = [
            f"# NansenScope AI Analysis — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"\n## Chains: {', '.join(chains)}",
            f"\n## Top Signals ({len(ranked)})\n",
        ]
        for sig in ranked:
            report_parts.append(
                f"- **[{sig.severity.value.upper()}]** {sig.chain}/{sig.token}: "
                f"{sig.type} — {sig.summary} (score: {sig.score:.0f})"
            )
        if narrative:
            report_parts.append(f"\n## AI Narrative Analysis\n\n{narrative}")
        else:
            report_parts.append("\n## AI Narrative Analysis\n\n*AI agent unavailable.*")

        report = "\n".join(report_parts)
        saved = save_report(report, args.output)
        console.print(f"\n[bold green]Report saved:[/bold green] {saved}")


async def cmd_daily(args: argparse.Namespace):
    """Full daily pipeline: scan -> signals -> alerts -> charts -> AI analysis -> report."""
    chains = [c.strip() for c in args.chains.split(",") if c.strip()]
    show_banner()

    total_steps = 5 if getattr(args, "no_ai", False) else 6
    pipeline_desc = "scan → signals → alerts → charts → report"
    if total_steps == 6:
        pipeline_desc = "scan → signals → alerts → charts → AI analysis → report"

    console.print(Panel(
        "[bold]Daily Intelligence Pipeline[/bold]\n"
        f"{pipeline_desc}",
        border_style="green",
    ))
    console.print(f"[bold cyan]Chains:[/bold cyan] {', '.join(chains)}\n")

    # Step 1: Scan
    console.print(f"[bold cyan]Step 1/{total_steps}:[/bold cyan] Scanning chains...")
    all_results = {}
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        for chain in chains:
            task = progress.add_task(f"Scanning {chain}...", total=None)
            chain_results = await _scan_chain_with_display(chain)
            all_results[chain] = chain_results
            progress.update(task, completed=True, description=f"[green]{chain} done")

    # Step 2: Signals
    console.print(f"\n[bold cyan]Step 2/{total_steps}:[/bold cyan] Analyzing signals...")
    all_signals = analyze_all_chains(all_results)
    ranked = rank_signals(all_signals)
    _display_signal_table(ranked[:10])

    # Step 3: Alerts
    console.print(f"\n[bold cyan]Step 3/{total_steps}:[/bold cyan] Running alert engine...")
    engine = AlertEngine()
    alerts = await engine.run(
        chains=chains,
        scan_results=all_results,
        all_signals=all_signals,
    )
    if alerts:
        for alert in alerts:
            console.print(f"  [bold red]ALERT:[/bold red] {alert.summary}")
    else:
        console.print("  [dim]No new alerts triggered.[/dim]")

    # Step 4: Charts
    console.print(f"\n[bold cyan]Step 4/{total_steps}:[/bold cyan] Generating charts...")
    try:
        chart_paths = generate_all_charts(all_results, all_signals)
        for name, path in chart_paths.items():
            console.print(f"  [green]✓[/green] {name}: {path}")
    except Exception as e:
        console.print(f"  [yellow]Chart generation failed: {e}[/yellow]")
        chart_paths = {}

    # Record signals to history
    flat_signals = [sig for sigs in all_signals.values() for sig in sigs]
    record_signals(flat_signals)

    # Step 5 (optional): AI Analysis
    ai_narrative = None
    if not getattr(args, "no_ai", False):
        ai_mode = getattr(args, "ai_mode", "fast")
        console.print(f"\n[bold cyan]Step 5/{total_steps}:[/bold cyan] AI narrative synthesis ({ai_mode} mode)...")

        if ranked:
            prompt = _format_signals_for_prompt(ranked[:10], chains)
            try:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[bold]{task.description}"),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task("Asking Nansen AI agent...", total=None)
                    ai_narrative = await ask_nansen_agent(prompt, mode=ai_mode)
                    progress.update(task, completed=True, description="[green]AI analysis complete")

                if ai_narrative:
                    console.print(Panel(
                        ai_narrative,
                        title="Nansen AI — Narrative Analysis",
                        title_align="left",
                        border_style="cyan",
                        padding=(1, 2),
                    ))
                else:
                    console.print("  [yellow]AI agent returned no response.[/yellow]")
            except Exception as e:
                console.print(f"  [yellow]AI analysis failed: {e}[/yellow]")
        else:
            console.print("  [dim]No signals to analyze, skipping AI.[/dim]")

    # Save latest results JSON for landing page
    save_latest_results(flat_signals, chains)

    # Final Step: Report
    report_step = total_steps
    console.print(f"\n[bold cyan]Step {report_step}/{total_steps}:[/bold cyan] Building report...")
    output_path = args.output or _default_report_path("daily")
    report = generate_scan_report(
        all_signals=all_signals,
        scan_results=all_results,
        chains=chains,
        chart_paths=chart_paths,
        alerts=alerts,
    )

    # Append AI narrative to report if available
    if ai_narrative:
        report += "\n\n## AI Narrative Analysis\n\n" + ai_narrative + "\n"

    saved = save_report(report, output_path)

    _display_api_stats()
    console.print(f"\n[bold green]Daily pipeline complete! Report saved:[/bold green] {saved}")


async def cmd_exit_signals(args: argparse.Namespace):
    """Detect smart money EXIT signals — tokens being dumped."""
    from scanner import get_smart_money_netflows, _run_nansen
    chains = [c.strip() for c in args.chains.split(",") if c.strip()]
    show_banner()

    console.print(Panel(
        "[bold]Smart Money Exit Signal Detection[/bold]\n"
        f"Chains: {', '.join(chains)} | Top: {args.top}",
        border_style="red",
    ))

    exit_signals = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        for chain in chains:
            task = progress.add_task(f"Scanning {chain} for outflows...", total=None)

            # Get netflows and filter for negative (outflows)
            result = await get_smart_money_netflows(chain)
            progress.update(task, completed=True, description=f"[green]{chain} done")

            if not result.success or result.is_empty:
                continue

            data = result.data
            if isinstance(data, str):
                continue

            # Normalize to list
            items = data if isinstance(data, list) else data.get("data", data.get("tokens", [data]))
            if not isinstance(items, list):
                items = [items] if isinstance(items, dict) else []

            for item in items:
                if not isinstance(item, dict):
                    continue

                # Look for negative netflow (outflow)
                netflow = None
                for key in ("netflow", "netFlow", "net_flow", "netflow_usd", "netFlowUsd"):
                    val = item.get(key)
                    if val is not None:
                        try:
                            netflow = float(str(val).replace(",", "").replace("$", ""))
                        except (ValueError, TypeError):
                            pass
                        break

                if netflow is None or netflow >= 0:
                    continue  # We only want negative = outflows

                token = (
                    item.get("token", "") or item.get("symbol", "")
                    or item.get("name", "") or item.get("tokenSymbol", "Unknown")
                )

                # Seller count from data if available
                sellers = 0
                for key in ("sellers", "sellerCount", "seller_count", "uniqueSellers"):
                    val = item.get(key)
                    if val is not None:
                        try:
                            sellers = int(val)
                        except (ValueError, TypeError):
                            pass
                        break

                # Severity based on outflow magnitude + seller count
                abs_outflow = abs(netflow)
                if abs_outflow > 500_000 and sellers >= 3:
                    severity = "CRITICAL"
                elif abs_outflow > 100_000 or sellers >= 3:
                    severity = "HIGH"
                elif abs_outflow > 25_000 or sellers >= 2:
                    severity = "MEDIUM"
                else:
                    severity = "LOW"

                exit_signals.append({
                    "token": str(token),
                    "chain": chain,
                    "outflow": abs_outflow,
                    "sellers": sellers,
                    "severity": severity,
                })

    # Sort by outflow descending
    exit_signals.sort(key=lambda x: x["outflow"], reverse=True)
    exit_signals = exit_signals[:args.top]

    if exit_signals:
        table = Table(title="Smart Money Exit Signals", title_style="bold red", show_lines=False, padding=(0, 1))
        table.add_column("#", style="dim", width=3)
        table.add_column("Token", style="bold", min_width=10)
        table.add_column("Chain", style="cyan", width=12)
        table.add_column("Outflow $", justify="right", min_width=14)
        table.add_column("Sellers", justify="right", width=8)
        table.add_column("Severity", width=10)

        severity_styles = {
            "CRITICAL": "[bold red]CRIT[/bold red]",
            "HIGH": "[bold yellow]HIGH[/bold yellow]",
            "MEDIUM": "[yellow]MED[/yellow]",
            "LOW": "[dim]LOW[/dim]",
        }

        for i, sig in enumerate(exit_signals, 1):
            table.add_row(
                str(i),
                sig["token"][:14],
                sig["chain"],
                f"${sig['outflow']:,.0f}",
                str(sig["sellers"]) if sig["sellers"] else "—",
                severity_styles.get(sig["severity"], sig["severity"]),
            )

        console.print(table)
        console.print(f"\n[bold]{len(exit_signals)} exit signals detected[/bold] — negative netflow = smart money selling")
    else:
        console.print("[dim]No exit signals detected (no negative netflows found).[/dim]")

    _display_api_stats()


async def cmd_defi(args: argparse.Namespace):
    """DeFi positions analysis for a wallet."""
    from scanner import get_portfolio_defi
    show_banner()

    address = args.address
    chain = args.chain

    console.print(Panel(
        f"[bold]DeFi Position Analysis[/bold]\n"
        f"{address} on {chain}",
        border_style="green",
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching DeFi positions...", total=None)
        result = await get_portfolio_defi(address)
        progress.update(task, completed=True, description="[green]DeFi data loaded")

    if not result.success:
        console.print(f"\n[red]Error:[/red] {result.error}")
        _display_api_stats()
        return

    data = result.data

    # Handle string (non-JSON) output
    if isinstance(data, str):
        console.print(Panel(data, title="DeFi Positions", border_style="green"))
        _display_api_stats()
        return

    # Normalize to list of positions
    if isinstance(data, dict):
        positions = data.get("positions", data.get("data", data.get("defi", [data])))
    elif isinstance(data, list):
        positions = data
    else:
        positions = []

    if not isinstance(positions, list):
        positions = [positions] if isinstance(positions, dict) else []

    if not positions:
        console.print("[dim]No DeFi positions found for this wallet.[/dim]")
        _display_api_stats()
        return

    # Build display table
    table = Table(title="DeFi Positions", title_style="bold green", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Protocol", style="cyan", min_width=14)
    table.add_column("Type", min_width=12)
    table.add_column("Asset", style="bold", min_width=10)
    table.add_column("Value", justify="right", min_width=14)
    table.add_column("APY", justify="right", width=8)

    total_value = 0.0

    for i, pos in enumerate(positions, 1):
        if not isinstance(pos, dict):
            continue

        protocol = (
            pos.get("protocol", "") or pos.get("protocolName", "")
            or pos.get("app", "") or pos.get("dapp", "Unknown")
        )
        pos_type = (
            pos.get("type", "") or pos.get("positionType", "")
            or pos.get("category", "") or "—"
        )
        asset = (
            pos.get("asset", "") or pos.get("token", "")
            or pos.get("symbol", "") or pos.get("name", "—")
        )

        # Value extraction
        value = 0.0
        for key in ("value", "valueUsd", "value_usd", "usdValue", "balanceUsd"):
            val = pos.get(key)
            if val is not None:
                try:
                    value = float(str(val).replace(",", "").replace("$", ""))
                except (ValueError, TypeError):
                    pass
                break
        total_value += value

        # APY extraction
        apy_str = "—"
        for key in ("apy", "apr", "yield", "rewardApy"):
            val = pos.get(key)
            if val is not None:
                try:
                    apy_val = float(str(val).replace(",", "").replace("%", ""))
                    apy_str = f"{apy_val:.1f}%"
                except (ValueError, TypeError):
                    apy_str = str(val)
                break

        table.add_row(
            str(i),
            str(protocol)[:20],
            str(pos_type)[:16],
            str(asset)[:14],
            f"${value:,.0f}" if value else "—",
            apy_str,
        )

    console.print(table)
    console.print(f"\n[bold]Total DeFi Exposure:[/bold] ${total_value:,.0f}")

    _display_api_stats()


async def cmd_search(args: argparse.Namespace):
    """Search tokens and entities across Nansen."""
    from scanner import search_nansen
    show_banner()

    query = args.query
    limit = args.limit

    console.print(f"[bold cyan]Searching:[/bold cyan] \"{query}\" (limit: {limit})\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Searching Nansen...", total=None)
        result = await search_nansen(query, limit=limit)
        progress.update(task, completed=True, description="[green]Search complete")

    if not result.success:
        console.print(f"\n[red]Error:[/red] {result.error}")
        _display_api_stats()
        return

    data = result.data

    # Handle string (non-JSON) output
    if isinstance(data, str):
        console.print(Panel(data, title="Search Results", border_style="cyan"))
        _display_api_stats()
        return

    # Normalize to list
    if isinstance(data, dict):
        items = data.get("results", data.get("data", data.get("items", [data])))
    elif isinstance(data, list):
        items = data
    else:
        items = []

    if not isinstance(items, list):
        items = [items] if isinstance(items, dict) else []

    if not items:
        console.print("[dim]No results found.[/dim]")
        _display_api_stats()
        return

    # Build display table
    table = Table(title=f"Search Results — \"{query}\"", title_style="bold cyan", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="bold", min_width=20)
    table.add_column("Type", style="cyan", width=14)
    table.add_column("Chain", width=12)
    table.add_column("Description", min_width=30)

    for i, item in enumerate(items[:limit], 1):
        if not isinstance(item, dict):
            continue

        name = (
            item.get("name", "") or item.get("title", "")
            or item.get("symbol", "") or item.get("label", "Unknown")
        )
        item_type = (
            item.get("type", "") or item.get("entityType", "")
            or item.get("category", "") or "—"
        )
        chain = (
            item.get("chain", "") or item.get("blockchain", "")
            or item.get("network", "") or "—"
        )
        description = (
            item.get("description", "") or item.get("summary", "")
            or item.get("address", "") or "—"
        )
        # Truncate description
        if len(str(description)) > 60:
            description = str(description)[:57] + "..."

        table.add_row(str(i), str(name), str(item_type), str(chain), str(description))

    console.print(table)
    console.print(f"\n[bold]{len(items)} results found[/bold]")

    _display_api_stats()


async def cmd_history(args: argparse.Namespace):
    """Signal history and trend detection."""
    show_banner()

    # Optional: run a scan and record signals first
    if args.record:
        chains = DEFAULT_CHAINS
        console.print(f"[bold cyan]Recording scan signals to history...[/bold cyan] ({', '.join(chains)})\n")

        all_results = {}
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            for chain in chains:
                task = progress.add_task(f"Scanning {chain}...", total=None)
                chain_results = await _scan_chain_with_display(chain)
                all_results[chain] = chain_results
                progress.update(task, completed=True, description=f"[green]{chain} done")

        all_signals = analyze_all_chains(all_results)
        flat = [sig for sigs in all_signals.values() for sig in sigs]
        recorded = record_signals(flat)
        console.print(f"[green]Recorded {recorded} signals to history.[/green]\n")

    # Load and display history
    console.print(f"[bold cyan]Signal History[/bold cyan] — last {args.days} days\n")
    history = load_history(days=args.days)

    # Optional chain filter
    if args.chain:
        history = [h for h in history if h.get("chain") == args.chain]

    if not history:
        console.print("[dim]No signals in history for this period.[/dim]")
        return

    # Detect trends
    trends = detect_trends(history, min_appearances=args.min_appearances)

    if trends:
        table = format_trend_table(trends)
        console.print(table)
    else:
        console.print(f"[dim]No tokens with >= {args.min_appearances} appearances in the last {args.days} days.[/dim]")

    # Summary stats
    unique_tokens = len({h.get("token") for h in history})
    unique_chains = sorted({h.get("chain") for h in history})
    timestamps = []
    for h in history:
        try:
            ts = datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00"))
            timestamps.append(ts)
        except (KeyError, ValueError, TypeError):
            continue

    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Total signals: {len(history)}")
    console.print(f"  Unique tokens: {unique_tokens}")
    console.print(f"  Chains: {', '.join(unique_chains)}")
    if timestamps:
        span = max(timestamps) - min(timestamps)
        console.print(f"  Time span: {span.days}d {span.seconds // 3600}h")
    if trends:
        console.print(f"  Trending tokens: {len(trends)}")


async def cmd_quote(args: argparse.Namespace):
    """Get a DEX trade quote via Nansen."""
    show_banner()

    from_token = args.from_token
    to_token = args.to_token
    amount = args.amount
    chain = args.chain

    console.print(Panel(
        f"[bold]DEX Quote[/bold]\n"
        f"{amount} {from_token} → {to_token} on {chain}",
        border_style="green",
    ))

    # Build the nansen trade quote command
    cmd_args = [
        "trade", "quote",
        "--chain", chain,
        "--from", from_token,
        "--to", to_token,
        "--amount", amount,
        "--amount-unit", "token",
    ]
    if args.slippage is not None:
        cmd_args.extend(["--slippage", str(args.slippage)])

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching quote...", total=None)
        result = await _run_nansen_quote(cmd_args)
        progress.update(task, completed=True, description="[green]Quote received")

    if not result.success:
        console.print(f"\n[red]Error:[/red] {result.error}")
        _display_api_stats()
        return

    # Parse and display the quote
    data = result.data

    if isinstance(data, dict):
        # Build a nicely formatted output
        table = Table(title="Quote Details", title_style="bold green", show_lines=True)
        table.add_column("Field", style="cyan", min_width=20)
        table.add_column("Value", style="bold", min_width=30)

        # Common fields to extract
        field_map = [
            ("Input", "inputAmount", "inAmount", "amountIn"),
            ("Output (estimated)", "outputAmount", "outAmount", "amountOut", "expectedOutput"),
            ("Price Impact", "priceImpact", "priceImpactPct"),
            ("Exchange Rate", "rate", "exchangeRate", "price"),
            ("Route", "route", "routePlan"),
            ("Slippage", "slippage", "slippageBps"),
            ("Min Output", "minOutputAmount", "otherAmountThreshold", "minimumReceived"),
            ("Fee", "fee", "fees", "platformFee", "networkFee"),
            ("Gas Estimate", "gas", "gasEstimate", "estimatedGas"),
        ]

        found_any = False
        for label, *keys in field_map:
            for k in keys:
                val = data.get(k)
                if val is not None:
                    found_any = True
                    # Format route lists nicely
                    if isinstance(val, list):
                        if all(isinstance(v, dict) for v in val):
                            # Route plan — extract DEX names
                            route_parts = []
                            for step in val:
                                dex = step.get("swapInfo", {}).get("label", step.get("label", step.get("ammKey", "")))
                                if not dex:
                                    dex = step.get("percent", "")
                                route_parts.append(str(dex))
                            val = " → ".join(route_parts) if route_parts else str(val)
                        else:
                            val = " → ".join(str(v) for v in val)
                    elif isinstance(val, (int, float)):
                        if "impact" in k.lower() or "slippage" in k.lower():
                            # Display as percentage
                            if abs(val) < 1:
                                val = f"{val * 100:.4f}%"
                            else:
                                val = f"{val:.4f}%"
                        elif "bps" in k.lower():
                            val = f"{val / 100:.2f}%"
                    table.add_row(label, str(val))
                    break

        if found_any:
            console.print(table)
        else:
            # Fallback: dump all keys
            console.print("\n[bold cyan]Raw Quote Data:[/bold cyan]")
            for k, v in data.items():
                console.print(f"  [cyan]{k}:[/cyan] {v}")

    elif isinstance(data, str):
        # Non-JSON output — display as-is in a panel
        console.print(Panel(data, title="Quote Result", border_style="green"))
    else:
        console.print(f"\n{data}")

    _display_api_stats()


async def _run_nansen_quote(args: list[str]) -> ScanResult:
    """Run a nansen trade quote command through the standard runner."""
    from scanner import _run_nansen
    return await _run_nansen(args, endpoint="trade/quote")


async def cmd_network(args: argparse.Namespace):
    """Wallet network & cluster analysis."""
    from network import NetworkAnalyzer
    show_banner()

    seeds = args.address  # list of one or more addresses
    seed_display = ", ".join(f"{a[:8]}..." for a in seeds)

    console.print(Panel(
        f"[bold]Wallet Network Analysis[/bold]\n"
        f"Seeds: {seed_display}\n"
        f"Chain: {args.chain} | Hops: {args.hops} | Max nodes: {args.max_nodes}",
        border_style="magenta",
    ))

    analyzer = NetworkAnalyzer(max_hops=args.hops, max_nodes=args.max_nodes)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Building wallet network...", total=None)
        await analyzer.build_network(seeds, args.chain)
        progress.update(task, completed=True, description="[green]Network built")

    # Display results
    console.print(f"\n[bold cyan]Network:[/bold cyan] {len(analyzer.nodes)} nodes, {len(analyzer.edges)} edges\n")

    # Smart Money nodes
    sm_nodes = analyzer.find_smart_money_nodes()
    if sm_nodes:
        table = Table(title="Smart Money Nodes", title_style="bold magenta")
        table.add_column("Address", style="cyan", width=14)
        table.add_column("Labels", min_width=30)
        table.add_column("PnL", justify="right", width=14)
        table.add_column("Connections", justify="right", width=12)
        for node in sm_nodes[:10]:
            table.add_row(
                f"{node.address[:6]}...{node.address[-4:]}",
                ", ".join(node.labels[:3]) or "—",
                f"${node.pnl_usd:,.0f}" if node.pnl_usd else "—",
                str(node.connection_count),
            )
        console.print(table)

    # Clusters
    clusters = analyzer.detect_clusters()
    if clusters:
        console.print(f"\n[bold cyan]Wallet Clusters:[/bold cyan] {len(clusters)} detected\n")
        for cluster in clusters[:5]:
            labels = ", ".join(f"{k}({v})" for k, v in
                              sorted(cluster.label_summary.items(),
                                     key=lambda x: x[1], reverse=True)[:3])
            console.print(f"  Cluster #{cluster.id}: {cluster.size} wallets | "
                          f"PnL: ${cluster.total_pnl:,.0f} | {labels or 'unlabeled'}")

    # Central nodes
    central = analyzer.find_central_nodes()
    if central:
        console.print(f"\n[bold cyan]Most Connected:[/bold cyan]")
        for addr, degree in central:
            node = analyzer.nodes.get(addr)
            label = ", ".join(node.labels[:2]) if node and node.labels else "unlabeled"
            console.print(f"  {addr[:10]}... — {degree} connections ({label})")

    # Bubble map removed — replaced by interactive HTML map below

    # Generate interactive HTML network map
    try:
        from network import generate_network_html
        html_path = generate_network_html(
            nodes=analyzer.nodes,
            edges=analyzer.edges,
            clusters=clusters,
            output_path="reports/charts/network_map.html",
        )
        console.print(f"[green]✓[/green] Interactive map: {html_path}")
    except Exception as e:
        console.print(f"[yellow]HTML map generation failed: {e}[/yellow]")

    # Save report
    output_path = args.output or _default_report_path(f"network_{seeds[0][:8]}")
    report = analyzer.generate_report()
    saved = save_report(report, output_path)

    _display_api_stats()
    console.print(f"\n[bold green]Network report saved:[/bold green] {saved}")
    console.print("[green]✓[/green] Command completed successfully")


async def cmd_perps(args: argparse.Namespace):
    """Smart Money perpetual trading intelligence."""
    from scanner import get_smart_money_perp_trades
    from perps import parse_perp_trades, analyze_perp_activity, detect_perp_signals, generate_perp_report
    show_banner()

    console.print(Panel(
        "[bold]Smart Money Perpetual Trading Intelligence[/bold]\n"
        "Hyperliquid — Real-time SM positions",
        border_style="red",
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching perp trades...", total=None)
        result = await get_smart_money_perp_trades(limit=args.limit)
        progress.update(task, completed=True, description="[green]Perp data loaded")

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        return

    positions = parse_perp_trades(result.data)
    summary = analyze_perp_activity(positions)
    signals = detect_perp_signals(positions, min_value_usd=500)

    # Display summary
    sentiment_color = "green" if "bullish" in summary.sentiment else "red" if "bearish" in summary.sentiment else "yellow"
    console.print(f"\n[bold]Positions:[/bold] {summary.total_positions} | "
                  f"[bold]Volume:[/bold] ${summary.total_volume_usd:,.0f} | "
                  f"[bold]Traders:[/bold] {summary.unique_traders}")
    console.print(f"[bold]L/S Ratio:[/bold] {summary.long_short_ratio:.2f} "
                  f"[{sentiment_color}]({summary.sentiment})[/{sentiment_color}]\n")

    # Token breakdown
    if summary.top_tokens:
        table = Table(title="Top Tokens by Perp Volume", title_style="bold red")
        table.add_column("Token", style="bold", width=10)
        table.add_column("Volume", justify="right", width=12)
        table.add_column("Trades", justify="right", width=8)
        table.add_column("Long", justify="right", style="green", width=12)
        table.add_column("Short", justify="right", style="red", width=12)
        for t in summary.top_tokens[:10]:
            table.add_row(
                t["token"],
                f"${t['total_vol']:,.0f}",
                str(t["trade_count"]),
                f"${t['long_vol']:,.0f}",
                f"${t['short_vol']:,.0f}",
            )
        console.print(table)

    # Signals
    if signals:
        console.print(f"\n[bold cyan]Perp Signals:[/bold cyan] {len(signals)}")
        for sig in signals[:10]:
            icon = "🟢" if "long" in sig.type.lower() else "🔴"
            console.print(f"  {icon} [{sig.severity.value}] {sig.summary}")

    # Save report
    if args.output or True:
        output_path = args.output or _default_report_path("perps")
        report = generate_perp_report(summary)
        saved = save_report(report, output_path)
        console.print(f"\n[bold green]Perp report saved:[/bold green] {saved}")

    _display_api_stats()


async def cmd_portfolio(args: argparse.Namespace):
    """Deep-dive wallet portfolio — holdings, labels, PnL."""
    show_banner()
    address = args.address
    chain = args.chain

    console.print(Panel(
        f"[bold]Wallet Portfolio Analysis[/bold]\n"
        f"{address} on {chain}",
        border_style="green",
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Loading portfolio...", total=3)

        # 1. Get labels
        labels_result = await get_wallet_labels(address, chain)
        progress.update(task, advance=1, description="Labels loaded, fetching holdings...")

        # 2. Get balance/holdings
        balance_result = await get_wallet_balance(address, chain)
        progress.update(task, advance=1, description="Holdings loaded, fetching PnL...")

        # 3. Get PnL summary
        pnl_result = await get_wallet_profile(address, chain)
        progress.update(task, advance=1, description="[green]Portfolio loaded")

    # ── Display labels ──
    if labels_result.success and labels_result.data:
        label_data = labels_result.data
        if isinstance(label_data, list):
            label_names = [
                l.get("label", l.get("name", str(l))) if isinstance(l, dict) else str(l)
                for l in label_data
            ]
        elif isinstance(label_data, dict):
            label_names = label_data.get("labels", [])
            if isinstance(label_names, list):
                label_names = [
                    l.get("label", l.get("name", str(l))) if isinstance(l, dict) else str(l)
                    for l in label_names
                ]
            else:
                label_names = [str(label_names)]
        else:
            label_names = [str(label_data)]

        if label_names:
            console.print(f"\n[bold cyan]Labels:[/bold cyan] {', '.join(label_names)}")
    else:
        if labels_result.error:
            console.print(f"\n[dim]Labels: {labels_result.error}[/dim]")
        else:
            console.print("\n[dim]Labels: none found[/dim]")

    # ── Display holdings table ──
    if balance_result.success and balance_result.data:
        holdings_data = balance_result.data

        # Normalize to list of dicts
        if isinstance(holdings_data, dict):
            holdings_data = holdings_data.get("tokens", holdings_data.get("balances", [holdings_data]))
        if not isinstance(holdings_data, list):
            holdings_data = [holdings_data] if holdings_data else []

        # Extract and sort by USD value
        holdings = []
        for item in holdings_data:
            if isinstance(item, dict):
                token = item.get("token", item.get("symbol", item.get("name", "Unknown")))
                balance = item.get("balance", item.get("amount", "—"))
                usd = float(item.get("usd_value", item.get("valueUsd", item.get("value", 0))) or 0)
                holdings.append({"token": str(token), "balance": str(balance), "usd": usd})
            elif isinstance(item, str):
                holdings.append({"token": item, "balance": "—", "usd": 0})

        # Sort descending by USD value
        holdings.sort(key=lambda h: h["usd"], reverse=True)

        # Calculate total for percentage
        total_usd = sum(h["usd"] for h in holdings) or 1  # avoid div by zero

        # Build table
        table = Table(
            title=f"Holdings — Top {args.top}",
            title_style="bold green",
            show_lines=False,
            padding=(0, 1),
        )
        table.add_column("Token", style="bold", min_width=10)
        table.add_column("Balance", justify="right", min_width=14)
        table.add_column("USD Value", justify="right", min_width=14)
        table.add_column("% of Portfolio", justify="right", min_width=10)

        for h in holdings[:args.top]:
            pct = (h["usd"] / total_usd) * 100
            usd_str = f"${h['usd']:,.0f}" if h["usd"] else "—"
            pct_str = f"{pct:.1f}%" if h["usd"] else "—"
            table.add_row(h["token"], h["balance"], usd_str, pct_str)

        console.print(table)

        if len(holdings) > args.top:
            console.print(f"[dim]  ... and {len(holdings) - args.top} more tokens[/dim]")

        console.print(f"\n[bold]Total Portfolio Value:[/bold] ${total_usd:,.0f}")
    else:
        if balance_result.error:
            console.print(f"\n[red]Holdings error:[/red] {balance_result.error}")
        else:
            console.print("\n[dim]No holdings data available.[/dim]")

    # ── Display PnL summary ──
    if pnl_result.success and pnl_result.data:
        pnl_data = pnl_result.data

        console.print(f"\n[bold cyan]PnL Summary:[/bold cyan]")

        if isinstance(pnl_data, dict):
            # Display key PnL metrics
            metrics = [
                ("Total PnL", "total_pnl", "totalPnl", "pnl"),
                ("Realized PnL", "realized_pnl", "realizedPnl"),
                ("Unrealized PnL", "unrealized_pnl", "unrealizedPnl"),
                ("Win Rate", "win_rate", "winRate"),
                ("Total Trades", "total_trades", "totalTrades", "tradeCount"),
                ("Avg Return", "avg_return", "avgReturn"),
            ]
            for label, *keys in metrics:
                for k in keys:
                    val = pnl_data.get(k)
                    if val is not None:
                        if isinstance(val, (int, float)):
                            if "rate" in k.lower() or "rate" in label.lower():
                                console.print(f"  {label}: {val:.1%}" if val < 1 else f"  {label}: {val:.1f}%")
                            else:
                                color = "green" if val >= 0 else "red"
                                console.print(f"  {label}: [{color}]${val:,.0f}[/{color}]")
                        else:
                            console.print(f"  {label}: {val}")
                        break
        elif isinstance(pnl_data, str):
            console.print(f"  {pnl_data}")
        else:
            console.print(f"  {pnl_data}")
    else:
        if pnl_result.error:
            console.print(f"\n[dim]PnL: {pnl_result.error}[/dim]")
        else:
            console.print("\n[dim]PnL data not available.[/dim]")

    _display_api_stats()


async def cmd_prediction(args: argparse.Namespace):
    """Prediction market intelligence (Polymarket)."""
    show_banner()

    mode = "events" if args.events else "markets"
    console.print(Panel(
        "[bold]Prediction Market Intelligence[/bold]\n"
        f"Source: Polymarket | Mode: {mode} | Top: {args.top}",
        border_style="magenta",
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Fetching prediction {mode}...", total=None)
        if args.events:
            result = await get_prediction_events(query=args.query)
        else:
            result = await get_prediction_markets(top=args.top, query=args.query)
        progress.update(task, completed=True, description=f"[green]Prediction data loaded")

    if not result.success:
        console.print(f"\n[red]Error:[/red] {result.error}")
        _display_api_stats()
        return

    data = result.data

    # Unwrap nested data envelope if present
    if isinstance(data, dict) and "data" in data:
        data = data["data"]

    # Handle string (non-JSON) output
    if isinstance(data, str):
        console.print(Panel(data, title="Prediction Market Data", border_style="magenta"))
        _display_api_stats()
        return

    if not isinstance(data, list):
        data = [data] if isinstance(data, dict) else []

    if not data:
        console.print("[dim]No prediction market data available.[/dim]")
        _display_api_stats()
        return

    # Sort results
    sort_keys = {
        "volume": lambda x: _to_float_safe(x.get("volume") or x.get("volume_usd") or x.get("totalVolume", 0)),
        "probability": lambda x: _to_float_safe(x.get("probability") or x.get("outcomeProbability") or x.get("yes_price", 0)),
        "name": lambda x: (x.get("title") or x.get("question") or x.get("name") or "").lower(),
    }
    sort_fn = sort_keys.get(args.sort, sort_keys["volume"])
    data.sort(key=sort_fn, reverse=(args.sort != "name"))

    # Limit to top N
    data = data[:args.top]

    # Build display table
    table = Table(
        title=f"Polymarket — Top {len(data)} {mode.capitalize()}",
        title_style="bold magenta",
        show_lines=True,
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Event / Market", min_width=30)
    table.add_column("Probability", justify="right", width=12)
    table.add_column("Volume", justify="right", width=14)
    table.add_column("Category", width=16)

    for i, item in enumerate(data, 1):
        name = (
            item.get("title") or item.get("question")
            or item.get("name") or item.get("description") or "—"
        )
        # Truncate long names
        if len(name) > 60:
            name = name[:57] + "..."

        prob = _to_float_safe(
            item.get("probability") or item.get("outcomeProbability")
            or item.get("yes_price") or item.get("bestAsk", 0)
        )
        prob_str = f"{prob * 100:.1f}%" if 0 < prob <= 1 else f"{prob:.1f}%" if prob > 1 else "—"

        vol = _to_float_safe(
            item.get("volume") or item.get("volume_usd")
            or item.get("totalVolume") or item.get("total_volume", 0)
        )
        vol_str = f"${vol:,.0f}" if vol else "—"

        category = (
            item.get("category") or item.get("tag")
            or item.get("tags", [""])[0] if isinstance(item.get("tags"), list) and item.get("tags") else
            item.get("category_name") or "—"
        )
        if isinstance(category, list):
            category = category[0] if category else "—"

        table.add_row(str(i), name, prob_str, vol_str, str(category))

    console.print(table)

    # Cross-reference with scan data if available
    # Check if there are recent scan reports we can reference
    try:
        from pathlib import Path
        import glob
        report_files = sorted(glob.glob("reports/scan_*.md"), reverse=True)
        if report_files:
            console.print(
                f"\n[dim]Tip: Cross-reference with latest scan data: "
                f"{Path(report_files[0]).name}[/dim]"
            )
    except Exception:
        pass

    _display_api_stats()


def _to_float_safe(val) -> float:
    """Safe float conversion for prediction market data."""
    if val is None:
        return 0.0
    try:
        return float(str(val).replace(",", "").replace("$", "").replace("%", ""))
    except (ValueError, TypeError):
        return 0.0


# ── Display Helpers ──────────────────────────────────────────────────────────

async def _scan_chain_with_display(chain: str) -> dict[str, ScanResult]:
    """Scan a chain and return results, used by all commands."""
    from scanner import scan_chain
    return await scan_chain(chain)


def _display_signal_table(signals: list[Signal]):
    """Render signals in a Rich table."""
    if not signals:
        console.print("[dim]No signals detected.[/dim]")
        return

    table = Table(
        title="Smart Money Signals",
        show_lines=False,
        padding=(0, 1),
        title_style="bold cyan",
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Sev", width=4)
    table.add_column("Chain", style="cyan", width=10)
    table.add_column("Token", style="bold", width=10)
    table.add_column("Type", width=16)
    table.add_column("Signal", min_width=40)
    table.add_column("Score", justify="right", width=6)

    severity_icons = {
        Severity.CRITICAL: "[bold red]CRIT[/bold red]",
        Severity.HIGH: "[bold yellow]HIGH[/bold yellow]",
        Severity.MEDIUM: "[yellow]MED[/yellow]",
        Severity.LOW: "[dim]LOW[/dim]",
    }

    for i, sig in enumerate(signals, 1):
        style = SEVERITY_STYLES.get(sig.severity, "")
        table.add_row(
            str(i),
            severity_icons.get(sig.severity, ""),
            sig.chain,
            sig.token[:10],
            sig.type,
            sig.summary[:80],
            f"{sig.score:.0f}",
            style=style if sig.severity == Severity.CRITICAL else "",
        )

    console.print(table)


def _display_profile_summary(results: dict[str, ScanResult], address: str):
    """Display wallet profile results."""
    table = Table(title=f"Wallet Profile: {address[:8]}...{address[-6:]}", title_style="bold cyan")
    table.add_column("Endpoint", style="cyan")
    table.add_column("Status")
    table.add_column("Details", min_width=40)

    for key, result in results.items():
        if result.success:
            detail = _summarize_data(result.data)
            table.add_row(key, "[green]OK[/green]", detail)
        else:
            table.add_row(key, "[red]FAIL[/red]", result.error or "Unknown error")

    console.print(table)


def _display_api_stats():
    """Show API usage statistics."""
    stats = api_tracker.summary
    console.print(
        f"\n[dim]API calls: {stats['total_calls']} | "
        f"Errors: {stats['errors']} | "
        f"Endpoints hit: {len(stats['by_endpoint'])}[/dim]"
    )


def _summarize_data(data) -> str:
    """Create a brief summary of data for display."""
    if data is None:
        return "[dim]No data[/dim]"
    if isinstance(data, list):
        return f"{len(data)} items"
    if isinstance(data, dict):
        keys = list(data.keys())[:5]
        return ", ".join(keys) + ("..." if len(data) > 5 else "")
    if isinstance(data, str):
        return data[:60] + ("..." if len(data) > 60 else "")
    return str(data)[:60]


def _default_report_path(prefix: str) -> str:
    """Generate a default report filename with timestamp."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    return str(Path("reports") / f"{prefix}_{date_str}.md")


# ── Entrypoint ───────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False, rich_tracebacks=True)],
    )

    if not args.command:
        show_banner()
        parser.print_help()
        sys.exit(0)

    # Dispatch command
    commands = {
        "scan": cmd_scan,
        "profile": cmd_profile,
        "signals": cmd_signals,
        "report": cmd_report,
        "alerts": cmd_alerts,
        "charts": cmd_charts,
        "network": cmd_network,
        "perps": cmd_perps,
        "daily": cmd_daily,
        "history": cmd_history,
        "portfolio": cmd_portfolio,
        "watch": cmd_watch,
        "quote": cmd_quote,
        "prediction": cmd_prediction,
        "analyze": cmd_analyze,
        "exit-signals": cmd_exit_signals,
        "defi": cmd_defi,
        "search": cmd_search,
    }

    handler = commands.get(args.command)
    if handler:
        try:
            asyncio.run(handler(args))
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
            _display_api_stats()
            sys.exit(130)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
