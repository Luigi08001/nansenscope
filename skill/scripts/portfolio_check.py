#!/usr/bin/env python3
"""
NansenScope Portfolio Monitor — track specific wallets.

Checks wallet holdings and alerts on significant changes compared to
the last check. Reads wallet list from config/watched_wallets.json or
command-line args.

Designed for OpenClaw cron scheduling — runs once and exits.

State file: reports/portfolio_state.json (auto-managed)

Usage:
    python3 skill/scripts/portfolio_check.py
    python3 skill/scripts/portfolio_check.py --wallets 0xabc...,0xdef... --chain base
    python3 skill/scripts/portfolio_check.py --threshold 20 --webhook https://hooks.example.com/portfolio
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
from typing import Any

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import api_tracker
from scanner import get_wallet_balance, get_wallet_labels, get_wallet_profile

log = logging.getLogger("nansenscope.portfolio")

WALLETS_CONFIG = PROJECT_ROOT / "config" / "watched_wallets.json"
STATE_FILE = PROJECT_ROOT / "reports" / "portfolio_state.json"
DEFAULT_THRESHOLD_PCT = 10.0  # minimum % change to report


# ── State Management ─────────────────────────────────────────────────────────

def load_state() -> dict[str, Any]:
    """Load previous portfolio state."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Failed to load state: %s", e)
    return {"wallets": {}, "last_run": None}


def save_state(state: dict[str, Any]) -> None:
    """Persist portfolio state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_watched_wallets() -> list[dict[str, str]]:
    """
    Load wallet list from config file.

    Expected format:
    [
        {"address": "0xabc...", "chain": "ethereum", "label": "Whale A"},
        {"address": "0xdef...", "chain": "base", "label": "Fund B"}
    ]
    """
    if WALLETS_CONFIG.exists():
        try:
            return json.loads(WALLETS_CONFIG.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Failed to load watched wallets config: %s", e)
    return []


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


# ── Portfolio Analysis ───────────────────────────────────────────────────────

async def check_wallet(
    address: str,
    chain: str,
    previous: dict | None,
    threshold_pct: float,
) -> dict[str, Any]:
    """
    Check a single wallet's holdings and compare against previous state.

    Returns dict with current holdings and any significant changes.
    """
    result = {
        "address": address,
        "chain": chain,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "holdings": {},
        "total_usd": 0.0,
        "changes": [],
        "error": None,
    }

    # Fetch current balance
    try:
        balance_result = await get_wallet_balance(address, chain)
        if not balance_result.success:
            result["error"] = balance_result.error or "Balance fetch failed"
            return result
    except Exception as e:
        result["error"] = str(e)
        return result

    # Parse holdings from balance data
    holdings = {}
    total_usd = 0.0

    if isinstance(balance_result.data, list):
        for item in balance_result.data:
            token = item.get("symbol") or item.get("token") or "UNKNOWN"
            usd_value = float(item.get("value_usd") or item.get("usd_value") or 0)
            amount = float(item.get("amount") or item.get("balance") or 0)
            holdings[token] = {"amount": amount, "usd_value": usd_value}
            total_usd += usd_value
    elif isinstance(balance_result.data, dict):
        for token, info in balance_result.data.items():
            if isinstance(info, dict):
                usd_value = float(info.get("value_usd") or info.get("usd_value") or 0)
                amount = float(info.get("amount") or info.get("balance") or 0)
            else:
                usd_value = float(info) if info else 0
                amount = 0
            holdings[token] = {"amount": amount, "usd_value": usd_value}
            total_usd += usd_value

    result["holdings"] = holdings
    result["total_usd"] = total_usd

    # Compare with previous state
    if previous and previous.get("holdings"):
        prev_holdings = previous["holdings"]
        prev_total = previous.get("total_usd", 0)

        # Check total portfolio change
        if prev_total > 0:
            total_change_pct = ((total_usd - prev_total) / prev_total) * 100
            if abs(total_change_pct) >= threshold_pct:
                result["changes"].append({
                    "type": "portfolio_total",
                    "token": "TOTAL",
                    "change_pct": round(total_change_pct, 2),
                    "prev_usd": round(prev_total, 2),
                    "curr_usd": round(total_usd, 2),
                })

        # Check individual token changes
        all_tokens = set(list(holdings.keys()) + list(prev_holdings.keys()))
        for token in all_tokens:
            curr = holdings.get(token, {})
            prev = prev_holdings.get(token, {})
            curr_usd = curr.get("usd_value", 0)
            prev_usd = prev.get("usd_value", 0)

            # New position
            if token not in prev_holdings and curr_usd > 100:
                result["changes"].append({
                    "type": "new_position",
                    "token": token,
                    "curr_usd": round(curr_usd, 2),
                })
            # Exited position
            elif token not in holdings and prev_usd > 100:
                result["changes"].append({
                    "type": "exited_position",
                    "token": token,
                    "prev_usd": round(prev_usd, 2),
                })
            # Significant change
            elif prev_usd > 100:
                change_pct = ((curr_usd - prev_usd) / prev_usd) * 100
                if abs(change_pct) >= threshold_pct:
                    result["changes"].append({
                        "type": "holding_change",
                        "token": token,
                        "change_pct": round(change_pct, 2),
                        "prev_usd": round(prev_usd, 2),
                        "curr_usd": round(curr_usd, 2),
                    })

    return result


async def run_portfolio_check(
    wallets: list[dict[str, str]],
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
    webhook_url: str | None = None,
) -> str:
    """
    Check all watched wallets and report significant changes.

    Returns formatted text suitable for OpenClaw delivery.
    """
    t_start = time.monotonic()
    state = load_state()
    prev_wallets = state.get("wallets", {})

    results = []
    all_changes = []

    for wallet in wallets:
        addr = wallet["address"]
        chain = wallet.get("chain", "ethereum")
        label = wallet.get("label", f"{addr[:8]}...")
        state_key = f"{chain}:{addr}"

        log.info("Checking %s on %s...", label, chain)
        result = await check_wallet(addr, chain, prev_wallets.get(state_key), threshold_pct)
        result["label"] = label
        results.append(result)

        if result["error"]:
            log.warning("Failed to check %s: %s", label, result["error"])
        else:
            # Update state
            prev_wallets[state_key] = {
                "holdings": result["holdings"],
                "total_usd": result["total_usd"],
                "timestamp": result["timestamp"],
            }
            for change in result["changes"]:
                change["wallet_label"] = label
                change["address"] = addr
                change["chain"] = chain
                all_changes.append(change)

    # Save updated state
    state["wallets"] = prev_wallets
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    elapsed = time.monotonic() - t_start
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Format output
    if not all_changes:
        output = (
            f"**NansenScope Portfolio** — {now_str}\n"
            f"Checked {len(wallets)} wallet(s) in {elapsed:.1f}s — no significant changes "
            f"(threshold: {threshold_pct}%).\n"
            f"API calls: {api_tracker.total_calls}"
        )
        # Check for errors
        errors = [r for r in results if r.get("error")]
        if errors:
            output += f"\nErrors: {len(errors)} wallet(s) failed to fetch."
    else:
        lines = [
            f"**NansenScope Portfolio** — {now_str}",
            f"{len(all_changes)} significant change(s) across {len(wallets)} wallet(s) ({elapsed:.1f}s):",
            "",
        ]
        for i, change in enumerate(all_changes, 1):
            label = change.get("wallet_label", "?")
            token = change["token"]
            ctype = change["type"]

            if ctype == "new_position":
                lines.append(f"{i}. **NEW** {label} — opened {token} position (${change['curr_usd']:,.0f})")
            elif ctype == "exited_position":
                lines.append(f"{i}. **EXIT** {label} — closed {token} position (was ${change['prev_usd']:,.0f})")
            elif ctype == "portfolio_total":
                direction = "UP" if change["change_pct"] > 0 else "DOWN"
                lines.append(
                    f"{i}. **{direction}** {label} — total portfolio {change['change_pct']:+.1f}% "
                    f"(${change['prev_usd']:,.0f} → ${change['curr_usd']:,.0f})"
                )
            else:
                direction = "UP" if change["change_pct"] > 0 else "DOWN"
                lines.append(
                    f"{i}. **{direction}** {label} — {token} {change['change_pct']:+.1f}% "
                    f"(${change['prev_usd']:,.0f} → ${change['curr_usd']:,.0f})"
                )

        lines.extend(["", f"API calls: {api_tracker.total_calls}"])
        output = "\n".join(lines)

    # Webhook
    if webhook_url and all_changes:
        _send_webhook(webhook_url, {
            "event": "nansenscope.portfolio",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "changes": all_changes,
            "wallets_checked": len(wallets),
        })

    return output


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="portfolio_check",
        description="NansenScope Portfolio Monitor — track wallet holdings",
    )
    parser.add_argument(
        "--wallets", type=str, default=None,
        help="Comma-separated wallet addresses (overrides config file)",
    )
    parser.add_argument(
        "--chain", type=str, default="ethereum",
        help="Chain for --wallets addresses (default: ethereum)",
    )
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD_PCT,
        help=f"Min % change to report (default: {DEFAULT_THRESHOLD_PCT})",
    )
    parser.add_argument(
        "--webhook", type=str, default=None,
        help="Webhook URL to POST changes to",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Clear state file (next run will have no comparison baseline)",
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

    # Build wallet list
    if args.wallets:
        addresses = [a.strip() for a in args.wallets.split(",") if a.strip()]
        wallets = [{"address": a, "chain": args.chain, "label": f"{a[:8]}..."} for a in addresses]
    else:
        wallets = load_watched_wallets()
        if not wallets:
            print("No wallets configured. Use --wallets or create config/watched_wallets.json")
            sys.exit(1)

    try:
        output = asyncio.run(run_portfolio_check(wallets, args.threshold, args.webhook))
        print(output)
    except KeyboardInterrupt:
        log.warning("Interrupted")
        sys.exit(130)
    except Exception as e:
        log.error("Portfolio check failed: %s", e, exc_info=True)
        print(f"NansenScope Portfolio — FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
