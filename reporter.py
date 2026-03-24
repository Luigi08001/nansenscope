"""
NansenScope — Markdown Report Generator

Generates structured, readable markdown reports from scan results and signals.
Reports are designed to be both human-readable and LLM-parseable.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from typing import Any

from config import DEFAULT_OUTPUT, OutputSettings, Severity, api_tracker
from signals import Signal

log = logging.getLogger("nansenscope.reporter")


# ── Severity Display ─────────────────────────────────────────────────────────

SEVERITY_ICONS = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟠",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "⚪",
}

SEVERITY_LABELS = {
    Severity.CRITICAL: "CRITICAL",
    Severity.HIGH: "HIGH",
    Severity.MEDIUM: "MEDIUM",
    Severity.LOW: "LOW",
}


# ── Report Builder ───────────────────────────────────────────────────────────

class ReportBuilder:
    """Builds a markdown report incrementally."""

    def __init__(self):
        self.sections: list[str] = []

    def add(self, text: str) -> "ReportBuilder":
        self.sections.append(text)
        return self

    def add_line(self, text: str = "") -> "ReportBuilder":
        self.sections.append(text + "\n")
        return self

    def add_heading(self, text: str, level: int = 1) -> "ReportBuilder":
        self.sections.append(f"{'#' * level} {text}\n")
        return self

    def add_divider(self) -> "ReportBuilder":
        self.sections.append("---\n")
        return self

    def build(self) -> str:
        return "\n".join(self.sections)


# ── Report Generators ────────────────────────────────────────────────────────

def generate_scan_report(
    all_signals: dict[str, list[Signal]],
    scan_results: dict | None = None,
    chains: list[str] | None = None,
    settings: OutputSettings = DEFAULT_OUTPUT,
    chart_paths: dict[str, str] | None = None,
    alerts: list[Any] | None = None,
) -> str:
    """
    Generate a full smart money intelligence report.

    Structure:
    1. Header with timestamp and metadata
    2. Executive summary with market snapshot
    3. Triggered alerts
    4. Per-chain breakdown
    5. Charts
    6. API cost tracking
    """
    now = datetime.now(timezone.utc).strftime(settings.date_format)
    report = ReportBuilder()

    # ── Header ──
    report.add_heading("NansenScope — Smart Money Intelligence Report")
    report.add_line(f"**Generated:** {now}")
    if chains:
        report.add_line(f"**Chains scanned:** {', '.join(chains)}")

    total_signals = sum(len(sigs) for sigs in all_signals.values())
    convergence_count = sum(
        1 for sigs in all_signals.values() for s in sigs if s.type == "convergence"
    )
    critical_count = sum(
        1 for sigs in all_signals.values() for s in sigs if s.severity == Severity.CRITICAL
    )
    high_count = sum(
        1 for sigs in all_signals.values() for s in sigs if s.severity == Severity.HIGH
    )

    report.add_line(f"**Total signals:** {total_signals} | **Convergence:** {convergence_count} | **Critical:** {critical_count} | **High:** {high_count}")
    report.add_divider()

    # ── Executive Summary ──
    report.add_heading("Executive Summary", 2)

    # Market snapshot
    all_flat = []
    for sigs in all_signals.values():
        all_flat.extend(sigs)
    all_flat.sort(key=lambda s: s.score, reverse=True)

    # Summarize direction
    bullish_tokens = set()
    bearish_tokens = set()
    for s in all_flat:
        if s.type in ("accumulation", "high_conviction") or (s.type in ("large_netflow", "notable_netflow") and s.details.get("direction") == "inflow"):
            bullish_tokens.add(s.token)
        elif s.type == "distribution" or (s.type in ("large_netflow", "notable_netflow") and s.details.get("direction") == "outflow"):
            bearish_tokens.add(s.token)

    if bullish_tokens or bearish_tokens:
        report.add_line("**Market Snapshot:**")
        if bullish_tokens:
            report.add_line(f"- Bullish signals on: {', '.join(sorted(bullish_tokens)[:10])}")
        if bearish_tokens:
            report.add_line(f"- Bearish signals on: {', '.join(sorted(bearish_tokens)[:10])}")
        report.add_line()

    # Top signals
    top = [s for s in all_flat if s.type == "convergence"][:5]
    if not top:
        top = all_flat[:5]

    if top:
        report.add_line("**Top Alerts:**\n")
        for i, sig in enumerate(top, 1):
            icon = SEVERITY_ICONS.get(sig.severity, "")
            report.add_line(f"{i}. {icon} **[{sig.chain.upper()}]** {sig.summary} _(score: {sig.score:.0f})_")
        report.add_line()
    else:
        report.add_line("_No significant signals detected in this scan._\n")

    # ── Triggered Alerts ──
    if alerts:
        report.add_heading("Triggered Alerts", 2)
        for alert in alerts:
            sev = alert.severity.value.upper() if hasattr(alert, "severity") else "INFO"
            summary = alert.summary if hasattr(alert, "summary") else str(alert)
            icon = SEVERITY_ICONS.get(alert.severity, "") if hasattr(alert, "severity") else ""
            report.add_line(f"- {icon} **[{sev}]** {summary}")
        report.add_line()

    # ── Critical / High Severity Breakdown ──
    critical_high = [s for s in all_flat if s.severity in (Severity.CRITICAL, Severity.HIGH)]
    if critical_high:
        report.add_heading("High-Priority Signals", 2)
        report.add_line("| Chain | Token | Signal | Severity | Score |")
        report.add_line("|-------|-------|--------|----------|-------|")
        for sig in critical_high[:settings.max_signals_per_chain]:
            icon = SEVERITY_ICONS.get(sig.severity, "")
            report.add_line(
                f"| {sig.chain} | {sig.token} | {sig.type} | {icon} {SEVERITY_LABELS[sig.severity]} | {sig.score:.0f} |"
            )
        report.add_line()

    # ── Per-Chain Sections ──
    for chain, sigs in all_signals.items():
        if not sigs:
            continue

        report.add_heading(f"{chain.upper()}", 2)

        # Group by signal type
        by_type: dict[str, list[Signal]] = {}
        for s in sigs:
            by_type.setdefault(s.type, []).append(s)

        for sig_type, type_sigs in by_type.items():
            report.add_heading(_format_signal_type(sig_type), 3)
            for sig in type_sigs[:settings.max_signals_per_chain]:
                icon = SEVERITY_ICONS.get(sig.severity, "")
                report.add_line(f"- {icon} {sig.summary}")

                # Add key details
                if sig.details:
                    detail_items = _format_details(sig.details)
                    if detail_items:
                        report.add_line(f"  - {detail_items}")

            report.add_line()

    # ── Charts ──
    if chart_paths:
        report.add_heading("Visualizations", 2)
        chart_labels = {
            "flow_heatmap": "Net Flow Heatmap (Chain x Token)",
            "signal_timeline": "Signal Timeline by Severity",
            "chain_comparison": "Smart Money Activity by Chain",
            "wallet_treemap": "Holdings Treemap",
        }
        for name, path in chart_paths.items():
            label = chart_labels.get(name, name.replace("_", " ").title())
            report.add_line(f"### {label}")
            report.add_line(f"![{label}]({path})")
            report.add_line()

    # ── API Cost Tracking ──
    report.add_divider()
    report.add_heading("API Usage & Cost Tracking", 2)
    stats = api_tracker.summary
    total_calls = stats['total_calls']
    errors = stats['errors']
    successful = total_calls - errors

    report.add_line(f"- **Total API calls:** {total_calls}")
    report.add_line(f"- **Successful:** {successful}")
    report.add_line(f"- **Errors:** {errors}")
    report.add_line(f"- **Estimated cost:** ~${total_calls * 0.01:.2f} (at ~$0.01/call via x402)")
    if stats["by_endpoint"]:
        report.add_line("- **Calls by endpoint:**")
        for endpoint, count in sorted(stats["by_endpoint"].items()):
            report.add_line(f"  - `{endpoint}`: {count}")

    report.add_divider()
    report.add_line("_Report generated by [NansenScope](https://github.com/Luigi08001/nansenscope) — Autonomous Smart Money Intelligence_")

    return report.build()


def generate_wallet_report(
    address: str,
    chain: str,
    profile_results: dict,
    settings: OutputSettings = DEFAULT_OUTPUT,
) -> str:
    """Generate a wallet deep-dive report."""
    now = datetime.now(timezone.utc).strftime(settings.date_format)
    report = ReportBuilder()

    report.add_heading(f"NansenScope — Wallet Profile")
    report.add_line(f"**Address:** `{address}`")
    report.add_line(f"**Chain:** {chain}")
    report.add_line(f"**Generated:** {now}")
    report.add_divider()

    # PnL Summary
    pnl = profile_results.get("pnl_summary")
    if pnl and hasattr(pnl, "success") and pnl.success and pnl.data:
        report.add_heading("PnL Summary", 2)
        _add_data_section(report, pnl.data)

    # Labels
    labels = profile_results.get("labels")
    if labels and hasattr(labels, "success") and labels.success and labels.data:
        report.add_heading("Wallet Labels", 2)
        _add_data_section(report, labels.data)

    # Balance
    balance = profile_results.get("balance")
    if balance and hasattr(balance, "success") and balance.success and balance.data:
        report.add_heading("Current Holdings", 2)
        if isinstance(balance.data, list):
            report.add_line("| Token | Balance | Value (USD) |")
            report.add_line("|-------|---------|-------------|")
            for item in balance.data[:30]:
                if isinstance(item, dict):
                    token = item.get("token_symbol") or item.get("symbol", "???")
                    bal = item.get("balance") or item.get("amount", "—")
                    val = item.get("value_usd") or item.get("balance_usd", "—")
                    report.add_line(f"| {token} | {bal} | {val} |")
            report.add_line()
        else:
            _add_data_section(report, balance.data)

    # Counterparties
    cps = profile_results.get("counterparties")
    if cps and hasattr(cps, "success") and cps.success and cps.data:
        report.add_heading("Top Counterparties", 2)
        if isinstance(cps.data, list):
            for item in cps.data[:10]:
                if isinstance(item, dict):
                    addr = item.get("address") or item.get("counterparty", "???")
                    vol = item.get("volume_usd") or item.get("value", "—")
                    label = item.get("label") or item.get("entity", "")
                    report.add_line(f"- `{addr[:10]}...{addr[-6:]}` — ${vol}" + (f" ({label})" if label else ""))
            report.add_line()
        else:
            _add_data_section(report, cps.data)

    # Errors
    errors = []
    for key, result in profile_results.items():
        if hasattr(result, "success") and not result.success and result.error:
            errors.append(f"- **{key}:** {result.error}")
    if errors:
        report.add_heading("Errors", 2)
        for e in errors:
            report.add_line(e)

    report.add_divider()
    report.add_line("_Report generated by [NansenScope](https://github.com/Luigi08001/nansenscope) — Autonomous Smart Money Intelligence_")

    return report.build()


def generate_signals_report(
    ranked_signals: list[Signal],
    settings: OutputSettings = DEFAULT_OUTPUT,
) -> str:
    """Generate a focused signals-only report."""
    now = datetime.now(timezone.utc).strftime(settings.date_format)
    report = ReportBuilder()

    report.add_heading("NansenScope — Signal Board")
    report.add_line(f"**Generated:** {now}")
    report.add_line(f"**Total signals:** {len(ranked_signals)}")
    report.add_divider()

    if not ranked_signals:
        report.add_line("_No signals detected. Run a scan first._")
        return report.build()

    # Group by severity
    for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
        sigs = [s for s in ranked_signals if s.severity == severity]
        if not sigs:
            continue

        icon = SEVERITY_ICONS[severity]
        report.add_heading(f"{icon} {SEVERITY_LABELS[severity]} ({len(sigs)})", 2)

        for sig in sigs:
            report.add_line(f"- **[{sig.chain.upper()}] {sig.token}** — {sig.summary} _(score: {sig.score:.0f})_")

        report.add_line()

    report.add_divider()
    report.add_line("_Report generated by [NansenScope](https://github.com/Luigi08001/nansenscope) — Autonomous Smart Money Intelligence_")

    return report.build()


# ── File Output ──────────────────────────────────────────────────────────────

def save_report(content: str, filepath: str | Path) -> Path:
    """Save a report to disk, creating directories as needed."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    log.info("Report saved to %s", path)
    return path


# ── Helpers ──────────────────────────────────────────────────────────────────

def _format_signal_type(signal_type: str) -> str:
    """Convert signal type slug to readable heading."""
    return signal_type.replace("_", " ").title()


def _format_details(details: dict) -> str:
    """Format signal details into a compact inline string."""
    parts = []
    skip_keys = {"component_signals", "direction", "sentiment", "side", "wallet", "label"}

    for k, v in details.items():
        if k in skip_keys:
            continue
        if isinstance(v, (list, set)):
            continue
        if isinstance(v, float):
            if abs(v) >= 1_000_000:
                parts.append(f"{_humanize_key(k)}: ${v:,.0f}")
            elif abs(v) >= 1:
                parts.append(f"{_humanize_key(k)}: {v:,.2f}")
            else:
                parts.append(f"{_humanize_key(k)}: {v:.4f}")
        elif isinstance(v, int):
            parts.append(f"{_humanize_key(k)}: {v:,}")
        elif v:
            parts.append(f"{_humanize_key(k)}: {v}")

    return " | ".join(parts[:6])


def _humanize_key(key: str) -> str:
    """Convert snake_case key to readable label."""
    return key.replace("_", " ").replace("usd", "USD").replace("pct", "%").title()


def _add_data_section(report: ReportBuilder, data) -> None:
    """Add arbitrary data (dict or list) to report."""
    if isinstance(data, dict):
        for k, v in data.items():
            report.add_line(f"- **{_humanize_key(k)}:** {v}")
    elif isinstance(data, list):
        for item in data[:20]:
            if isinstance(item, dict):
                parts = [f"{_humanize_key(k)}: {v}" for k, v in list(item.items())[:5]]
                report.add_line(f"- {' | '.join(parts)}")
            else:
                report.add_line(f"- {item}")
    else:
        report.add_line(f"```\n{data}\n```")
    report.add_line()
