"""
NansenScope — Configuration & Thresholds

Central configuration for chains, signal thresholds, output settings,
and API tracking. All values are tunable for different market conditions.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# ── Supported Chains ─────────────────────────────────────────────────────────

SUPPORTED_CHAINS = [
    "ethereum",
    "base",
    "solana",
    "arbitrum",
    "bnb",
]

# Extended chains available in Nansen but not scanned by default
EXTENDED_CHAINS = [
    "polygon",
    "optimism",
    "avalanche",
    "linea",
    "scroll",
    "mantle",
    "ronin",
    "sei",
    "sonic",
]


# ── Signal Severity ──────────────────────────────────────────────────────────

class Severity(str, Enum):
    CRITICAL = "critical"   # Immediate action needed
    HIGH = "high"           # Strong signal, worth watching closely
    MEDIUM = "medium"       # Notable but not urgent
    LOW = "low"             # Informational


# ── Signal Thresholds ────────────────────────────────────────────────────────

@dataclass
class SignalThresholds:
    """Configurable thresholds for signal detection."""

    # Netflow: minimum absolute USD value to flag
    netflow_significant_usd: float = 1_000_000
    netflow_large_usd: float = 10_000_000

    # DEX trades: minimum trade size in USD
    dex_trade_notable_usd: float = 100_000
    dex_trade_whale_usd: float = 1_000_000

    # Holdings: minimum position change percentage to flag
    holdings_change_pct: float = 10.0

    # Token screener: minimum smart money holders to flag
    screener_min_smart_holders: int = 3

    # Accumulation: minimum buy/sell ratio to flag as accumulation
    accumulation_ratio: float = 2.0

    # Distribution: maximum buy/sell ratio to flag as distribution
    distribution_ratio: float = 0.5

    # Convergence: minimum distinct signals on same token to flag
    convergence_min_signals: int = 2

    # Wallet profiler: minimum PnL to consider "successful"
    wallet_min_pnl_usd: float = 50_000


# ── Output Settings ──────────────────────────────────────────────────────────

@dataclass
class OutputSettings:
    """Report and display configuration."""

    report_dir: Path = field(default_factory=lambda: Path("reports"))
    max_signals_per_chain: int = 20
    max_tokens_in_report: int = 50
    date_format: str = "%Y-%m-%d %H:%M UTC"
    markdown_width: int = 120


# ── API Tracking ─────────────────────────────────────────────────────────────

@dataclass
class APITracker:
    """Track API calls and estimated cost."""

    total_calls: int = 0
    calls_by_endpoint: dict = field(default_factory=dict)
    errors: int = 0

    def record(self, endpoint: str) -> None:
        self.total_calls += 1
        self.calls_by_endpoint[endpoint] = self.calls_by_endpoint.get(endpoint, 0) + 1

    def record_error(self) -> None:
        self.errors += 1

    @property
    def summary(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "errors": self.errors,
            "by_endpoint": dict(self.calls_by_endpoint),
        }


# ── Global Defaults ──────────────────────────────────────────────────────────

DEFAULT_CHAINS = SUPPORTED_CHAINS
DEFAULT_THRESHOLDS = SignalThresholds()
DEFAULT_OUTPUT = OutputSettings()

# Singleton tracker — shared across the entire scan session
api_tracker = APITracker()
