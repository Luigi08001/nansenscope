# NansenScope

> **Autonomous Smart Money Intelligence Agent** | Nansen CLI Challenge Week 2

[![Nansen CLI Challenge](https://img.shields.io/badge/Nansen%20CLI-Challenge%20Week%202-blue)](https://docs.nansen.ai)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

NansenScope scans Nansen's smart money data across **18 blockchains**, detects actionable signals through cross-referencing, maps wallet networks, tracks perpetual trading sentiment, runs alert rules with cooldowns, generates visualizations, and produces intelligence reports — all from one command.

## What It Does

1. **18-chain scanning** — Queries netflows, DEX trades, holdings, and token screener across Ethereum, Base, Solana, Arbitrum, BNB, Polygon, Avalanche, Optimism, Fantom, Blast, Scroll, zkSync, Linea, Mantle, Sei, Sui, Aptos, and Ronin
2. **Signal detection** — Identifies accumulation, distribution, whale trades, position shifts, and convergence patterns
3. **Wallet network analysis** — BFS graph expansion from seed addresses, cluster detection, centrality scoring, cross-chain presence mapping, and fund flow tracing
4. **Perpetual trading intelligence** — Parses smart money perp trades from Hyperliquid, computes long/short ratios, detects consensus plays across multiple wallets
5. **Alert engine** — 5 built-in rules (whale accumulation, SM divergence, cross-chain flow, new token attention, convergence spike) with cooldowns and history
6. **Visualizations** — Flow heatmaps, signal timelines, chain comparison bars, holdings treemaps (Plotly → PNG)
7. **Reports** — Structured Markdown with executive summary, chart embedding, and API cost tracking
8. **Daily pipeline** — One command runs everything: `scan → signals → alerts → perps → charts → report`

## Architecture

```
nansenscope.py    CLI (9 commands, argparse + Rich)
  ├── scanner.py    Nansen CLI wrappers (20+ async endpoints, retry/backoff)
  ├── signals.py    Signal detection (5 detectors + convergence engine)
  ├── network.py    Wallet network/cluster analysis (BFS, centrality, flow tracing)
  ├── perps.py      Perpetual trading intelligence (Hyperliquid SM sentiment)
  ├── alerts.py     Alert engine (5 rules, cooldowns, JSON history)
  ├── charts.py     Plotly visualizations (4 chart types → PNG)
  ├── reporter.py   Markdown report generator (charts, alerts, cost tracking)
  ├── config.py     18 chains, thresholds, severity levels, API tracking
  └── skill/        OpenClaw skill package
      ├── SKILL.md
      └── scripts/daily_scan.py
```

```
                    ┌─────────────────────────────────────┐
                    │         nansenscope.py (CLI)         │
                    │  scan│profile│signals│alerts│charts  │
                    │            │daily│report             │
                    └─────────┬───────────────┬───────────┘
                              │               │
                 ┌────────────▼──┐    ┌───────▼────────┐
                 │  scanner.py   │    │   config.py    │
                 │ async Nansen  │    │  chains, thres │
                 │ CLI wrappers  │    │  API tracker   │
                 └──────┬────┬──┘    └────────────────┘
                        │    │
           ┌────────────▼┐  └──────────┐
           │ signals.py  │             │
           │ 5 detectors │      ┌──────▼──────┐
           │ convergence │      │  alerts.py  │
           └──────┬──────┘      │ 5 rules     │
                  │             │ cooldowns   │
           ┌──────▼──────┐     └─────────────┘
           │ reporter.py │
           │ MD reports  │──── charts.py (Plotly PNG)
           └─────────────┘
```

## Setup

### 1. Install Nansen CLI

```bash
npm install -g nansen-cli
```

### 2. Set Up x402 Payment (USDC on Base)

NansenScope uses [x402 micropayments](https://docs.nansen.ai) — no API key needed. Each CLI call is paid per-use with USDC on Base.

```bash
# Create a wallet
nansen wallet create

# Fund it with USDC on Base network
# Send USDC to the displayed wallet address on Base chain
# Minimum ~$5 USDC recommended for a full scan

# Verify wallet is set up
nansen wallet status
```

Alternatively, use an API key:
```bash
nansen login --api-key <your-key>
```

### 3. Install Python Dependencies

```bash
cd nansenscope
pip install -r requirements.txt
```

**Dependencies:** `rich`, `aiohttp`, `plotly`, `kaleido`

## Usage

### Daily Pipeline (The Killer Feature)

One command runs the full intelligence pipeline:

```bash
python nansenscope.py daily --chains ethereum,base,solana,arbitrum,bnb
```

This executes: **scan → signals → alerts → charts → report** and saves everything to `reports/`.

### Individual Commands

```bash
# Scan chains for smart money activity
python nansenscope.py scan --chains ethereum,base,solana

# Detect and rank signals
python nansenscope.py signals --chains ethereum --top 20

# Run alert engine (with cooldowns and history)
python nansenscope.py alerts --chains ethereum,base,solana

# Generate visualizations (PNG charts)
python nansenscope.py charts --chains ethereum,base

# Profile a specific wallet
python nansenscope.py profile --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 --chain ethereum

# Map wallet networks (the killer feature)
python nansenscope.py network --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 --chain ethereum --depth 2

# Smart money perpetual trading sentiment
python nansenscope.py perps --chains ethereum

# Generate a full intelligence report
python nansenscope.py report --chains ethereum,base,solana

# Verbose mode (debug logging)
python nansenscope.py -v daily --chains ethereum
```

### Cron / Automated Daily Scan

```bash
# Standalone script for cron (outputs markdown to stdout)
python3 skill/scripts/daily_scan.py --chains ethereum,base,solana

# Crontab: run daily at 8:00 AM UTC
# 0 8 * * * cd /path/to/nansenscope && python3 skill/scripts/daily_scan.py >> reports/cron.log 2>&1
```

## Signal Types

| Signal | Description | Severity |
|--------|-------------|----------|
| Convergence | Multiple signal types on same token | CRITICAL / HIGH |
| Large Netflow | Significant capital flow (>$10M) | HIGH |
| Whale Trade | Single trade >$1M | HIGH |
| Accumulation | Buy/sell ratio >2x from smart money | HIGH |
| Distribution | Sell/buy ratio >2x from smart money | HIGH |
| Screener Trending | Token with multiple SM holders | MEDIUM-HIGH |
| High Conviction | Many smart money wallets hold | MEDIUM |
| Position Shift | Holdings change >10% | MEDIUM |
| Notable Netflow | Capital flow >$1M | MEDIUM |

## Alert Rules

| Rule | Trigger | Severity | Cooldown |
|------|---------|----------|----------|
| whale_accumulation | SM buying across 2+ chains | CRITICAL | 60 min |
| convergence_spike | Convergence score >80 | CRITICAL | 30 min |
| smart_money_divergence | SM buying while price drops >5% | HIGH | 30 min |
| cross_chain_flow | Token flowing into multiple chains | HIGH | 45 min |
| new_token_attention | New token in SM holdings | MEDIUM | 120 min |

## Outputs

- **Reports:** `reports/daily_YYYY-MM-DD_HHMM.md` — Full Markdown intelligence reports
- **Charts:** `reports/charts/*.png` — Flow heatmaps, signal timelines, chain comparisons, treemaps
- **Alert History:** `reports/alert_history.json` — Persistent history with deduplication

### Sample Report Sections

```
# NansenScope — Smart Money Intelligence Report
## Executive Summary
  Market Snapshot: Bullish on ETH, USDC | Bearish on ...
  Top Alerts: CONVERGENCE on ethereum...
## Triggered Alerts
## High-Priority Signals
## ETHEREUM / BASE / SOLANA (per-chain breakdown)
## Visualizations (embedded charts)
## API Usage & Cost Tracking
```

## How Convergence Works

NansenScope's key insight: a single data point is noise, but multiple independent signals pointing at the same token is a pattern.

When the same token appears in:
- **Netflow data** (capital moving in)
- **DEX trades** (wallets actively buying)
- **Holdings** (positions being built)
- **Token screener** (gaining smart money attention)

...the engine flags it as a **convergence** — the highest-conviction signal it can produce.

## OpenClaw Skill

NansenScope ships as an OpenClaw skill for automated fleet integration:

```bash
# Install the skill
openclaw skill install ./skill

# Or reference directly in cron
openclaw cron add --name "nansenscope-daily" \
  --schedule "0 8 * * *" \
  --command "cd /path/to/nansenscope && python3 skill/scripts/daily_scan.py"
```

See `skill/SKILL.md` for full skill specification.

## Wallet Network Analysis (Killer Feature)

Most tools look at wallets in isolation. NansenScope maps the **network** around a wallet:

- **BFS expansion** — Starting from a seed address, discovers related wallets through counterparties and transactions (configurable depth)
- **Cluster detection** — Groups connected wallets into clusters using connected components analysis
- **Centrality scoring** — Identifies the most influential nodes (wallets that connect many others)
- **Fund flow tracing** — Traces how capital moves through a network of wallets across configurable hops
- **Cross-chain presence** — Scans all 18 chains to find where a wallet (or cluster) operates

This reveals coordinated activity that single-wallet analysis misses entirely.

## Perpetual Trading Intelligence

Tracks smart money perpetual futures activity on Hyperliquid:

- **Long/short ratio** — Aggregate positioning of smart money wallets per token
- **Consensus detection** — Flags when multiple independent SM wallets take the same directional bet
- **Sentiment scoring** — Bullish/bearish/neutral classification with confidence levels
- Real data: tested with live Nansen CLI calls, producing actionable directional signals

## Nansen CLI Commands Used

```bash
# Smart Money endpoints
nansen research smart-money netflow --chain <chain>
nansen research smart-money dex-trades --chain <chain>
nansen research smart-money holdings --chain <chain>
nansen research smart-money dcas --chain <chain>
nansen research smart-money perp-trades --chain <chain>

# Token analysis
nansen research token screener --chain <chain> --timeframe 24h

# Wallet profiling
nansen research profiler pnl-summary --address <addr> --chain <chain> --days 30
nansen research profiler counterparties --address <addr> --chain <chain>
nansen research profiler labels --address <addr> --chain <chain>
nansen research profiler balance --address <addr> --chain <chain>
nansen research profiler historical-holdings --address <addr> --chain <chain>
nansen research profiler historical-balances --address <addr> --chain <chain>
nansen research profiler transactions --address <addr> --chain <chain>
nansen research profiler related-wallets --address <addr> --chain <chain>
nansen research profiler pnl --address <addr> --chain <chain>
nansen research profiler portfolio --address <addr> --chain <chain>
nansen research profiler defi --address <addr> --chain <chain>

# Search
nansen search --query <term>
```

## License

MIT
