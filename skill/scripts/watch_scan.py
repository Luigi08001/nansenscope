#!/usr/bin/env python3
"""
NansenScope Watch Mode — for OpenClaw cron scheduling.

Runs a single scan cycle and reports only NEW signals compared to last run.
Designed to be called by OpenClaw cron every N minutes.

State file: reports/watch_state.json (auto-managed)

Usage:
    python3 skill/scripts/watch_scan.py
    python3 skill/scripts/watch_scan.py --chains ethereum,base
    python3 skill/scripts/watch_scan.py --webhook https://hooks.example.com/watch
"""

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DEFAULT_CHAINS, api_tracker
from scanner import scan_all_chains
from signals import analyze_all_chains, rank_signals

log = logging.getLogger("nansenscope.watch")

STATE_FILE = PROJECT_ROOT / "reports" / "watch_state.json"
MAX_STATE_SIGNALS = 500  # cap stored signal hashes to prevent unbounded growth


# ── Signal Hashing ───────────────────────────────────────────────────────────

def _signal_hash(sig) -> str:
    """
    Create a stable hash for a signal to detect duplicates.
    Uses chain + token + type + core summary content.
    """
    key = f"{sig.chain}:{sig.token}:{sig.type}:{sig.summary[:100]}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# ── State Management ─────────────────────────────────────────────────────────

def load_state() -> dict[str, Any]:
    """Load previous watch state from disk."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            return data
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Failed to load state file, starting fresh: %s", e)
    return {"seen_hashes": [], "last_run": None, "run_count": 0}


def save_state(state: dict[str, Any]) -> None:
    """Persist watch state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Cap stored hashes
    if len(state.get("seen_hashes", [])) > MAX_STATE_SIGNALS:
        state["seen_hashes"] = state["seen_hashes"][-MAX_STATE_SIGNALS:]
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Webhook ──────────────────────────────────────────────────────────────────

def _send_webhook(url: str, payload: dict) -> bool:
    """POST JSON to a webhook URL."""
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


# ── Core ─────────────────────────────────────────────────────────────────────

async def run_watch_cycle(
    chains: list[str],
    webhook_url: str | None = None,
) -> str:
    """
    Run one watch cycle:
    1. Scan chains
    2. Detect signals
    3. Compare against state file
    4. Report only new signals
    5. Update state

    Returns formatted text suitable for OpenClaw delivery.
    """
    t_start = time.monotonic()
    state = load_state()
    seen = set(state.get("seen_hashes", []))

    # Scan
    log.info("Scanning %d chains: %s", len(chains), ", ".join(chains))
    try:
        scan_results = await scan_all_chains(chains)
    except Exception as e:
        log.error("Scan failed: %s", e)
        return f"NansenScope Watch — SCAN FAILED: {e}"

    # Detect signals
    all_signals = analyze_all_chains(scan_results)
    ranked = rank_signals(all_signals)

    # Find new signals
    new_signals = []
    new_hashes = []
    for sig in ranked:
        h = _signal_hash(sig)
        if h not in seen:
            new_signals.append(sig)
            new_hashes.append(h)

    elapsed = time.monotonic() - t_start

    # Update state
    state["seen_hashes"] = list(seen | set(new_hashes))
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["run_count"] = state.get("run_count", 0) + 1
    save_state(state)

    # Format output
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not new_signals:
        output = (
            f"**NansenScope Watch** — {now_str}\n"
            f"Scanned {len(chains)} chains in {elapsed:.1f}s — no new signals.\n"
            f"Total signals this cycle: {len(ranked)} | API calls: {api_tracker.total_calls}"
        )
        log.info("No new signals (total: %d, elapsed: %.1fs)", len(ranked), elapsed)
    else:
        lines = [
            f"**NansenScope Watch** — {now_str}",
            f"{len(new_signals)} new signal(s) detected across {len(chains)} chains ({elapsed:.1f}s):",
            "",
        ]
        for i, sig in enumerate(new_signals, 1):
            sev = sig.severity.value.upper()
            lines.append(f"{i}. **[{sev}]** {sig.chain} / {sig.token} — {sig.type}: {sig.summary}")
        lines.extend([
            "",
            f"Total signals this cycle: {len(ranked)} | New: {len(new_signals)} | "
            f"API calls: {api_tracker.total_calls}",
        ])
        output = "\n".join(lines)
        log.info("%d new signals (total: %d, elapsed: %.1fs)", len(new_signals), len(ranked), elapsed)

    # Webhook
    if webhook_url and new_signals:
        _send_webhook(webhook_url, {
            "event": "nansenscope.watch",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "new_signals": len(new_signals),
            "total_signals": len(ranked),
            "chains": chains,
            "signals": [
                {
                    "chain": s.chain,
                    "token": s.token,
                    "type": s.type,
                    "severity": s.severity.value,
                    "summary": s.summary,
                    "score": s.score,
                }
                for s in new_signals[:50]  # cap webhook payload
            ],
        })

    return output


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="watch_scan",
        description="NansenScope Watch — single-cycle signal monitor for cron",
    )
    parser.add_argument(
        "--chains", type=str, default=",".join(DEFAULT_CHAINS),
        help=f"Comma-separated chains (default: {','.join(DEFAULT_CHAINS)})",
    )
    parser.add_argument(
        "--webhook", type=str, default=None,
        help="Webhook URL to POST new signals to",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Clear state file and start fresh",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> None:
    args = build_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        log.info("State file cleared: %s", STATE_FILE)

    chains = [c.strip() for c in args.chains.split(",") if c.strip()]

    try:
        output = asyncio.run(run_watch_cycle(chains, args.webhook))
        print(output)
    except KeyboardInterrupt:
        log.warning("Interrupted")
        sys.exit(130)
    except Exception as e:
        log.error("Watch scan failed: %s", e, exc_info=True)
        print(f"NansenScope Watch — FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
