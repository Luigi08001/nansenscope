#!/usr/bin/env python3
"""
NansenScope — Daily Scan Script

Standalone script for cron / OpenClaw scheduled execution.
Runs a full pipeline: scan -> signals -> alerts -> charts -> report.
Outputs markdown report to stdout for cron delivery.

Usage:
    python3 skill/scripts/daily_scan.py
    python3 skill/scripts/daily_scan.py --chains ethereum,base,solana
    python3 skill/scripts/daily_scan.py --chains ethereum --webhook https://hooks.example.com/daily
    python3 skill/scripts/daily_scan.py -v
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
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

# ── Constants ────────────────────────────────────────────────────────────────

MAX_STEP_RETRIES = 2
RETRY_DELAY = 5  # seconds


# ── Helpers ──────────────────────────────────────────────────────────────────

def _retry(label: str, fn, *args, retries: int = MAX_STEP_RETRIES, **kwargs):
    """Sync retry wrapper for pipeline steps."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            log.warning("[%s] attempt %d/%d failed: %s", label, attempt, retries, e)
            if attempt < retries:
                time.sleep(RETRY_DELAY)
    raise RuntimeError(f"{label} failed after {retries} attempts: {last_err}") from last_err


async def _retry_async(label: str, fn, *args, retries: int = MAX_STEP_RETRIES, **kwargs):
    """Async retry wrapper for pipeline steps."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            log.warning("[%s] attempt %d/%d failed: %s", label, attempt, retries, e)
            if attempt < retries:
                await asyncio.sleep(RETRY_DELAY)
    raise RuntimeError(f"{label} failed after {retries} attempts: {last_err}") from last_err


def _send_webhook(url: str, payload: dict) -> bool:
    """POST JSON to a webhook URL. Returns True on success."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            log.info("Webhook sent (%d): %s", resp.status, url)
            return True
    except (urllib.error.URLError, OSError) as e:
        log.error("Webhook failed: %s", e)
        return False


# ── Pipeline ─────────────────────────────────────────────────────────────────

async def run_daily_pipeline(
    chains: list[str],
    webhook_url: str | None = None,
) -> tuple[str, dict]:
    """
    Execute the full daily intelligence pipeline.

    Returns:
        (report_text, summary_dict)
    """
    timings: dict[str, float] = {}
    summary = {
        "chains": chains,
        "signals_count": 0,
        "alerts_count": 0,
        "charts_count": 0,
        "report_path": None,
        "status": "success",
        "errors": [],
    }
    t_start = time.monotonic()

    # Step 1: Scan all chains
    log.info("Step 1/5: Scanning %d chains: %s", len(chains), ", ".join(chains))
    t0 = time.monotonic()
    scan_results = await _retry_async("scan", scan_all_chains, chains)
    timings["scan"] = time.monotonic() - t0
    log.info("Scan completed in %.1fs", timings["scan"])

    # Step 2: Detect signals
    log.info("Step 2/5: Analyzing signals...")
    t0 = time.monotonic()
    all_signals = _retry("signals", analyze_all_chains, scan_results)
    ranked = rank_signals(all_signals)
    timings["signals"] = time.monotonic() - t0
    summary["signals_count"] = len(ranked)
    log.info("Found %d signals in %.1fs", len(ranked), timings["signals"])

    # Step 3: Run alert engine
    log.info("Step 3/5: Running alert engine...")
    t0 = time.monotonic()
    engine = AlertEngine()
    try:
        alerts = await _retry_async(
            "alerts", engine.run,
            chains=chains,
            scan_results=scan_results,
            all_signals=all_signals,
        )
    except Exception as e:
        log.error("Alert engine failed (non-fatal): %s", e)
        alerts = []
        summary["errors"].append(f"alerts: {e}")
    timings["alerts"] = time.monotonic() - t0
    summary["alerts_count"] = len(alerts)
    log.info("Alerts: %d triggered in %.1fs", len(alerts), timings["alerts"])

    # Step 4: Generate charts
    log.info("Step 4/5: Generating charts...")
    t0 = time.monotonic()
    try:
        chart_paths = _retry("charts", generate_all_charts, scan_results, all_signals)
    except Exception as e:
        log.warning("Chart generation failed (non-fatal): %s", e)
        chart_paths = {}
        summary["errors"].append(f"charts: {e}")
    timings["charts"] = time.monotonic() - t0
    summary["charts_count"] = len(chart_paths)
    log.info("Charts: %d generated in %.1fs", len(chart_paths), timings["charts"])

    # Step 5: Generate and save report
    log.info("Step 5/5: Building report...")
    t0 = time.monotonic()
    report = generate_scan_report(
        all_signals=all_signals,
        scan_results=scan_results,
        chains=chains,
        chart_paths=chart_paths,
        alerts=alerts,
    )

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    report_path = PROJECT_ROOT / "reports" / f"daily_{date_str}.md"
    save_report(report, report_path)
    timings["report"] = time.monotonic() - t0
    summary["report_path"] = str(report_path)
    log.info("Report saved to %s in %.1fs", report_path, timings["report"])

    # Total timing
    total_elapsed = time.monotonic() - t_start
    timings["total"] = total_elapsed

    # Build summary footer
    summary_text = _build_summary(summary, timings)
    full_report = report + "\n\n" + summary_text

    # Webhook notification
    if webhook_url:
        _send_webhook(webhook_url, {
            "event": "nansenscope.daily",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "timings": {k: round(v, 2) for k, v in timings.items()},
        })

    return full_report, summary


def _build_summary(summary: dict, timings: dict) -> str:
    """Build a human-readable summary block."""
    lines = [
        "---",
        "## Pipeline Summary",
        "",
        f"- **Chains scanned:** {len(summary['chains'])} ({', '.join(summary['chains'])})",
        f"- **Signals detected:** {summary['signals_count']}",
        f"- **Alerts triggered:** {summary['alerts_count']}",
        f"- **Charts generated:** {summary['charts_count']}",
        f"- **Report:** {summary['report_path']}",
        f"- **API calls:** {api_tracker.total_calls} ({api_tracker.errors} errors)",
        "",
        "### Timing",
        "",
    ]
    for step, elapsed in timings.items():
        lines.append(f"- {step}: {elapsed:.1f}s")

    if summary["errors"]:
        lines.extend(["", "### Non-Fatal Errors", ""])
        for err in summary["errors"]:
            lines.append(f"- {err}")

    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="daily_scan",
        description="NansenScope — Daily Intelligence Pipeline",
    )
    parser.add_argument(
        "--chains", type=str, default=",".join(DEFAULT_CHAINS),
        help=f"Comma-separated chains (default: {','.join(DEFAULT_CHAINS)})",
    )
    parser.add_argument(
        "--webhook", type=str, default=None,
        help="Webhook URL to POST summary JSON to",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for daily scan."""
    args = build_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    chains = [c.strip() for c in args.chains.split(",") if c.strip()]

    try:
        report, summary = asyncio.run(run_daily_pipeline(chains, args.webhook))
        # Output report to stdout (for cron capture)
        print(report)
    except KeyboardInterrupt:
        log.warning("Interrupted")
        sys.exit(130)
    except Exception as e:
        log.error("Daily scan failed: %s", e, exc_info=True)
        print(f"# NansenScope Daily Scan — FAILED\n\nError: {e}\n")
        print(f"API calls made: {api_tracker.total_calls}")

        # Send failure webhook
        if args.webhook:
            _send_webhook(args.webhook, {
                "event": "nansenscope.daily.failed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
            })

        sys.exit(1)


if __name__ == "__main__":
    main()
