# NansenScope

## Metadata

- **name:** nansenscope
- **version:** 0.2.0
- **description:** Autonomous Smart Money Intelligence Agent powered by Nansen CLI
- **author:** Luigi08001
- **tags:** nansen, smart-money, blockchain, intelligence, signals, crypto
- **requires:** nansen-cli, python3.11+

## Description

NansenScope is an autonomous agent that scans Nansen's smart money data across multiple blockchains, detects actionable signals through cross-referencing, and generates intelligence reports with visualizations.

It monitors:
- Smart money netflows, DEX trades, holdings, and token screener data
- Cross-chain convergence patterns (highest-conviction signals)
- Whale accumulation, distribution, and divergence patterns
- New token attention from smart money wallets

## Installation

```bash
# 1. Install Nansen CLI
npm install -g nansen-cli

# 2. Set up x402 payment (USDC on Base)
nansen wallet create
# Fund the wallet with USDC on Base network

# 3. Install Python dependencies
cd /path/to/nansenscope
pip install -r requirements.txt
```

## Usage

### One-Command Daily Pipeline
```bash
python nansenscope.py daily --chains ethereum,base,solana,arbitrum,bnb
```
This runs: scan -> signals -> alerts -> charts -> report

### Individual Commands
```bash
# Scan chains for smart money activity
python nansenscope.py scan --chains ethereum,base

# Detect and rank signals
python nansenscope.py signals --chains ethereum --top 20

# Run alert engine
python nansenscope.py alerts --chains ethereum,base,solana

# Generate visualizations
python nansenscope.py charts --chains ethereum,base

# Profile a specific wallet
python nansenscope.py profile --address 0x... --chain ethereum

# Full report
python nansenscope.py report --chains ethereum,base,solana
```

### Standalone Daily Scan Script (for cron)
```bash
python3 skill/scripts/daily_scan.py
```

## Cron Setup

Run a daily scan at 8:00 AM UTC:

```bash
# Add to crontab (crontab -e)
0 8 * * * cd /path/to/nansenscope && python3 skill/scripts/daily_scan.py >> reports/cron.log 2>&1
```

Or via OpenClaw:
```bash
openclaw cron add --name "nansenscope-daily" \
  --schedule "0 8 * * *" \
  --command "cd /path/to/nansenscope && python3 skill/scripts/daily_scan.py"
```

## Configuration

Thresholds can be adjusted in `config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `netflow_significant_usd` | $1M | Minimum netflow to flag |
| `netflow_large_usd` | $10M | Large netflow threshold |
| `dex_trade_whale_usd` | $1M | Whale trade threshold |
| `accumulation_ratio` | 2.0 | Buy/sell ratio for accumulation |
| `convergence_min_signals` | 2 | Min signal types for convergence |

## Outputs

- **Reports:** `reports/daily_YYYY-MM-DD_HHMM.md` — Markdown intelligence reports
- **Charts:** `reports/charts/*.png` — Flow heatmaps, signal timelines, chain comparisons, treemaps
- **Alerts:** `reports/alert_history.json` — Persistent alert history with cooldown tracking

## Architecture

```
nansenscope.py    CLI entry point (argparse + Rich)
  ├── scanner.py    Nansen CLI wrappers (async, retry, backoff)
  ├── signals.py    Signal detection (5 detectors + convergence)
  ├── alerts.py     Alert engine (5 rules, cooldowns, history)
  ├── charts.py     Plotly visualizations (4 chart types)
  ├── reporter.py   Markdown report generator
  └── config.py     Chains, thresholds, API tracking
```
