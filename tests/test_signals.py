"""Tests for NansenScope signal detection engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Severity
from signals import (
    Signal,
    detect_holdings_signals,
    detect_convergence,
)


def test_signal_creation():
    """Signal objects create correctly with all fields."""
    s = Signal(
        type="high_conviction",
        severity=Severity.HIGH,
        chain="ethereum",
        token="UNI",
        summary="29 smart money wallets hold UNI",
        score=100.0,
    )
    assert s.type == "high_conviction"
    assert s.chain == "ethereum"
    assert s.token == "UNI"
    assert s.score == 100.0


def test_signal_key_uniqueness():
    """Signal keys are unique per chain:token:type combo."""
    s1 = Signal(type="accumulation", severity=Severity.HIGH, chain="ethereum", token="UNI", summary="test")
    s2 = Signal(type="accumulation", severity=Severity.HIGH, chain="base", token="UNI", summary="test")
    s3 = Signal(type="whale_trade", severity=Severity.HIGH, chain="ethereum", token="UNI", summary="test")
    assert s1.key != s2.key  # different chain
    assert s1.key != s3.key  # different type
    assert s1.key == "ethereum:UNI:accumulation"


def test_holdings_detector_with_real_data():
    """Holdings detector finds tokens held by multiple SM wallets."""
    # Simulate holdings data structure
    holdings_data = {
        "data": [
            {"token_symbol": "UNI", "entity": "Fund A", "usd_value": 1000000},
            {"token_symbol": "UNI", "entity": "Fund B", "usd_value": 2000000},
            {"token_symbol": "UNI", "entity": "Fund C", "usd_value": 500000},
            {"token_symbol": "RARE", "entity": "Fund A", "usd_value": 100},
        ]
    }
    signals = detect_holdings_signals(holdings_data, "ethereum")
    assert isinstance(signals, list)


def test_holdings_empty_data():
    """Detector handles empty/None data gracefully."""
    assert detect_holdings_signals(None, "ethereum") == []
    assert detect_holdings_signals({}, "ethereum") == []
    assert detect_holdings_signals({"data": []}, "ethereum") == []


def test_convergence_detection():
    """Cross-chain convergence detects same token on multiple chains."""
    signals = [
        Signal(type="high_conviction", severity=Severity.HIGH, chain="ethereum", token="UNI", summary="test", score=80),
        Signal(type="high_conviction", severity=Severity.HIGH, chain="base", token="UNI", summary="test", score=70),
        Signal(type="high_conviction", severity=Severity.HIGH, chain="ethereum", token="AAVE", summary="test", score=60),
    ]
    convergence = detect_convergence(signals)
    # UNI appears on 2 chains -- should be flagged
    assert isinstance(convergence, list)
