#!/usr/bin/env bash
set -e

# NansenScope 60s demo runner (V1)
# Usage: bash scripts/demo_v1.sh

clear
echo "=== NansenScope Demo V1 ==="
echo "Landing: http://100.77.83.10:8090/?v=demo"
echo "Results: http://100.77.83.10:8090/results.html"
echo

echo "[1/5] Smart Money scan"
python3 nansenscope.py scan --chains ethereum,base,solana --top 8 || true
echo
echo "[2/5] Perps pressure"
python3 nansenscope.py perps || true
echo
echo "[3/5] Exit risk"
python3 nansenscope.py exit-signals --chains ethereum,base --top 8 || true
echo
echo "[4/5] Wallet DeFi exposure"
python3 nansenscope.py defi --address 0x0000000000000000000000000000000000000000 --chain ethereum || true
echo
echo "[5/5] Natural language search"
python3 nansenscope.py search "ethereum whale buying ONDO" --limit 5 || true

echo

echo "Demo sequence completed."
