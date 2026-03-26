# NansenScope 🔬

**Autonomous Smart Money Intelligence Agent**

> Track what smart money does — before the market moves.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![Nansen CLI](https://img.shields.io/badge/nansen--cli-v1.21.0-green.svg)]()
[![Commands](https://img.shields.io/badge/commands-11-orange.svg)]()
[![Chains](https://img.shields.io/badge/chains-18-purple.svg)]()
[![License](https://img.shields.io/badge/license-MIT-brightgreen.svg)]()

[Live Demo](https://luigi08001.github.io/nansenscope/) · [Architecture](#architecture) · [Quick Start](#quick-start)

---

## What is NansenScope?

NansenScope is a CLI-powered intelligence platform that turns Nansen's raw blockchain data into actionable signals. It scans 18 chains, detects wallet clusters, tracks leveraged bets on Hyperliquid, identifies cross-chain convergence patterns, and alerts you — all autonomously.

**One command. Full intelligence pipeline.**

```bash
$ nansenscope daily --chains ethereum,base,solana,apechain
```

## Why NansenScope?

| Problem | NansenScope Solution |
|---|---|
| Smart money data is scattered across chains | **Chain Sweep** — parallel scanning across 18 blockchains |
| Hard to know if wallets are related | **Syndicate Hunter** — BFS graph traversal maps wallet clusters |
| Miss leveraged positions on Hyperliquid | **Leverage Radar** — real-time SM perp tracking |
| Same token moving on multiple chains | **Signal Fusion** — cross-chain convergence detection |
| Too much noise, missed alerts | **Threat Matrix** — 5 alert rules with cooldown engine |
| Manual daily research takes hours | **Morning Brief** — one command, full pipeline |

## Features

### 11 Commands

| Command | What it does |
|---|---|
| `scan` | Multi-chain smart money scanning. 18 chains, parallel async |
| `signals` | Cross-chain convergence detection. Score & rank |
| `alerts` | 5 built-in rules, cooldown engine, persistent history |
| `charts` | Plotly dark charts. Timeline + chain heatmap |
| `daily` | Full pipeline: scan → signals → alerts → charts → report |
| `network` | Wallet graph analysis via BFS. Clusters, centrality |
| `perps` | Hyperliquid perpetual positions. L/S ratios, SM traders |
| `profile` | Wallet deep dive. Holdings, labels |
| `portfolio` | Full portfolio analysis — holdings, labels, PnL breakdown |
| `watch` | Continuous monitoring — re-scans every N minutes, alerts on NEW signals |
| `quote` | DEX trade quotes via Nansen |

### Signal Detection Engine

5 signal detectors running in parallel:
1. **High Conviction Holding** — multiple SM wallets holding same token
2. **Netflow Surge** — unusual token netflow (>$1M threshold)
3. **DEX Trade Whale** — large DEX trades from labeled wallets
4. **Token Screener** — tokens attracting new SM attention
5. **Cross-Chain Convergence** — same token flagged on multiple chains = highest conviction

### Architecture

```
nansenscope.py          CLI entry point (argparse + Rich)
  ├── scanner.py        Nansen CLI wrappers (async, retry, backoff)
  ├── signals.py        Signal detection (5 detectors + convergence)
  ├── alerts.py         Alert engine (5 rules, cooldowns, history)
  ├── charts.py         Plotly visualizations (dark theme)
  ├── reporter.py       Markdown report generator
  ├── network.py        Wallet graph analysis (BFS, clusters)
  ├── perps.py          Hyperliquid perp intelligence
  └── config.py         Chains, thresholds, API tracking

skill/                  OpenClaw Agent Skill
  ├── SKILL.md          Skill manifest & documentation
  └── scripts/
      ├── daily_scan.py     Cron-ready daily pipeline
      ├── watch_scan.py     Single-cycle scanner with state dedup
      └── portfolio_check.py  Wallet change detection
```

### Stats

- **5,500+ lines of Python**
- **18 chains** supported (ethereum, solana, base, apechain, arbitrum, bnb, polygon, optimism, avalanche, linea, scroll, mantle, ronin, sei, plasma, sonic, monad, hyperevm, iotaevm)
- **11 CLI commands**
- **5 signal detectors** + convergence engine
- **5 alert rules** with persistent cooldowns
- **x402 micropayment** — no API key needed

## Quick Start

```bash
# 1. Install Nansen CLI
npm install -g nansen-cli

# 2. Create & fund x402 wallet (USDC on Base)
nansen wallet create

# 3. Clone NansenScope
git clone https://github.com/Luigi08001/nansenscope
cd nansenscope

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Run daily intelligence pipeline
python nansenscope.py daily --chains ethereum,base,solana

# 6. Start continuous monitoring
python nansenscope.py watch --chains ethereum,base,solana --interval 5
```

## Example Output

### Scan (real data)
```
$ nansenscope scan --chains ethereum,base,solana

Scanning 3 chains: ethereum, base, solana
✓ ethereum done (11s)
✓ base done (7s)
✓ solana done (4s)

                    Smart Money Signals
 #   Sev   Chain      Token    Type              Signal
 1   HIGH  ethereum   UNI      high_conviction   29 top traders ($144M)
 2   HIGH  ethereum   WLD      high_conviction   22 top traders ($60M)
 3   HIGH  ethereum   ONDO     high_conviction   19 top traders ($87M)
 4   HIGH  base       VIRTUAL  high_conviction   27 top traders ($757K)
 5   HIGH  solana     JUP      high_conviction   19 top traders ($2.7M)

API calls: 12 | Errors: 0 | Chains: 3
```

### Watch Mode (continuous monitoring)
```
$ nansenscope watch --chains ethereum,base --interval 5

━━━ Cycle 1 — 14:23:05 UTC ━━━
Scanned 2 chains | 15 total signals | 15 NEW

━━━ Cycle 2 — 14:28:07 UTC ━━━
Scanned 2 chains | 16 total signals | 1 NEW
  NEW: HIGH | base | VIRTUAL | high_conviction | 28 top traders ($812K)
```

### Network Analysis
```
$ nansenscope network --address <wallet> --chain ethereum --hops 2

Network: 12 nodes, 11 edges
Wallet Clusters: 2 detected

  Cluster #1: 8 wallets | $2.1M total PnL
  Cluster #0: 4 wallets | $450K total PnL
```

### Perps Intelligence
```
$ nansenscope perps

Positions: 50 | Volume: $208,111 | Traders: 5
L/S Ratio: 18.91 (strongly bullish)
```

## OpenClaw Integration

NansenScope ships as an OpenClaw Agent Skill for autonomous operation:

```bash
# Daily scan at 8:00 AM UTC
python3 skill/scripts/daily_scan.py --chains ethereum,base,solana --webhook <url>

# Watch mode — single cycle for cron
python3 skill/scripts/watch_scan.py --chains ethereum,base

# Portfolio monitoring
python3 skill/scripts/portfolio_check.py --threshold 10
```

## Configuration

Key thresholds in `config.py`:

| Parameter | Default | Description |
|---|---|---|
| `netflow_significant_usd` | $1M | Minimum netflow to flag |
| `screener_min_smart_holders` | 3 | Min SM holders to flag |
| `convergence_min_signals` | 2 | Min signals for convergence |
| `accumulation_ratio` | 2.0 | Buy/sell ratio threshold |

## Built With

- [Nansen CLI](https://agents.nansen.ai/) — onchain intelligence API
- [x402](https://www.x402.org/) — micropayment protocol (USDC on Base)
- [Rich](https://rich.readthedocs.io/) — terminal UI
- [Plotly](https://plotly.com/) — data visualization
- [OpenClaw](https://openclaw.ai/) — AI agent orchestration

## License

MIT

---

**Built for [#NansenCLI Challenge](https://agents.nansen.ai/) Week 2** by [@luigi08002](https://x.com/luigi08002)
