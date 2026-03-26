"""
NansenScope — Signal Detection Engine

Analyzes raw Nansen data to detect actionable smart money signals.
Each detector function examines one data source and emits Signal objects.
The engine then cross-references signals for convergence detection.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from config import DEFAULT_THRESHOLDS, Severity, SignalThresholds

log = logging.getLogger("nansenscope.signals")


# ── Signal Data Model ────────────────────────────────────────────────────────

@dataclass
class Signal:
    """A single detected smart money signal."""

    type: str                   # e.g., "accumulation", "large_netflow", "whale_trade"
    severity: Severity
    chain: str
    token: str                  # Token symbol or address
    summary: str                # Human-readable one-liner
    details: dict = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )
    score: float = 0.0         # Composite score for ranking (0-100)

    @property
    def key(self) -> str:
        """Unique key for deduplication and convergence matching."""
        return f"{self.chain}:{self.token}:{self.type}"


# ── Signal Detectors ─────────────────────────────────────────────────────────

def detect_netflow_signals(
    data: Any, chain: str, thresholds: SignalThresholds = DEFAULT_THRESHOLDS
) -> list[Signal]:
    """
    Analyze net capital flows for significant movements.

    Looks for:
    - Large positive netflows (accumulation)
    - Large negative netflows (distribution)
    - Extreme flow imbalances
    """
    signals = []
    if not data or not isinstance(data, list):
        return signals

    for item in data:
        if not isinstance(item, dict):
            continue

        token = item.get("token_symbol") or item.get("symbol") or item.get("token", "???")
        netflow = _to_float(
            item.get("net_flow_24h_usd") or item.get("net_flow_7d_usd")
            or item.get("netflow_usd") or item.get("netflow") or item.get("net_flow", 0)
        )
        inflow = _to_float(item.get("inflow_usd") or item.get("inflow", 0))
        outflow = _to_float(item.get("outflow_usd") or item.get("outflow", 0))

        abs_flow = abs(netflow)

        if abs_flow >= thresholds.netflow_large_usd:
            direction = "inflow" if netflow > 0 else "outflow"
            signals.append(Signal(
                type="large_netflow",
                severity=Severity.HIGH,
                chain=chain,
                token=token,
                summary=f"${abs_flow:,.0f} net {direction} on {token}",
                details={
                    "netflow_usd": netflow,
                    "inflow_usd": inflow,
                    "outflow_usd": outflow,
                    "direction": direction,
                },
                score=min(80 + (abs_flow / thresholds.netflow_large_usd) * 10, 100),
            ))
        elif abs_flow >= thresholds.netflow_significant_usd:
            direction = "inflow" if netflow > 0 else "outflow"
            signals.append(Signal(
                type="notable_netflow",
                severity=Severity.MEDIUM,
                chain=chain,
                token=token,
                summary=f"${abs_flow:,.0f} net {direction} on {token}",
                details={
                    "netflow_usd": netflow,
                    "inflow_usd": inflow,
                    "outflow_usd": outflow,
                    "direction": direction,
                },
                score=40 + (abs_flow / thresholds.netflow_large_usd) * 30,
            ))

    return signals


def detect_dex_trade_signals(
    data: Any, chain: str, thresholds: SignalThresholds = DEFAULT_THRESHOLDS
) -> list[Signal]:
    """
    Analyze DEX trades for whale activity and accumulation patterns.

    Looks for:
    - Whale-sized single trades
    - Clusters of buys on same token (accumulation)
    - Smart money consensus (multiple wallets buying same token)
    """
    signals = []
    if not data or not isinstance(data, list):
        return signals

    # Track buy/sell aggregates per token
    token_activity: dict[str, dict] = {}

    for trade in data:
        if not isinstance(trade, dict):
            continue

        # Nansen CLI DEX trades use token_bought_symbol / token_sold_symbol
        bought_token = trade.get("token_bought_symbol") or ""
        sold_token = trade.get("token_sold_symbol") or ""
        token = (
            bought_token or sold_token
            or trade.get("token_symbol")
            or trade.get("symbol")
            or trade.get("token", "???")
        )
        amount_usd = _to_float(
            trade.get("trade_value_usd")
            or trade.get("amount_usd")
            or trade.get("value_usd", 0)
        )
        # Infer side: if bought_token is not a stablecoin, it's a buy
        stables = {"USDC", "USDT", "DAI", "BUSD", "TUSD", "FRAX", "LUSD", "USDD", "USDP"}
        if bought_token and bought_token.upper() not in stables:
            side = "buy"
            token = bought_token
        elif sold_token and sold_token.upper() not in stables:
            side = "sell"
            token = sold_token
        else:
            side = (trade.get("side") or trade.get("type") or "").lower()
        wallet = trade.get("trader_address") or trade.get("address") or trade.get("wallet") or ""
        label = trade.get("trader_address_label") or trade.get("label") or trade.get("entity") or ""

        # Whale individual trade
        if amount_usd >= thresholds.dex_trade_whale_usd:
            signals.append(Signal(
                type="whale_trade",
                severity=Severity.HIGH,
                chain=chain,
                token=token,
                summary=f"Whale {side or 'trade'}: ${amount_usd:,.0f} of {token}" + (f" by {label}" if label else ""),
                details={
                    "amount_usd": amount_usd,
                    "side": side,
                    "wallet": wallet,
                    "label": label,
                },
                score=70 + min((amount_usd / thresholds.dex_trade_whale_usd) * 15, 30),
            ))

        # Aggregate per token for pattern detection
        if token not in token_activity:
            token_activity[token] = {"buys": 0, "sells": 0, "buy_vol": 0, "sell_vol": 0, "wallets": set()}

        agg = token_activity[token]
        if side in ("buy", "bought"):
            agg["buys"] += 1
            agg["buy_vol"] += amount_usd
        elif side in ("sell", "sold"):
            agg["sells"] += 1
            agg["sell_vol"] += amount_usd
        if wallet:
            agg["wallets"].add(wallet)

    # Detect accumulation/distribution patterns
    for token, agg in token_activity.items():
        buys, sells = agg["buys"], agg["sells"]
        buy_vol, sell_vol = agg["buy_vol"], agg["sell_vol"]
        wallet_count = len(agg["wallets"])

        # Accumulation: heavy buying from multiple wallets
        if buys > 0 and sells > 0:
            ratio = buy_vol / sell_vol if sell_vol > 0 else float("inf")
            if ratio >= thresholds.accumulation_ratio and buy_vol >= thresholds.dex_trade_notable_usd:
                signals.append(Signal(
                    type="accumulation",
                    severity=Severity.HIGH,
                    chain=chain,
                    token=token,
                    summary=f"Smart money accumulating {token}: {buys} buys (${buy_vol:,.0f}) vs {sells} sells (${sell_vol:,.0f})",
                    details={
                        "buy_count": buys,
                        "sell_count": sells,
                        "buy_volume_usd": buy_vol,
                        "sell_volume_usd": sell_vol,
                        "buy_sell_ratio": round(ratio, 2),
                        "distinct_wallets": wallet_count,
                    },
                    score=min(60 + ratio * 10 + wallet_count * 5, 100),
                ))
            elif ratio <= thresholds.distribution_ratio and sell_vol >= thresholds.dex_trade_notable_usd:
                signals.append(Signal(
                    type="distribution",
                    severity=Severity.HIGH,
                    chain=chain,
                    token=token,
                    summary=f"Smart money distributing {token}: {sells} sells (${sell_vol:,.0f}) vs {buys} buys (${buy_vol:,.0f})",
                    details={
                        "buy_count": buys,
                        "sell_count": sells,
                        "buy_volume_usd": buy_vol,
                        "sell_volume_usd": sell_vol,
                        "buy_sell_ratio": round(ratio, 2),
                        "distinct_wallets": wallet_count,
                    },
                    score=min(60 + (1 / ratio if ratio > 0 else 10) * 10 + wallet_count * 5, 100),
                ))
        elif buys > 0 and sells == 0 and buy_vol >= thresholds.dex_trade_notable_usd:
            signals.append(Signal(
                type="accumulation",
                severity=Severity.MEDIUM,
                chain=chain,
                token=token,
                summary=f"Buy-only activity on {token}: {buys} buys (${buy_vol:,.0f}), no sells",
                details={
                    "buy_count": buys,
                    "buy_volume_usd": buy_vol,
                    "distinct_wallets": wallet_count,
                },
                score=50 + min(wallet_count * 10, 30),
            ))

    return signals


def detect_holdings_signals(
    data: Any, chain: str, thresholds: SignalThresholds = DEFAULT_THRESHOLDS
) -> list[Signal]:
    """
    Analyze smart money holdings for conviction positions.

    Looks for:
    - Tokens with high smart money holder count
    - Large concentrated positions
    """
    signals = []
    if not data or not isinstance(data, list):
        return signals

    for item in data:
        if not isinstance(item, dict):
            continue

        token = item.get("token_symbol") or item.get("symbol") or item.get("token", "???")
        holders = _to_int(
            item.get("holders_count") or item.get("smart_money_holders")
            or item.get("holder_count") or item.get("holders", 0)
        )
        value_usd = _to_float(
            item.get("value_usd") or item.get("total_value_usd")
            or item.get("balance_usd", 0)
        )
        pct_change = _to_float(
            item.get("balance_24h_percent_change") or item.get("change_pct")
            or item.get("pct_change", 0)
        )

        if holders >= thresholds.screener_min_smart_holders:
            severity = Severity.HIGH if holders >= thresholds.screener_min_smart_holders * 2 else Severity.MEDIUM
            signals.append(Signal(
                type="high_conviction",
                severity=severity,
                chain=chain,
                token=token,
                summary=f"{holders} smart money wallets hold {token}" + (f" (${value_usd:,.0f})" if value_usd else ""),
                details={
                    "smart_holders": holders,
                    "total_value_usd": value_usd,
                    "change_pct": pct_change,
                },
                score=min(40 + holders * 8, 100),
            ))

        if abs(pct_change) >= thresholds.holdings_change_pct and value_usd > 0:
            direction = "increased" if pct_change > 0 else "decreased"
            signals.append(Signal(
                type="position_shift",
                severity=Severity.MEDIUM,
                chain=chain,
                token=token,
                summary=f"Smart money {direction} {token} holdings by {abs(pct_change):.1f}%",
                details={
                    "change_pct": pct_change,
                    "value_usd": value_usd,
                    "direction": direction,
                },
                score=min(30 + abs(pct_change), 80),
            ))

    return signals


def detect_screener_signals(
    data: Any, chain: str, thresholds: SignalThresholds = DEFAULT_THRESHOLDS
) -> list[Signal]:
    """
    Analyze token screener data for trending tokens with smart money interest.
    """
    signals = []
    if not data or not isinstance(data, list):
        return signals

    for item in data:
        if not isinstance(item, dict):
            continue

        token = item.get("token_symbol") or item.get("symbol") or item.get("token", "???")
        sm_holders = _to_int(item.get("smart_money_holders") or item.get("sm_holders", 0))
        sm_buys = _to_int(item.get("smart_money_buys") or item.get("sm_buys", 0))
        sm_sells = _to_int(item.get("smart_money_sells") or item.get("sm_sells", 0))
        price_change = _to_float(item.get("price_change_pct") or item.get("price_change", 0))
        volume = _to_float(item.get("volume_usd") or item.get("volume", 0))

        if sm_holders >= thresholds.screener_min_smart_holders:
            net_activity = sm_buys - sm_sells
            sentiment = "bullish" if net_activity > 0 else "bearish" if net_activity < 0 else "neutral"

            signals.append(Signal(
                type="screener_trending",
                severity=Severity.HIGH if sm_holders >= thresholds.screener_min_smart_holders * 2 else Severity.MEDIUM,
                chain=chain,
                token=token,
                summary=f"{token} trending: {sm_holders} SM holders, {sm_buys} buys/{sm_sells} sells ({sentiment})",
                details={
                    "smart_money_holders": sm_holders,
                    "smart_money_buys": sm_buys,
                    "smart_money_sells": sm_sells,
                    "net_activity": net_activity,
                    "sentiment": sentiment,
                    "price_change_pct": price_change,
                    "volume_usd": volume,
                },
                score=min(50 + sm_holders * 5 + abs(net_activity) * 3, 100),
            ))

    return signals


# ── DCA Signal Detector ──────────────────────────────────────────────────────

def detect_dca_signals(
    data: Any, chain: str, thresholds: SignalThresholds = DEFAULT_THRESHOLDS
) -> list[Signal]:
    """
    Analyze Smart Money DCA (Dollar Cost Averaging) activity.

    DCA = strong conviction — smart money systematically buying over time.
    Jupiter DCA strategies (Solana). Signals are HIGH or CRITICAL severity
    because DCA implies deliberate, high-conviction accumulation.

    Looks for:
    - Tokens being DCA'd by multiple wallets
    - Large total USD committed via DCA
    - High-frequency DCA orders
    """
    signals = []
    if not data:
        return signals

    # Handle both list and dict formats
    items = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
    if not items:
        return signals

    for item in items:
        if not isinstance(item, dict):
            continue

        token = (
            item.get("token_symbol") or item.get("symbol")
            or item.get("output_token_symbol") or item.get("output_token")
            or item.get("token") or "???"
        )
        wallet_count = _to_int(
            item.get("wallet_count") or item.get("wallets")
            or item.get("unique_wallets") or item.get("num_wallets", 0)
        )
        total_usd = _to_float(
            item.get("total_usd") or item.get("total_value_usd")
            or item.get("volume_usd") or item.get("amount_usd")
            or item.get("total_amount_usd", 0)
        )
        order_count = _to_int(
            item.get("order_count") or item.get("orders")
            or item.get("num_orders") or item.get("dca_count", 0)
        )
        frequency = item.get("frequency") or item.get("interval") or ""
        input_token = (
            item.get("input_token_symbol") or item.get("input_token")
            or item.get("from_token") or ""
        )

        # Skip entries with no meaningful data
        if not token or token == "???":
            continue

        # Determine severity: CRITICAL if multiple wallets or large USD commitment
        if wallet_count >= 3 or total_usd >= 100_000:
            severity = Severity.CRITICAL
        else:
            severity = Severity.HIGH

        # Build summary
        parts = [f"Smart money DCA into {token}"]
        if wallet_count:
            parts.append(f"{wallet_count} wallets")
        if total_usd:
            parts.append(f"${total_usd:,.0f} committed")
        if order_count:
            parts.append(f"{order_count} orders")
        if frequency:
            parts.append(f"freq: {frequency}")
        summary = " | ".join(parts)

        # Score: DCA is high-conviction by nature
        score = 70.0
        if wallet_count:
            score += min(wallet_count * 5, 15)
        if total_usd >= 50_000:
            score += 10
        if total_usd >= 500_000:
            score += 5
        score = min(score, 100)

        signals.append(Signal(
            type="smart_money_dca",
            severity=severity,
            chain=chain,
            token=token,
            summary=summary,
            details={
                "wallet_count": wallet_count,
                "total_usd": total_usd,
                "order_count": order_count,
                "frequency": frequency,
                "input_token": input_token,
            },
            score=score,
        ))

    log.info("Detected %d DCA signals on %s", len(signals), chain)
    return signals


# ── Cross-Signal Convergence ─────────────────────────────────────────────────

def detect_convergence(
    all_signals: list[Signal],
    min_signals: int = DEFAULT_THRESHOLDS.convergence_min_signals,
) -> list[Signal]:
    """
    Find tokens that appear in multiple independent signal sources.
    Convergence = multiple smart money data points pointing the same direction.
    This is the highest-conviction signal NansenScope can produce.
    """
    # Group signals by (chain, token)
    token_signals: dict[tuple[str, str], list[Signal]] = {}
    for sig in all_signals:
        key = (sig.chain, sig.token)
        token_signals.setdefault(key, []).append(sig)

    convergence_signals = []
    for (chain, token), sigs in token_signals.items():
        # Only flag if we have signals from distinct types
        unique_types = {s.type for s in sigs}
        if len(unique_types) < min_signals:
            continue

        # Determine if signals are directionally aligned
        bullish = sum(1 for s in sigs if _is_bullish(s))
        bearish = sum(1 for s in sigs if _is_bearish(s))
        total = len(sigs)

        if bullish > bearish:
            direction = "bullish"
            alignment = bullish / total
        elif bearish > bullish:
            direction = "bearish"
            alignment = bearish / total
        else:
            direction = "mixed"
            alignment = 0.5

        max_score = max(s.score for s in sigs)
        avg_score = sum(s.score for s in sigs) / total

        convergence_signals.append(Signal(
            type="convergence",
            severity=Severity.CRITICAL if len(unique_types) >= 3 else Severity.HIGH,
            chain=chain,
            token=token,
            summary=(
                f"CONVERGENCE: {token} on {chain} — {len(unique_types)} signal types, "
                f"{direction} ({alignment:.0%} aligned)"
            ),
            details={
                "signal_count": total,
                "unique_signal_types": sorted(unique_types),
                "direction": direction,
                "alignment": round(alignment, 2),
                "component_signals": [s.summary for s in sigs],
                "bullish_count": bullish,
                "bearish_count": bearish,
            },
            score=min(avg_score + len(unique_types) * 10 + alignment * 15, 100),
        ))

    # Sort by score descending
    convergence_signals.sort(key=lambda s: s.score, reverse=True)
    return convergence_signals


def _is_bullish(signal: Signal) -> bool:
    d = signal.details
    if signal.type == "accumulation":
        return True
    if signal.type in ("large_netflow", "notable_netflow"):
        return d.get("direction") == "inflow"
    if signal.type == "position_shift":
        return d.get("direction") == "increased"
    if signal.type == "screener_trending":
        return d.get("sentiment") == "bullish"
    if signal.type == "whale_trade":
        return d.get("side") in ("buy", "bought")
    return False


def _is_bearish(signal: Signal) -> bool:
    d = signal.details
    if signal.type == "distribution":
        return True
    if signal.type in ("large_netflow", "notable_netflow"):
        return d.get("direction") == "outflow"
    if signal.type == "position_shift":
        return d.get("direction") == "decreased"
    if signal.type == "screener_trending":
        return d.get("sentiment") == "bearish"
    if signal.type == "whale_trade":
        return d.get("side") in ("sell", "sold")
    return False


# ── Master Detection Pipeline ────────────────────────────────────────────────

def analyze_chain_data(
    chain: str,
    scan_results: dict,
    thresholds: SignalThresholds = DEFAULT_THRESHOLDS,
) -> list[Signal]:
    """
    Run all detectors on a chain's scan results.
    Returns deduplicated, scored, and sorted signals.
    """
    signals = []

    # Extract data from ScanResults, handling both success and failure
    netflow_data = _extract_data(scan_results.get("netflows"))
    dex_data = _extract_data(scan_results.get("dex_trades"))
    holdings_data = _extract_data(scan_results.get("holdings"))
    screener_data = _extract_data(scan_results.get("token_screener"))
    dca_data = _extract_data(scan_results.get("dcas"))

    # Run individual detectors
    signals.extend(detect_netflow_signals(netflow_data, chain, thresholds))
    signals.extend(detect_dex_trade_signals(dex_data, chain, thresholds))
    signals.extend(detect_holdings_signals(holdings_data, chain, thresholds))
    signals.extend(detect_screener_signals(screener_data, chain, thresholds))
    signals.extend(detect_dca_signals(dca_data, chain, thresholds))

    # Detect cross-signal convergence
    convergence = detect_convergence(signals, thresholds.convergence_min_signals)
    signals.extend(convergence)

    # Sort by score descending
    signals.sort(key=lambda s: s.score, reverse=True)

    log.info("Detected %d signals on %s (%d convergence)", len(signals), chain, len(convergence))
    return signals


def analyze_all_chains(
    all_scan_results: dict,
    thresholds: SignalThresholds = DEFAULT_THRESHOLDS,
) -> dict[str, list[Signal]]:
    """Run signal analysis across all scanned chains."""
    return {
        chain: analyze_chain_data(chain, results, thresholds)
        for chain, results in all_scan_results.items()
    }


def rank_signals(all_signals: dict[str, list[Signal]], top_n: int = 20) -> list[Signal]:
    """Flatten and rank all signals across chains by score."""
    flat = [sig for sigs in all_signals.values() for sig in sigs]
    flat.sort(key=lambda s: s.score, reverse=True)
    return flat[:top_n]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_data(scan_result) -> Any:
    """Safely extract data from a ScanResult, unwrapping nested {data: [...]} envelopes."""
    if scan_result is None:
        return None
    if hasattr(scan_result, "success") and scan_result.success:
        data = scan_result.data
        # Nansen CLI wraps results in {"data": [...], "pagination": {...}}
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data
    return None


def _to_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(str(val).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return 0.0


def _to_int(val: Any) -> int:
    if val is None:
        return 0
    try:
        return int(float(str(val).replace(",", "")))
    except (ValueError, TypeError):
        return 0
