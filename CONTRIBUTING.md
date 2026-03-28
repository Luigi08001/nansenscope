# Contributing to NansenScope

Thanks for your interest! NansenScope is built for the Nansen CLI Challenge but contributions are welcome.

## Quick Start

```bash
git clone https://github.com/Luigi08001/nansenscope
cd nansenscope
pip install -r requirements.txt
python -m pytest tests/ -v  # should be 10/10
```

## Requirements

- Python 3.11+
- [Nansen CLI](https://agents.nansen.ai/) v1.21+ (`npm install -g nansen-cli`)
- A funded x402 wallet (USDC on Base) for live scans

## Development

```bash
make test       # run tests
make scan       # quick scan (ethereum + base)
make daily      # full pipeline
make dashboard  # open dashboard
```

## Code Style

- Type hints on all functions
- Docstrings on public functions
- `rich` for terminal output
- `logging` module (not print)
- Async where possible (scanner uses `asyncio`)

## Adding a New Command

1. Add the argparse parser in `nansenscope.py` (search `# ──`)
2. Write the `async def cmd_yourcommand(args)` handler
3. Wire it in the `COMMANDS` dict at the bottom
4. Add tests in `tests/`

## Adding a New Signal Detector

1. Add the detector function in `signals.py`
2. Wire it into `analyze_chain_data()`
3. Add test cases in `tests/test_signals.py`
