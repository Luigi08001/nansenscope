---
name: nansenscope
description: >
  Autonomous Smart Money Intelligence Agent — scan 18 chains, detect whale
  movements, map wallet networks, track leveraged bets, get cross-chain
  convergence alerts. Built on Nansen CLI.
version: 1.0.0
license: MIT
requires:
  - nansen-cli >= 1.21.0
  - python >= 3.11
tags:
  - nansen
  - smart-money
  - blockchain
  - intelligence
  - signals
  - crypto
  - whale-tracking
---

# NansenScope

Autonomous Smart Money Intelligence Agent. Scans Nansen's smart money data
across 18 chains, detects actionable signals through cross-referencing, and
generates intelligence reports with visualizations.

## When to Use

| Need | Command |
|------|---------|
| Daily intelligence brief | `daily` |
| Real-time signal monitoring | `watch` or `scripts/watch_scan.py` |
| Investigate a specific wallet | `profile` |
| Check wallet holdings/PnL | `portfolio` |
| Map wallet relationships | `network` |
| Smart money perp positions | `perps` |
| Quick signal check | `signals` |
| Generate charts only | `charts` |
| Check alert rules | `alerts` |
| Full multi-chain scan | `scan` |

## Commands

All commands are run via `python nansenscope.py <command>`.

### scan — Multi-chain smart money scan

Scans netflows, DEX trades, holdings, and token screener data across chains.

```bash
# Default 5 chains
nansenscope scan

# Specific chains
nansenscope scan --chains ethereum,base,solana,arbitrum

# All 18 supported chains
nansenscope scan --all-chains

# Save to custom path
nansenscope scan --chains ethereum --output my_report.md
```

**Output:** Ranked signal table + saved markdown report in `reports/scan_*.md`

### signals — Detect and rank signals

Scans chains then runs signal detection (accumulation, distribution, whale trades, convergence).

```bash
nansenscope signals --chains ethereum,base --top 30
```

**Output:** Ranked signal table with severity, chain, token, type, and score.

### alerts — Run alert engine

Triggers alert rules with cooldown tracking. Persists history to `reports/alert_history.json`.

```bash
nansenscope alerts --chains ethereum,base,solana
```

**Output:** Table of triggered alerts with severity (CRIT/HIGH/MED/LOW) and summaries.

### charts — Generate visualizations

Creates Plotly charts: flow heatmaps, signal timelines, chain comparisons, treemaps.

```bash
nansenscope charts --chains ethereum,base
```

**Output:** PNG files in `reports/charts/`.

### daily — Full daily pipeline

Runs the complete pipeline: scan → signals → alerts → charts → report.

```bash
# Default chains
nansenscope daily

# Custom chains
nansenscope daily --chains ethereum,base,solana,arbitrum,bnb
```

**Output:** Complete intelligence report in `reports/daily_*.md` with embedded chart references.

### network — Wallet network analysis

Maps wallet relationships from seed addresses. Detects clusters, finds smart money nodes, generates bubble maps.

```bash
# Single seed
nansenscope network --address 0xabc123... --chain ethereum

# Multiple seeds, deeper scan
nansenscope network --address 0xabc... 0xdef... --chain base --hops 3 --max-nodes 50
```

**Output:** Network report with clusters, central nodes, and bubble map visualization.

### perps — Perpetual trading intelligence

Fetches smart money perpetual positions from Hyperliquid. Shows long/short ratios, top tokens, and leveraged signals.

```bash
nansenscope perps --limit 100
```

**Output:** Position summary, token volume table, perp signals, saved to `reports/perps_*.md`.

### profile — Wallet deep-dive

Profiles a single wallet: labels, balances, transaction history, PnL.

```bash
nansenscope profile --address 0xabc123... --chain ethereum --days 60
```

**Output:** Wallet profile report saved to `reports/profile_*.md`.

### portfolio — Wallet holdings

Shows token holdings, labels, and PnL for a specific wallet.

```bash
nansenscope portfolio --address 0xabc123... --chain ethereum --top 30
```

**Output:** Holdings table with token positions.

### watch — Continuous monitoring

Scans at regular intervals and alerts on new signals. For interactive terminal use.

```bash
# Scan every 5 minutes (default)
nansenscope watch --chains ethereum,base

# Custom interval + webhook
nansenscope watch --chains ethereum --interval 10 --webhook https://hooks.example.com/alerts
```

**Output:** Continuous stream of new signals to terminal (and optional webhook).

> For cron-based monitoring, use `scripts/watch_scan.py` instead — it runs one cycle and exits.

## Cron Scripts

### scripts/daily_scan.py — Scheduled daily pipeline

Full pipeline for cron or OpenClaw scheduling. Outputs markdown to stdout.

```bash
# Run with defaults (5 chains)
python3 skill/scripts/daily_scan.py

# Custom chains + webhook notification
python3 skill/scripts/daily_scan.py --chains ethereum,base,solana --webhook https://hooks.example.com/daily

# Verbose logging
python3 skill/scripts/daily_scan.py -v
```

OpenClaw cron:
```
openclaw cron add --name "nansenscope-daily" --schedule "0 8 * * *" \
  --command "cd ~/Desktop/Projets/nansenscope && python3 skill/scripts/daily_scan.py"
```

### scripts/watch_scan.py — Single-cycle signal monitor

Runs one scan, compares against previous state, reports only NEW signals. Designed for OpenClaw cron (not a loop).

```bash
python3 skill/scripts/watch_scan.py --chains ethereum,base --webhook https://hooks.example.com/watch
```

State file: `reports/watch_state.json` (auto-managed).

OpenClaw cron (every 5 minutes):
```
openclaw cron add --name "nansenscope-watch" --schedule "*/5 * * * *" \
  --command "cd ~/Desktop/Projets/nansenscope && python3 skill/scripts/watch_scan.py"
```

### scripts/portfolio_check.py — Wallet portfolio monitor

Checks tracked wallets for significant holding changes. Reads wallet list from `config/watched_wallets.json`.

```bash
python3 skill/scripts/portfolio_check.py
python3 skill/scripts/portfolio_check.py --wallets 0xabc...,0xdef... --chain base --threshold 15
```

## Configuration

Thresholds in `config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `netflow_significant_usd` | $1M | Minimum netflow to flag |
| `netflow_large_usd` | $10M | Large netflow threshold |
| `dex_trade_whale_usd` | $1M | Whale trade size |
| `dex_trade_notable_usd` | $100K | Notable trade size |
| `accumulation_ratio` | 2.0 | Buy/sell ratio for accumulation |
| `distribution_ratio` | 0.5 | Buy/sell ratio for distribution |
| `convergence_min_signals` | 2 | Min signal types for convergence |
| `screener_min_smart_holders` | 3 | Min smart money holders |
| `wallet_min_pnl_usd` | $50K | Min PnL for "successful" wallet |

Supported chains (18): ethereum, solana, base, bnb, arbitrum, polygon, optimism, avalanche, linea, scroll, mantle, ronin, sei, plasma, sonic, monad, hyperevm, iotaevm.

## Architecture

```
nansenscope.py     CLI entry point (argparse + Rich)
├── scanner.py     Nansen CLI wrappers (async, retry, backoff)
├── signals.py     Signal detection (5 detectors + convergence)
├── alerts.py      Alert engine (5 rules, cooldowns, history)
├── charts.py      Plotly visualizations (4 chart types)
├── reporter.py    Markdown report generator
├── network.py     Wallet network & cluster analysis
├── perps.py       Perpetual trading intelligence
├── config.py      Chains, thresholds, API tracking
└── skill/
    ├── SKILL.md           This file
    └── scripts/
        ├── daily_scan.py      Cron: full daily pipeline
        ├── watch_scan.py      Cron: single-cycle signal monitor
        └── portfolio_check.py Cron: wallet portfolio monitor
```

## Outputs

- **Reports:** `reports/daily_*.md`, `reports/scan_*.md`, `reports/perps_*.md`, etc.
- **Charts:** `reports/charts/*.png`
- **Alert history:** `reports/alert_history.json`
- **Watch state:** `reports/watch_state.json`
