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
from scanner import ScanResult, profile_wallet, scan_all_chains
from signals import Signal, analyze_all_chains, rank_signals

console = Console()

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

    # ── daily ──
    daily_p = sub.add_parser("daily", help="Full daily pipeline: scan -> signals -> alerts -> perps -> charts -> report")
    daily_p.add_argument(
        "--chains", type=str, default=",".join(DEFAULT_CHAINS),
        help="Comma-separated chains to scan",
    )
    daily_p.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output path (default: reports/daily_YYYY-MM-DD.md)",
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


async def cmd_daily(args: argparse.Namespace):
    """Full daily pipeline: scan -> signals -> alerts -> charts -> report."""
    chains = [c.strip() for c in args.chains.split(",") if c.strip()]
    show_banner()

    console.print(Panel(
        "[bold]Daily Intelligence Pipeline[/bold]\n"
        "scan → signals → alerts → charts → report",
        border_style="green",
    ))
    console.print(f"[bold cyan]Chains:[/bold cyan] {', '.join(chains)}\n")

    # Step 1: Scan
    console.print("[bold cyan]Step 1/5:[/bold cyan] Scanning chains...")
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
    console.print("\n[bold cyan]Step 2/5:[/bold cyan] Analyzing signals...")
    all_signals = analyze_all_chains(all_results)
    ranked = rank_signals(all_signals)
    _display_signal_table(ranked[:10])

    # Step 3: Alerts
    console.print("\n[bold cyan]Step 3/5:[/bold cyan] Running alert engine...")
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
    console.print("\n[bold cyan]Step 4/5:[/bold cyan] Generating charts...")
    try:
        chart_paths = generate_all_charts(all_results, all_signals)
        for name, path in chart_paths.items():
            console.print(f"  [green]✓[/green] {name}: {path}")
    except Exception as e:
        console.print(f"  [yellow]Chart generation failed: {e}[/yellow]")
        chart_paths = {}

    # Step 5: Report
    console.print("\n[bold cyan]Step 5/5:[/bold cyan] Building report...")
    output_path = args.output or _default_report_path("daily")
    report = generate_scan_report(
        all_signals=all_signals,
        scan_results=all_results,
        chains=chains,
        chart_paths=chart_paths,
        alerts=alerts,
    )
    saved = save_report(report, output_path)

    _display_api_stats()
    console.print(f"\n[bold green]Daily pipeline complete! Report saved:[/bold green] {saved}")


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

    # Generate bubble map
    try:
        bubble_path = analyzer.generate_bubble_map()
        if bubble_path:
            console.print(f"\n[green]✓[/green] Bubble map saved: {bubble_path}")
    except Exception as e:
        console.print(f"\n[yellow]Bubble map generation failed: {e}[/yellow]")

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
