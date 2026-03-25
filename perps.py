"""
NansenScope — Perpetual Trading Intelligence

Tracks Smart Money perp positions on Hyperliquid.
Cross-references with spot activity to detect hedges and leveraged bets.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from config import Severity
from signals import Signal

log = logging.getLogger("nansenscope.perps")


@dataclass
class PerpPosition:
    """A perpetual trading position."""

    trader: str
    trader_label: str
    token: str
    side: str           # "Long" or "Short"
    action: str         # "Open" or "Close"
    amount: float
    price_usd: float
    value_usd: float
    order_type: str     # "Market" or "Limit"
    timestamp: str
    tx_hash: str = ""


@dataclass
class PerpSummary:
    """Aggregated perp trading summary."""

    total_positions: int = 0
    total_volume_usd: float = 0.0
    long_volume_usd: float = 0.0
    short_volume_usd: float = 0.0
    unique_traders: int = 0
    top_tokens: list[dict] = field(default_factory=list)
    positions: list[PerpPosition] = field(default_factory=list)

    @property
    def long_short_ratio(self) -> float:
        if self.short_volume_usd == 0:
            return float("inf") if self.long_volume_usd > 0 else 1.0
        return self.long_volume_usd / self.short_volume_usd

    @property
    def sentiment(self) -> str:
        ratio = self.long_short_ratio
        if ratio > 2.0:
            return "strongly bullish"
        elif ratio > 1.3:
            return "bullish"
        elif ratio > 0.7:
            return "neutral"
        elif ratio > 0.5:
            return "bearish"
        else:
            return "strongly bearish"


def parse_perp_trades(data: Any) -> list[PerpPosition]:
    """Parse raw Nansen perp trades response into PerpPosition objects."""
    positions = []
    if not data:
        return positions

    items = data
    if isinstance(data, dict):
        items = data.get("data", [])
    if not isinstance(items, list):
        return positions

    for item in items:
        if not isinstance(item, dict):
            continue
        positions.append(PerpPosition(
            trader=item.get("trader_address", ""),
            trader_label=item.get("trader_address_label", ""),
            token=item.get("token_symbol", "???"),
            side=item.get("side", ""),
            action=item.get("action", ""),
            amount=_to_float(item.get("token_amount", 0)),
            price_usd=_to_float(item.get("price_usd", 0)),
            value_usd=_to_float(item.get("value_usd", 0)),
            order_type=item.get("type", ""),
            timestamp=item.get("block_timestamp", ""),
            tx_hash=item.get("transaction_hash", ""),
        ))

    return positions


def analyze_perp_activity(positions: list[PerpPosition]) -> PerpSummary:
    """Aggregate perp positions into a summary with token breakdown."""
    summary = PerpSummary(
        total_positions=len(positions),
        positions=positions,
    )

    traders = set()
    token_volume: dict[str, dict] = {}

    for pos in positions:
        summary.total_volume_usd += pos.value_usd
        traders.add(pos.trader)

        if pos.side.lower() == "long":
            summary.long_volume_usd += pos.value_usd
        elif pos.side.lower() == "short":
            summary.short_volume_usd += pos.value_usd

        if pos.token not in token_volume:
            token_volume[pos.token] = {
                "token": pos.token, "long_vol": 0, "short_vol": 0,
                "total_vol": 0, "trade_count": 0,
            }
        tv = token_volume[pos.token]
        tv["total_vol"] += pos.value_usd
        tv["trade_count"] += 1
        if pos.side.lower() == "long":
            tv["long_vol"] += pos.value_usd
        elif pos.side.lower() == "short":
            tv["short_vol"] += pos.value_usd

    summary.unique_traders = len(traders)
    summary.top_tokens = sorted(
        token_volume.values(), key=lambda x: x["total_vol"], reverse=True
    )[:10]

    return summary


def detect_perp_signals(
    positions: list[PerpPosition],
    min_value_usd: float = 10_000,
) -> list[Signal]:
    """
    Detect actionable signals from perp trading activity.

    - Large individual positions
    - Coordinated long/short activity on same token
    - SM consensus (multiple traders same direction)
    """
    signals = []

    # 1. Large individual positions
    for pos in positions:
        if pos.value_usd >= min_value_usd and pos.action.lower() == "open":
            signals.append(Signal(
                type="perp_whale",
                severity=Severity.HIGH if pos.value_usd >= 50_000 else Severity.MEDIUM,
                chain="hyperliquid",
                token=pos.token,
                summary=(f"SM perp {pos.side} {pos.action}: ${pos.value_usd:,.0f} "
                         f"{pos.token} @ ${pos.price_usd:,.2f}"
                         f"{' by ' + pos.trader_label if pos.trader_label else ''}"),
                details={
                    "side": pos.side,
                    "action": pos.action,
                    "value_usd": pos.value_usd,
                    "price_usd": pos.price_usd,
                    "trader": pos.trader,
                    "trader_label": pos.trader_label,
                },
                score=min(60 + (pos.value_usd / 10_000) * 5, 100),
            ))

    # 2. Token consensus — multiple SMs same direction
    token_sides: dict[str, dict] = {}
    for pos in positions:
        if pos.action.lower() != "open":
            continue
        key = pos.token
        if key not in token_sides:
            token_sides[key] = {"long_traders": set(), "short_traders": set(),
                                "long_vol": 0, "short_vol": 0}
        ts = token_sides[key]
        if pos.side.lower() == "long":
            ts["long_traders"].add(pos.trader)
            ts["long_vol"] += pos.value_usd
        elif pos.side.lower() == "short":
            ts["short_traders"].add(pos.trader)
            ts["short_vol"] += pos.value_usd

    for token, ts in token_sides.items():
        long_count = len(ts["long_traders"])
        short_count = len(ts["short_traders"])

        if long_count >= 3:
            signals.append(Signal(
                type="perp_consensus_long",
                severity=Severity.HIGH,
                chain="hyperliquid",
                token=token,
                summary=(f"SM perp consensus LONG on {token}: "
                         f"{long_count} traders, ${ts['long_vol']:,.0f} total"),
                details={
                    "long_traders": long_count,
                    "short_traders": short_count,
                    "long_volume": ts["long_vol"],
                    "short_volume": ts["short_vol"],
                },
                score=min(70 + long_count * 5, 100),
            ))

        if short_count >= 3:
            signals.append(Signal(
                type="perp_consensus_short",
                severity=Severity.HIGH,
                chain="hyperliquid",
                token=token,
                summary=(f"SM perp consensus SHORT on {token}: "
                         f"{short_count} traders, ${ts['short_vol']:,.0f} total"),
                details={
                    "long_traders": long_count,
                    "short_traders": short_count,
                    "long_volume": ts["long_vol"],
                    "short_volume": ts["short_vol"],
                },
                score=min(70 + short_count * 5, 100),
            ))

    return signals


def generate_perp_report(summary: PerpSummary) -> str:
    """Generate markdown report for perp activity."""
    lines = []
    lines.append("# Smart Money Perpetual Trading Report\n")
    lines.append(f"**Positions:** {summary.total_positions} | "
                 f"**Volume:** ${summary.total_volume_usd:,.0f} | "
                 f"**Traders:** {summary.unique_traders}\n")
    lines.append(f"**Long/Short Ratio:** {summary.long_short_ratio:.2f} "
                 f"({summary.sentiment})\n")
    lines.append(f"- Long volume: ${summary.long_volume_usd:,.0f}")
    lines.append(f"- Short volume: ${summary.short_volume_usd:,.0f}\n")

    if summary.top_tokens:
        lines.append("## Top Tokens by Volume\n")
        lines.append("| Token | Volume | Trades | Long | Short |")
        lines.append("|-------|--------|--------|------|-------|")
        for t in summary.top_tokens[:10]:
            lines.append(
                f"| {t['token']} | ${t['total_vol']:,.0f} | {t['trade_count']} | "
                f"${t['long_vol']:,.0f} | ${t['short_vol']:,.0f} |"
            )

    if summary.positions:
        lines.append("\n## Recent Positions\n")
        for pos in summary.positions[:15]:
            emoji = "🟢" if pos.side.lower() == "long" else "🔴"
            lines.append(
                f"- {emoji} **{pos.side} {pos.action}** {pos.token} "
                f"${pos.value_usd:,.0f} @ ${pos.price_usd:,.2f} "
                f"— {pos.trader_label or pos.trader[:10]}"
            )

    return "\n".join(lines)


def _to_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(str(val).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return 0.0
