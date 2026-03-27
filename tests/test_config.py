"""Tests for NansenScope configuration module."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    SUPPORTED_CHAINS,
    EXTENDED_CHAINS,
    ALL_CHAINS,
    DEFAULT_CHAINS,
    Severity,
    SignalThresholds,
    DEFAULT_THRESHOLDS,
    api_tracker,
)


def test_chain_counts():
    """Verify documented chain counts match reality."""
    assert len(SUPPORTED_CHAINS) == 5, f"Expected 5 supported chains, got {len(SUPPORTED_CHAINS)}"
    assert len(ALL_CHAINS) == 18, f"Expected 18 total chains, got {len(ALL_CHAINS)}"
    assert DEFAULT_CHAINS == SUPPORTED_CHAINS


def test_chain_names():
    """Verify core chains are present."""
    for chain in ["ethereum", "solana", "base", "bnb", "arbitrum"]:
        assert chain in SUPPORTED_CHAINS, f"{chain} missing from SUPPORTED_CHAINS"


def test_severity_ordering():
    """Severity levels exist and are strings."""
    assert Severity.CRITICAL == "critical"
    assert Severity.HIGH == "high"
    assert Severity.MEDIUM == "medium"
    assert Severity.LOW == "low"


def test_default_thresholds():
    """Default thresholds are sensible."""
    t = DEFAULT_THRESHOLDS
    assert t.netflow_significant_usd > 0
    assert t.netflow_large_usd > t.netflow_significant_usd
    assert t.dex_trade_whale_usd > 0
    assert t.screener_min_smart_holders >= 1


def test_api_tracker():
    """API tracker starts at zero and records calls."""
    tracker = type(api_tracker)()  # fresh instance
    assert tracker.total_calls == 0
    tracker.record("test/endpoint")
    assert tracker.total_calls == 1
    assert tracker.calls_by_endpoint["test/endpoint"] == 1
    tracker.record("test/endpoint")
    assert tracker.total_calls == 2
    assert tracker.calls_by_endpoint["test/endpoint"] == 2
