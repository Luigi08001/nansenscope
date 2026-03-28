# Changelog

## v2.0 — Week 2 Submission (2026-03-28)

### Added
- Interactive local dashboard (opens in browser after scan)
- Dashboard matches landing page aesthetic (dark navy + teal)
- 10 unit tests (config + signal engine)
- Example reports and charts in `examples/`
- Verifiability section in README (on-chain proof via Basescan)
- CI workflow (GitHub Actions, Python 3.11-3.13)
- Makefile for common tasks
- `--dashboard` flag on scan command
- Signal timeline redesigned as horizontal bar chart ranked by conviction
- Chain comparison now shows USD value, not just signal count

### Fixed
- AI agent logger (`log` not defined)
- AI agent kwarg (`cmd_args` → `args`)
- Signal detectors count: 6 → 5 (matched actual code)
- Command count: 19 → 18 (matched actual CLI)
- README stats aligned with codebase

### Changed
- Cleaned 25+ old video versions from docs/
- Landing page demo video updated to V15

## v1.0 — Week 1 (2026-03-21)

### Added
- 18 CLI commands (scan, profile, signals, report, alerts, charts, network, perps, watch, portfolio, quote, daily, analyze, exit-signals, defi, search, history, prediction)
- 5 signal detectors + cross-chain convergence engine
- 5 alert rules with cooldown engine
- Plotly chart generation (dark theme)
- Markdown report generator
- Wallet network analysis (BFS graph traversal)
- Hyperliquid perp intelligence
- Signal history persistence
- Watch mode (continuous monitoring)
- OpenClaw Agent Skill integration
- Landing page with demo video
- x402 micropayment support (no API key needed)
