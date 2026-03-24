"""
NansenScope — Nansen CLI Scanner

Wraps the Nansen CLI binary via subprocess. Every API call goes through
`_run_nansen()` which handles JSON parsing, error recovery, rate-limit
retries, and call tracking.

All public functions are async-friendly via asyncio.create_subprocess_exec.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from config import api_tracker

log = logging.getLogger("nansenscope.scanner")

# ── Constants ────────────────────────────────────────────────────────────────

NANSEN_BIN = "nansen"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0          # seconds, exponential backoff
COMMAND_TIMEOUT = 60             # seconds per CLI call


# ── Result Container ─────────────────────────────────────────────────────────

@dataclass
class ScanResult:
    """Wraps the result of a Nansen CLI call."""

    success: bool
    data: Any = None
    error: str | None = None
    endpoint: str = ""
    chain: str = ""
    elapsed_ms: int = 0
    raw: str = ""

    @property
    def is_empty(self) -> bool:
        if self.data is None:
            return True
        if isinstance(self.data, list):
            return len(self.data) == 0
        if isinstance(self.data, dict):
            return len(self.data) == 0
        return False


# ── Core CLI Runner ──────────────────────────────────────────────────────────

async def _run_nansen(args: list[str], endpoint: str) -> ScanResult:
    """
    Execute a Nansen CLI command and return a parsed ScanResult.

    Handles:
    - JSON parsing of stdout
    - Rate limit detection (HTTP 429) with exponential backoff
    - Payment required (402) with graceful messaging
    - Timeout protection
    - API call tracking
    """
    full_cmd = [NANSEN_BIN] + args
    cmd_str = " ".join(full_cmd)
    chain = _extract_chain(args)

    for attempt in range(1, MAX_RETRIES + 1):
        t0 = time.monotonic()
        api_tracker.record(endpoint)

        try:
            log.debug("Running [attempt %d]: %s", attempt, cmd_str)

            proc = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=COMMAND_TIMEOUT
            )

            elapsed = int((time.monotonic() - t0) * 1000)
            raw_out = stdout.decode("utf-8", errors="replace").strip()
            raw_err = stderr.decode("utf-8", errors="replace").strip()

            # Try parsing JSON from stdout
            if raw_out:
                try:
                    parsed = json.loads(raw_out)
                except json.JSONDecodeError:
                    # Some commands output non-JSON (tables, etc.)
                    return ScanResult(
                        success=True,
                        data=raw_out,
                        endpoint=endpoint,
                        chain=chain,
                        elapsed_ms=elapsed,
                        raw=raw_out,
                    )

                # Check for API-level errors in the JSON
                if isinstance(parsed, dict) and not parsed.get("success", True):
                    error_code = parsed.get("code", "")
                    error_msg = parsed.get("error", "Unknown API error")

                    # Rate limited — retry with backoff
                    if error_code == "RATE_LIMITED" or parsed.get("status") == 429:
                        retry_after = _get_retry_delay(parsed, attempt)
                        log.warning(
                            "Rate limited on %s (attempt %d), waiting %.1fs",
                            endpoint, attempt, retry_after,
                        )
                        api_tracker.record_error()
                        await asyncio.sleep(retry_after)
                        continue

                    # Payment required — no auth configured
                    if error_code == "PAYMENT_REQUIRED" or parsed.get("status") == 402:
                        log.warning("Payment required for %s — no API key or x402 wallet", endpoint)
                        return ScanResult(
                            success=False,
                            error=f"Auth required: {error_msg}",
                            endpoint=endpoint,
                            chain=chain,
                            elapsed_ms=elapsed,
                            raw=raw_out,
                        )

                    # Unauthorized
                    if error_code == "UNAUTHORIZED" or parsed.get("status") == 401:
                        log.warning("Unauthorized for %s", endpoint)
                        return ScanResult(
                            success=False,
                            error=f"Unauthorized: {error_msg}",
                            endpoint=endpoint,
                            chain=chain,
                            elapsed_ms=elapsed,
                            raw=raw_out,
                        )

                    # Other API error — don't retry
                    api_tracker.record_error()
                    return ScanResult(
                        success=False,
                        error=error_msg,
                        endpoint=endpoint,
                        chain=chain,
                        elapsed_ms=elapsed,
                        raw=raw_out,
                    )

                # Success — extract data payload
                data = parsed.get("data", parsed) if isinstance(parsed, dict) else parsed
                return ScanResult(
                    success=True,
                    data=data,
                    endpoint=endpoint,
                    chain=chain,
                    elapsed_ms=elapsed,
                    raw=raw_out,
                )

            # No stdout — check stderr
            if raw_err:
                api_tracker.record_error()
                return ScanResult(
                    success=False,
                    error=raw_err,
                    endpoint=endpoint,
                    chain=chain,
                    elapsed_ms=elapsed,
                    raw=raw_err,
                )

            # Empty response
            return ScanResult(
                success=True,
                data=None,
                endpoint=endpoint,
                chain=chain,
                elapsed_ms=elapsed,
            )

        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - t0) * 1000)
            log.error("Timeout after %ds on %s (attempt %d)", COMMAND_TIMEOUT, endpoint, attempt)
            api_tracker.record_error()
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BASE_DELAY * attempt)
                continue
            return ScanResult(
                success=False,
                error=f"Timeout after {COMMAND_TIMEOUT}s",
                endpoint=endpoint,
                chain=chain,
                elapsed_ms=elapsed,
            )

        except Exception as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            log.error("Unexpected error on %s: %s", endpoint, e)
            api_tracker.record_error()
            return ScanResult(
                success=False,
                error=str(e),
                endpoint=endpoint,
                chain=chain,
                elapsed_ms=elapsed,
            )

    # Exhausted retries
    return ScanResult(
        success=False,
        error=f"Failed after {MAX_RETRIES} retries",
        endpoint=endpoint,
        chain=chain,
    )


def _extract_chain(args: list[str]) -> str:
    """Pull the --chain value from args list."""
    for i, arg in enumerate(args):
        if arg == "--chain" and i + 1 < len(args):
            return args[i + 1]
    return ""


def _get_retry_delay(response: dict, attempt: int) -> float:
    """Calculate retry delay from response or exponential backoff."""
    details = response.get("details", {})
    retry_ms = details.get("retryAfterMs")
    if retry_ms and isinstance(retry_ms, (int, float)):
        return retry_ms / 1000.0
    return RETRY_BASE_DELAY ** attempt


# ── Smart Money Endpoints ────────────────────────────────────────────────────

async def get_smart_money_netflows(chain: str) -> ScanResult:
    """
    Get net capital flows — inflows vs outflows by token.
    Shows where smart money capital is moving.
    """
    return await _run_nansen(
        ["research", "smart-money", "netflow", "--chain", chain],
        endpoint="smart-money/netflow",
    )


async def get_smart_money_dex_trades(chain: str) -> ScanResult:
    """
    Get real-time DEX trading activity from smart money wallets.
    Shows what tokens smart money is actively buying/selling.
    """
    return await _run_nansen(
        ["research", "smart-money", "dex-trades", "--chain", chain],
        endpoint="smart-money/dex-trades",
    )


async def get_smart_money_holdings(chain: str) -> ScanResult:
    """
    Get aggregated token holdings across smart money wallets.
    Shows what positions smart money currently holds.
    """
    return await _run_nansen(
        ["research", "smart-money", "holdings", "--chain", chain],
        endpoint="smart-money/holdings",
    )


async def get_token_screener(chain: str, timeframe: str = "24h") -> ScanResult:
    """
    Discover and filter tokens by smart money activity.
    The screener surfaces tokens gaining smart money attention.
    """
    return await _run_nansen(
        ["research", "token", "screener", "--chain", chain, "--timeframe", timeframe],
        endpoint="token/screener",
    )


# ── Wallet Profiler Endpoints ────────────────────────────────────────────────

async def get_wallet_profile(address: str, chain: str = "ethereum", days: int = 30) -> ScanResult:
    """
    Get summarized PnL metrics for a wallet.
    Shows trading performance, win rate, average returns.
    """
    return await _run_nansen(
        [
            "research", "profiler", "pnl-summary",
            "--address", address,
            "--chain", chain,
            "--days", str(days),
        ],
        endpoint="profiler/pnl-summary",
    )


async def get_wallet_counterparties(address: str, chain: str = "ethereum", days: int = 30) -> ScanResult:
    """
    Get top counterparties by volume for a wallet.
    Reveals who a wallet trades with most, useful for cluster detection.
    """
    return await _run_nansen(
        [
            "research", "profiler", "counterparties",
            "--address", address,
            "--chain", chain,
            "--days", str(days),
        ],
        endpoint="profiler/counterparties",
    )


# ── Extended Endpoints (bonus coverage) ──────────────────────────────────────

async def get_smart_money_dcas(chain: str) -> ScanResult:
    """Get DCA (Dollar Cost Averaging) activity from smart money."""
    return await _run_nansen(
        ["research", "smart-money", "dcas", "--chain", chain],
        endpoint="smart-money/dcas",
    )


async def get_wallet_labels(address: str, chain: str = "ethereum") -> ScanResult:
    """Get Nansen labels for a wallet address."""
    return await _run_nansen(
        ["research", "profiler", "labels", "--address", address, "--chain", chain],
        endpoint="profiler/labels",
    )


async def get_wallet_balance(address: str, chain: str = "ethereum") -> ScanResult:
    """Get current token balances for a wallet."""
    return await _run_nansen(
        ["research", "profiler", "balance", "--address", address, "--chain", chain],
        endpoint="profiler/balance",
    )


async def get_token_flows(token: str, chain: str = "ethereum") -> ScanResult:
    """Get flow data for a specific token (requires token address)."""
    return await _run_nansen(
        ["research", "token", "flows", "--token", token, "--chain", chain],
        endpoint="token/flows",
    )


# ── Multi-Chain Scanner ──────────────────────────────────────────────────────

async def scan_chain(chain: str) -> dict[str, ScanResult]:
    """
    Run all core smart money scans for a single chain in parallel.
    Returns a dict of endpoint_name -> ScanResult.
    """
    tasks = {
        "netflows": get_smart_money_netflows(chain),
        "dex_trades": get_smart_money_dex_trades(chain),
        "holdings": get_smart_money_holdings(chain),
        "token_screener": get_token_screener(chain),
    }

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    out = {}
    for key, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            log.error("Exception scanning %s/%s: %s", chain, key, result)
            api_tracker.record_error()
            out[key] = ScanResult(
                success=False,
                error=str(result),
                endpoint=key,
                chain=chain,
            )
        else:
            out[key] = result

    return out


async def scan_all_chains(chains: list[str]) -> dict[str, dict[str, ScanResult]]:
    """
    Run full scans across multiple chains. Chains are scanned sequentially
    to respect rate limits, but endpoints within a chain run in parallel.
    """
    all_results = {}
    for chain in chains:
        log.info("Scanning %s...", chain)
        all_results[chain] = await scan_chain(chain)
    return all_results


async def profile_wallet(
    address: str, chain: str = "ethereum", days: int = 30
) -> dict[str, ScanResult]:
    """
    Run a full wallet deep-dive: PnL, counterparties, labels, balance.
    All endpoints run in parallel.
    """
    tasks = {
        "pnl_summary": get_wallet_profile(address, chain, days),
        "counterparties": get_wallet_counterparties(address, chain, days),
        "labels": get_wallet_labels(address, chain),
        "balance": get_wallet_balance(address, chain),
    }

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    out = {}
    for key, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            log.error("Exception profiling %s/%s: %s", address, key, result)
            api_tracker.record_error()
            out[key] = ScanResult(
                success=False,
                error=str(result),
                endpoint=key,
                chain=chain,
            )
        else:
            out[key] = result

    return out
