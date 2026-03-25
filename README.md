
<p align="center">
<pre>
 _   _                            ____
| \ | | __ _ _ __  ___  ___ _ __ / ___|  ___ ___  _ __   ___
|  \| |/ _` | '_ \/ __|/ _ \ '_ \\___ \ / __/ _ \| '_ \ / _ \
| |\  | (_| | | | \__ \  __/ | | |___) | (_| (_) | |_) |  __/
|_| \_|\__,_|_| |_|___/\___|_| |_|____/ \___\___/| .__/ \___|
                                                  |_|
</pre>
</p>

<h3 align="center">Autonomous Smart Money Intelligence Agent powered by Nansen CLI</h3>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#commands">Commands</a> •
  <a href="#chains">Chains</a> •
  <a href="#how-it-works">How It Works</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/chains-18-blue?style=flat-square" alt="18 Chains" />
  <img src="https://img.shields.io/badge/signals-9_engines-orange?style=flat-square" alt="9 Signal Engines" />
  <img src="https://img.shields.io/badge/python-3.11+-green?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square" alt="MIT License" />
  <img src="https://img.shields.io/badge/%23NansenCLI-Challenge_Week_2-purple?style=flat-square" alt="NansenCLI Challenge" />
</p>

---

**NansenScope** doesn't just read Nansen data — it thinks about it. It scans 18 chains, detects signals across netflows/DEX trades/holdings/screener data, cross-references them for convergence, maps wallet networks via BFS graph traversal, tracks perpetual positions on Hyperliquid, and delivers prioritized intelligence reports. One command. Zero manual work.

---

## Features

| Module | Command | What It Does |
|--------|---------|-------------|
| **⚡ Chain Sweep** | `scan` | Multi-chain smart money scan across 18 chains — netflows, DEX trades, holdings, token screener — all in parallel |
| **🕸️ Syndicate Hunter** | `network` | Wallet cluster detection via BFS graph traversal. Maps counterparties, related wallets, and first-funders to expose coordinated groups |
| **📊 Leverage Radar** | `perps` | Hyperliquid perpetual position intelligence — long/short ratios, top tokens, whale position tracking |
| **🎯 Signal Fusion** | `signals` | Cross-chain convergence detection. When multiple signal types fire on the same token across chains, that's alpha |
| **🚨 Threat Matrix** | `alerts` | Rule-based alert engine with cooldown management, deduplication, and persistent history tracking |
| **🎨 Intel Canvas** | `charts` | Plotly visualizations — chain heatmaps, signal severity distributions, netflow comparisons, bubble maps |
| **📋 Morning Brief** | `daily` | Full daily pipeline: scan → signals → alerts → perps → charts → report. One command, complete intel |
| **🔍 Deep Dive** | `profile` | Single wallet forensics — PnL summary, counterparties, labels, balance, trading performance |
| **📄 Situation Report** | `report` | Full intelligence report in structured markdown — human-readable and LLM-parseable |

---

## Quick Start

### Prerequisites

- Python 3.11+
- [Nansen CLI](https://cli.nansen.ai) installed and authenticated (`nansen auth login`)

### Install

```bash
# Clone
git clone https://github.com/yourusername/nansenscope.git
cd nansenscope

# Install dependencies
pip install -r requirements.txt

# Run your first scan
python nansenscope.py scan --chains ethereum,base,solana
```

### First Commands

```bash
# Full scan across default chains (ethereum, solana, base, bnb, arbitrum)
python nansenscope.py scan

# Deep dive on a specific wallet
python nansenscope.py profile --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045

# Detect cross-chain convergence signals
python nansenscope.py signals --top 20

# Map a wallet's network (THE killer feature)
python nansenscope.py network --address 0x... --hops 2 --max-nodes 30

# Smart Money perp positions on Hyperliquid
python nansenscope.py perps --limit 50

# Run the full daily pipeline
python nansenscope.py daily
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        NansenScope CLI                          │
│                      nansenscope.py (9 commands)                │
├─────────────┬──────────────┬──────────────┬─────────────────────┤
│             │              │              │                     │
│  scanner.py │  signals.py  │  network.py  │     perps.py        │
│  ─────────  │  ──────────  │  ──────────  │     ────────        │
│  Nansen CLI │  Signal      │  BFS Graph   │     Hyperliquid     │
│  subprocess │  detection   │  Traversal   │     Perp Intel      │
│  wrapper    │  engine      │  & Clusters  │                     │
│  w/ retries │  (6 types)   │              │                     │
│             │              │              │                     │
├─────────────┴──────┬───────┴──────────────┴─────────────────────┤
│                    │                                            │
│   alerts.py        │        charts.py        reporter.py        │
│   ─────────        │        ──────────       ────────────       │
│   Rule engine      │        Plotly PNG       Markdown reports   │
│   w/ cooldowns     │        generation       (structured,       │
│   & history        │                         LLM-parseable)     │
│                    │                                            │
├────────────────────┴────────────────────────────────────────────┤
│                        config.py                                │
│          Chains · Thresholds · Severity · API Tracking          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   Nansen CLI     │
                    │   (subprocess)   │
                    │   v1.21.0+       │
                    └──────────────────┘
```

---

## Commands in Detail

### ⚡ Chain Sweep — `scan`

Scans all core smart money endpoints across your chosen chains in parallel:
- **Netflows** — where capital is moving (in/out by token)
- **DEX Trades** — what smart money is actively buying/selling
- **Holdings** — what positions smart money currently holds
- **Token Screener** — tokens gaining smart money attention

```bash
python nansenscope.py scan --chains ethereum,base,solana,arbitrum,bnb
```

![Chain Sweep](screenshots/screenshot_scan.png)

---

### 🕸️ Syndicate Hunter — `network`

**The killer feature.** Starting from a seed wallet, NansenScope uses BFS (breadth-first search) to expand through related wallets and counterparties, building a full network graph. It then:

- Detects **wallet clusters** (coordinated groups)
- Identifies **smart money nodes** within the network
- Finds **central nodes** (most connected wallets)
- Maps **counterparty relationships** by volume

```bash
python nansenscope.py network --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 \
  --chain ethereum --hops 2 --max-nodes 30
```

![Syndicate Hunter](screenshots/screenshot_network.png)

---

### 📊 Leverage Radar — `perps`

Taps into Hyperliquid perpetual trading data from Smart Money wallets:
- Long/short ratio and market sentiment
- Top tokens by perpetual volume
- Individual whale position tracking
- Signal detection on large leveraged bets

```bash
python nansenscope.py perps --limit 50
```

![Leverage Radar](screenshots/screenshot_perps.png)

---

### 🎯 Signal Fusion — `signals`

The signal engine runs 6 detector types across all scanned data, then cross-references for **convergence** — when multiple independent signals fire on the same token:

| Detector | What It Catches |
|----------|----------------|
| Netflow Signals | Large capital inflows/outflows, extreme imbalances |
| DEX Trade Signals | Whale trades, accumulation/distribution patterns |
| Holdings Signals | Significant position changes across SM wallets |
| Screener Signals | Tokens gaining unusual SM attention |
| Convergence | Multiple signal types on same token = high conviction |
| Cross-Chain | Same token accumulation across multiple chains |

Signals are scored 0–100 and ranked by severity (CRITICAL → HIGH → MEDIUM → LOW).

```bash
python nansenscope.py signals --chains ethereum,base --top 20
```

![Signal Fusion](screenshots/screenshot_signals.png)

---

### 🚨 Threat Matrix — `alerts`

Production-grade alert engine built on top of signals:
- **Rule-based** — configurable conditions per severity level
- **Cooldown management** — prevents alert fatigue with per-rule cooldowns
- **Deduplication** — same alert won't fire twice within cooldown window
- **Persistent history** — alert log stored as JSON for audit trail

```bash
python nansenscope.py alerts --chains ethereum,base,solana
```

---

### 🎨 Intel Canvas — `charts`

Auto-generates Plotly visualizations saved as PNG:
- Chain activity heatmaps
- Signal severity distribution
- Netflow comparison charts
- Bubble maps for multi-dimensional data

```bash
python nansenscope.py charts --chains ethereum,base,solana
```

![Intel Canvas](screenshots/screenshot_charts.png)

---

### 📋 Morning Brief — `daily`

The full pipeline in one command. Runs all 5 stages sequentially:

```
scan → signals → alerts → charts → report
```

```bash
python nansenscope.py daily --chains ethereum,base,solana,arbitrum,bnb
```

Outputs a timestamped daily report with everything: signals, alerts, charts, and API usage stats.

---

## Supported Chains

NansenScope supports all **18 chains** available in Nansen CLI v1.21.0:

| Core Chains | Extended Chains | |
|-------------|-----------------|---|
| Ethereum | Polygon | Ronin |
| Solana | Optimism | Sei |
| Base | Avalanche | Plasma |
| BNB | Linea | Sonic |
| Arbitrum | Scroll | Monad |
| | Mantle | HyperEVM |
| | | IOTA EVM |

Plus **Hyperliquid** for perpetual trading data.

---

## How It Works

```
                    ┌──────────────┐
                    │  Nansen CLI  │
                    │  18 chains   │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Netflows │ │DEX Trades│ │ Holdings │ ...
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             └──────┬─────┴────────────┘
                    ▼
         ┌─────────────────┐
         │ Signal Detection │ ← 6 detector types
         │ (signals.py)     │
         └────────┬────────┘
                  │
         ┌────────▼────────┐
         │  Convergence    │ ← cross-reference: same token,
         │  Detection      │   multiple signal types = alpha
         └────────┬────────┘
                  │
        ┌─────────┼──────────┐
        ▼         ▼          ▼
   ┌─────────┐ ┌───────┐ ┌────────┐
   │ Alerts  │ │Charts │ │Reports │
   │ Engine  │ │(PNG)  │ │ (.md)  │
   └─────────┘ └───────┘ └────────┘
```

**Data Flow:**
1. **Ingest** — `scanner.py` wraps `nansen` CLI calls via async subprocess with retry logic, rate-limit handling, and 402 payment detection
2. **Detect** — `signals.py` runs 6 detector types over raw data, scoring each signal 0–100
3. **Converge** — Cross-references signals: when netflows + DEX trades + holdings all point to the same token, conviction multiplies
4. **Alert** — `alerts.py` applies rules with cooldowns to prevent noise
5. **Visualize** — `charts.py` generates Plotly PNGs for visual analysis
6. **Report** — `reporter.py` compiles everything into structured markdown

**Resilience:**
- Exponential backoff on rate limits (429)
- Graceful handling of payment-required (402) and unauthorized (401)
- Per-call timeout protection (60s)
- API call tracking across entire session
- Up to 3 retries per endpoint with configurable delays

---

## x402 Payment Protocol

NansenScope gracefully handles Nansen CLI's x402 payment protocol. When an endpoint requires payment:
- The scanner detects 402 responses and logs them clearly
- No crash, no retry loop — just clean error reporting
- Configure your Nansen CLI wallet/auth for seamless paid access

---

## Configuration

All thresholds are tunable in `config.py`:

```python
@dataclass
class SignalThresholds:
    netflow_significant_usd: float = 1_000_000    # Flag netflows above $1M
    netflow_large_usd: float = 10_000_000          # Large netflows above $10M
    dex_trade_notable_usd: float = 100_000         # Notable DEX trades
    dex_trade_whale_usd: float = 1_000_000         # Whale-sized trades
    accumulation_ratio: float = 2.0                 # Buy/sell ratio for accumulation
    convergence_min_signals: int = 2                # Min signals for convergence
    # ... and more
```

---

## Project Structure

```
nansenscope/
├── nansenscope.py    # CLI entrypoint — 9 commands, Rich UI
├── scanner.py        # Nansen CLI wrapper — async, retries, rate limits
├── signals.py        # Signal detection — 6 detector types, scoring
├── network.py        # Wallet network — BFS traversal, cluster detection
├── perps.py          # Perp intelligence — Hyperliquid positions
├── charts.py         # Plotly visualizations — heatmaps, bubble maps
├── alerts.py         # Alert engine — rules, cooldowns, history
├── reporter.py       # Markdown report generator
├── config.py         # Chains, thresholds, severity, tracking
├── requirements.txt  # Dependencies
└── reports/          # Generated reports, charts, alert history
    └── charts/       # PNG chart output
```

---

## Built for #NansenCLI Challenge — Week 2

<p align="center">
  <img src="https://img.shields.io/badge/%23NansenCLI-Challenge_Week_2-blueviolet?style=for-the-badge" alt="NansenCLI Challenge Week 2" />
</p>

NansenScope was built specifically for the **Nansen CLI Developer Challenge Week 2** with a focus on:

- **Breadth** — 18 chains, 9 commands, 6 signal types, perpetual trading data
- **Depth** — Wallet network analysis with BFS graph traversal and cluster detection (no other entry has this)
- **Intelligence** — Not just data retrieval but signal detection, convergence analysis, and automated alerting
- **Production quality** — Async execution, rate-limit handling, exponential backoff, structured error handling
- **Developer experience** — Rich terminal UI, progress bars, colored tables, auto-generated reports

### What Makes NansenScope Different

Most challenge entries query Nansen data and display it. **NansenScope reasons about it.**

The **Syndicate Hunter** (network analysis) is the standout feature: starting from one wallet, it BFS-expands through Nansen's related-wallets and counterparty data to build a network graph, detect clusters of coordinated wallets, and identify the most influential nodes. This is the kind of analysis that hedge funds pay six figures for.

**Signal Fusion** (convergence detection) is the other differentiator: when netflow signals, DEX trade signals, and holdings signals independently point to the same token, that's not coincidence — that's alpha. NansenScope catches it automatically.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| CLI Framework | argparse + Rich |
| Data Source | Nansen CLI (subprocess) |
| Async | asyncio |
| Visualizations | Plotly |
| Reports | Structured Markdown |

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <b>NansenScope</b> — Stop reading data. Start reading signals.<br/>
  <sub>Built with conviction for the #NansenCLI Challenge</sub>
</p>
