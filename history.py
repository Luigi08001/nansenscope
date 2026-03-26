"""
NansenScope — Signal History & Trend Detection

Tracks signals over time and identifies trending tokens.
State stored in reports/signal_history.json
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from rich.table import Table

from signals import Signal

log = logging.getLogger("nansenscope.history")

HISTORY_PATH = Path("reports") / "signal_history.json"
MAX_ENTRIES = 10_000


# ── Record & Load ────────────────────────────────────────────────────────────

def record_signals(signals: list[Signal], path: Path = HISTORY_PATH) -> int:
    """Append signals to history file with timestamp. Returns count recorded."""
    if not signals:
        return 0

    now = datetime.now(timezone.utc).isoformat()
    history = _load_raw(path)

    for sig in signals:
        history.append({
            "timestamp": now,
            "chain": sig.chain,
            "token": sig.token,
            "severity": sig.severity.value,
            "signal_type": sig.type,
            "score": round(sig.score, 1),
            "summary": sig.summary,
        })

    # Cap at MAX_ENTRIES (trim oldest)
    if len(history) > MAX_ENTRIES:
        history = history[-MAX_ENTRIES:]

    _save(history, path)
    log.info("Recorded %d signals to history (%d total)", len(signals), len(history))
    return len(signals)


def load_history(days: int = 7, path: Path = HISTORY_PATH) -> list[dict]:
    """Load signal history, filter by recency (last N days)."""
    history = _load_raw(path)
    if not history:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    filtered = []
    for entry in history:
        try:
            ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            if ts >= cutoff:
                filtered.append(entry)
        except (KeyError, ValueError, TypeError):
            continue

    return filtered


# ── Trend Detection ──────────────────────────────────────────────────────────

def detect_trends(history: list[dict], min_appearances: int = 3) -> list[dict]:
    """
    Find tokens appearing repeatedly in signal history.

    Groups by token, counts appearances, calculates stats.
    Returns tokens with >= min_appearances, sorted by count descending.
    """
    if not history:
        return []

    token_data: dict[str, list[dict]] = defaultdict(list)
    for entry in history:
        token = entry.get("token", "???")
        token_data[token].append(entry)

    trends = []
    for token, entries in token_data.items():
        count = len(entries)
        if count < min_appearances:
            continue

        scores = [e.get("score", 0) for e in entries]
        chains = sorted({e.get("chain", "?") for e in entries})

        # Parse timestamps for first/last seen
        timestamps = []
        for e in entries:
            try:
                ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
                timestamps.append(ts)
            except (KeyError, ValueError, TypeError):
                continue

        first_seen = min(timestamps) if timestamps else None
        last_seen = max(timestamps) if timestamps else None

        # Trend direction: compare score in recent half vs older half
        mid = len(entries) // 2
        if mid > 0:
            older_avg = sum(e.get("score", 0) for e in entries[:mid]) / mid
            recent_avg = sum(e.get("score", 0) for e in entries[mid:]) / (len(entries) - mid)
            if recent_avg > older_avg + 5:
                trend = "up"
            elif recent_avg < older_avg - 5:
                trend = "down"
            else:
                trend = "stable"
        else:
            trend = "stable"

        trends.append({
            "token": token,
            "chains": chains,
            "appearances": count,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "trend": trend,
        })

    trends.sort(key=lambda t: t["appearances"], reverse=True)
    return trends


# ── Display ──────────────────────────────────────────────────────────────────

def format_trend_table(trends: list[dict]) -> Table:
    """Build a Rich table of trending tokens."""
    trend_icons = {"up": "[green]\u2191[/green]", "down": "[red]\u2193[/red]", "stable": "[dim]\u2192[/dim]"}

    table = Table(
        title="Trending Tokens",
        title_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Token", style="bold", width=12)
    table.add_column("Chain(s)", style="cyan", width=18)
    table.add_column("Appearances", justify="right", width=12)
    table.add_column("First Seen", width=12)
    table.add_column("Last Seen", width=12)
    table.add_column("Avg Score", justify="right", width=10)
    table.add_column("Trend", justify="center", width=6)

    for t in trends:
        first = t["first_seen"].strftime("%Y-%m-%d") if t["first_seen"] else "—"
        last = t["last_seen"].strftime("%Y-%m-%d") if t["last_seen"] else "—"

        table.add_row(
            t["token"][:12],
            ", ".join(t["chains"]),
            str(t["appearances"]),
            first,
            last,
            f"{t['avg_score']:.1f}",
            trend_icons.get(t["trend"], "—"),
        )

    return table


# ── Internal Helpers ─────────────────────────────────────────────────────────

def _load_raw(path: Path = HISTORY_PATH) -> list[dict]:
    """Load raw history JSON. Returns empty list on missing/corrupt file."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        log.warning("History file is not a list, resetting")
        return []
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load signal history: %s", e)
        return []


def _save(history: list[dict], path: Path = HISTORY_PATH) -> None:
    """Persist history to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(history, indent=2, default=str),
        encoding="utf-8",
    )
