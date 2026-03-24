"""
NansenScope — Smart Money Alert Engine

Wraps signal detection into a rule-based alerting system with cooldowns,
deduplication, and persistent history tracking via JSON.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from config import DEFAULT_CHAINS, DEFAULT_THRESHOLDS, Severity, api_tracker
from scanner import scan_all_chains
from signals import Signal, analyze_all_chains, rank_signals

log = logging.getLogger("nansenscope.alerts")

ALERT_HISTORY_PATH = Path("reports") / "alert_history.json"


# ── Alert Data Models ───────────────────────────────────────────────────────

@dataclass
class AlertRule:
    """A single alert rule definition."""

    name: str
    condition_fn: Callable[[list[Signal]], list[Signal]]
    severity: Severity
    cooldown_minutes: int = 30
    description: str = ""


@dataclass
class Alert:
    """A triggered alert instance."""

    rule_name: str
    severity: Severity
    signals: list[Signal]
    summary: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON storage."""
        return {
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "summary": self.summary,
            "timestamp": self.timestamp,
            "signal_count": len(self.signals),
            "tokens": list({s.token for s in self.signals}),
            "chains": list({s.chain for s in self.signals}),
        }


# ── Built-in Rule Conditions ────────────────────────────────────────────────

def _whale_accumulation(signals: list[Signal]) -> list[Signal]:
    """SM buying same token across 2+ chains."""
    token_chains: dict[str, set[str]] = {}
    accum_signals: list[Signal] = []

    for s in signals:
        if s.type in ("accumulation", "large_netflow") and _is_buy_signal(s):
            token_chains.setdefault(s.token, set()).add(s.chain)
            accum_signals.append(s)

    multi_chain_tokens = {t for t, chains in token_chains.items() if len(chains) >= 2}
    return [s for s in accum_signals if s.token in multi_chain_tokens]


def _smart_money_divergence(signals: list[Signal]) -> list[Signal]:
    """SM buying while price drops >5%."""
    result = []
    for s in signals:
        if s.type in ("accumulation", "whale_trade") and _is_buy_signal(s):
            price_change = s.details.get("price_change_pct", 0)
            if isinstance(price_change, (int, float)) and price_change < -5:
                result.append(s)
    return result


def _cross_chain_flow(signals: list[Signal]) -> list[Signal]:
    """Same token flowing into multiple chains."""
    token_chains: dict[str, set[str]] = {}
    flow_signals: list[Signal] = []

    for s in signals:
        if s.type in ("large_netflow", "notable_netflow"):
            if s.details.get("direction") == "inflow":
                token_chains.setdefault(s.token, set()).add(s.chain)
                flow_signals.append(s)

    multi = {t for t, chains in token_chains.items() if len(chains) >= 2}
    return [s for s in flow_signals if s.token in multi]


def _new_token_attention(signals: list[Signal]) -> list[Signal]:
    """Token appears in SM holdings for first time (screener trending)."""
    return [
        s for s in signals
        if s.type == "screener_trending"
        and s.details.get("smart_money_holders", 0) >= 3
        and s.details.get("sentiment") == "bullish"
    ]


def _convergence_spike(signals: list[Signal]) -> list[Signal]:
    """Convergence score jumps above 80."""
    return [s for s in signals if s.type == "convergence" and s.score >= 80]


def _is_buy_signal(signal: Signal) -> bool:
    """Check if a signal indicates buying activity."""
    if signal.type == "accumulation":
        return True
    if signal.type in ("large_netflow", "notable_netflow"):
        return signal.details.get("direction") == "inflow"
    if signal.type == "whale_trade":
        return signal.details.get("side") in ("buy", "bought")
    return False


# ── Default Rules ───────────────────────────────────────────────────────────

DEFAULT_RULES: list[AlertRule] = [
    AlertRule(
        name="whale_accumulation",
        condition_fn=_whale_accumulation,
        severity=Severity.CRITICAL,
        cooldown_minutes=60,
        description="Smart money buying same token across 2+ chains",
    ),
    AlertRule(
        name="smart_money_divergence",
        condition_fn=_smart_money_divergence,
        severity=Severity.HIGH,
        cooldown_minutes=30,
        description="Smart money buying while price drops >5%",
    ),
    AlertRule(
        name="cross_chain_flow",
        condition_fn=_cross_chain_flow,
        severity=Severity.HIGH,
        cooldown_minutes=45,
        description="Same token flowing into multiple chains",
    ),
    AlertRule(
        name="new_token_attention",
        condition_fn=_new_token_attention,
        severity=Severity.MEDIUM,
        cooldown_minutes=120,
        description="New token gaining smart money attention",
    ),
    AlertRule(
        name="convergence_spike",
        condition_fn=_convergence_spike,
        severity=Severity.CRITICAL,
        cooldown_minutes=30,
        description="Convergence score above 80",
    ),
]


# ── Alert History ───────────────────────────────────────────────────────────

class AlertHistory:
    """Persistent alert history backed by a JSON file."""

    def __init__(self, path: Path = ALERT_HISTORY_PATH):
        self.path = path
        self._history: list[dict] = []
        self._load()

    def _load(self) -> None:
        """Load history from disk."""
        if self.path.exists():
            try:
                self._history = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Failed to load alert history: %s", e)
                self._history = []

    def save(self) -> None:
        """Persist history to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._history, indent=2, default=str),
            encoding="utf-8",
        )

    def record(self, alert: Alert) -> None:
        """Add an alert to history."""
        self._history.append(alert.to_dict())
        self.save()

    def is_in_cooldown(self, rule_name: str, tokens: set[str], cooldown_minutes: int) -> bool:
        """Check if a rule+token combo is still in cooldown."""
        cutoff = time.time() - (cooldown_minutes * 60)
        for entry in reversed(self._history):
            if entry.get("timestamp", 0) < cutoff:
                break
            if entry.get("rule_name") == rule_name:
                past_tokens = set(entry.get("tokens", []))
                if past_tokens & tokens:
                    return True
        return False

    @property
    def recent(self) -> list[dict]:
        """Get last 50 alerts."""
        return self._history[-50:]


# ── Alert Engine ────────────────────────────────────────────────────────────

class AlertEngine:
    """Runs alert rules against detected signals."""

    def __init__(
        self,
        rules: list[AlertRule] | None = None,
        history_path: Path = ALERT_HISTORY_PATH,
    ):
        self.rules = rules or DEFAULT_RULES
        self.history = AlertHistory(history_path)

    async def run(
        self,
        chains: list[str] | None = None,
        scan_results: dict | None = None,
        all_signals: dict[str, list[Signal]] | None = None,
    ) -> list[Alert]:
        """
        Full alert pipeline: scan -> signals -> check rules -> emit alerts.

        Accepts pre-computed scan_results/all_signals to avoid redundant scans.
        """
        chains = chains or DEFAULT_CHAINS

        # Step 1: Scan if needed
        if scan_results is None:
            log.info("Running scan across %d chains...", len(chains))
            scan_results = await scan_all_chains(chains)

        # Step 2: Detect signals if needed
        if all_signals is None:
            all_signals = analyze_all_chains(scan_results)

        # Flatten all signals
        flat_signals = [s for sigs in all_signals.values() for s in sigs]
        log.info("Checking %d rules against %d signals", len(self.rules), len(flat_signals))

        # Step 3: Check each rule
        triggered: list[Alert] = []
        for rule in self.rules:
            matching = rule.condition_fn(flat_signals)
            if not matching:
                continue

            tokens = {s.token for s in matching}

            # Cooldown check
            if self.history.is_in_cooldown(rule.name, tokens, rule.cooldown_minutes):
                log.debug("Rule %s in cooldown for tokens %s, skipping", rule.name, tokens)
                continue

            # Build alert
            token_list = ", ".join(sorted(tokens)[:5])
            chain_list = ", ".join(sorted({s.chain for s in matching}))
            summary = (
                f"[{rule.name.upper()}] {len(matching)} signals on {token_list} "
                f"({chain_list})"
            )

            alert = Alert(
                rule_name=rule.name,
                severity=rule.severity,
                signals=matching,
                summary=summary,
            )

            triggered.append(alert)
            self.history.record(alert)
            log.info("ALERT: %s", summary)

        log.info("Triggered %d alerts", len(triggered))
        return triggered

    def get_recent_alerts(self) -> list[dict]:
        """Get recent alert history."""
        return self.history.recent
