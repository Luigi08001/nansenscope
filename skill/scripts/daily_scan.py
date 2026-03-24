#!/usr/bin/env python3
"""
NansenScope — Daily Scan Script

Standalone script for cron / OpenClaw scheduled execution.
Runs a full pipeline: scan -> signals -> alerts -> charts -> report.
Outputs markdown report to stdout for cron delivery.

Usage:
    python3 skill/scripts/daily_scan.py
    python3 skill/scripts/daily_scan.py --chains ethereum,base,solana
"""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DEFAULT_CHAINS, api_tracker
from scanner import scan_all_chains
from signals import analyze_all_chains, rank_signals
from alerts import AlertEngine
from charts import generate_all_charts
from reporter import generate_scan_report, save_report

log = logging.getLogger("nansenscope.daily")


async def run_daily_pipeline(chains: list[str]) -> str:
    """Execute the full daily intelligence pipeline."""

    # Step 1: Scan all chains
    log.info("Scanning %d chains: %s", len(chains), ", ".join(chains))
    scan_results = await scan_all_chains(chains)

    # Step 2: Detect signals
    log.info("Analyzing signals...")
    all_signals = analyze_all_chains(scan_results)
    ranked = rank_signals(all_signals)

    # Step 3: Run alert engine
    log.info("Running alert engine...")
    engine = AlertEngine()
    alerts = await engine.run(
        chains=chains,
        scan_results=scan_results,
        all_signals=all_signals,
    )

    # Step 4: Generate charts
    log.info("Generating charts...")
    try:
        chart_paths = generate_all_charts(scan_results, all_signals)
    except Exception as e:
        log.warning("Chart generation failed: %s", e)
        chart_paths = {}

    # Step 5: Generate report
    log.info("Building report...")
    report = generate_scan_report(
        all_signals=all_signals,
        scan_results=scan_results,
        chains=chains,
        chart_paths=chart_paths,
        alerts=alerts,
    )

    # Step 6: Save report to file
    from datetime import datetime, timezone
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    report_path = PROJECT_ROOT / "reports" / f"daily_{date_str}.md"
    save_report(report, report_path)
    log.info("Report saved to %s", report_path)

    return report


def main() -> None:
    """Entry point for daily scan."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    # Parse chains from argv
    chains = DEFAULT_CHAINS
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--chains" and i < len(sys.argv) - 1:
            chains = [c.strip() for c in sys.argv[i + 1].split(",") if c.strip()]

    try:
        report = asyncio.run(run_daily_pipeline(chains))
        # Output report to stdout (for cron capture)
        print(report)
    except KeyboardInterrupt:
        log.warning("Interrupted")
        sys.exit(130)
    except Exception as e:
        log.error("Daily scan failed: %s", e, exc_info=True)
        # Still output something useful
        print(f"# NansenScope Daily Scan — FAILED\n\nError: {e}\n")
        print(f"API calls made: {api_tracker.total_calls}")
        sys.exit(1)


if __name__ == "__main__":
    main()
