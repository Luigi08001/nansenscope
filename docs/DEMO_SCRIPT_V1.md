# NansenScope Demo Script V1 (60 sec)

## URLs (Air / Tailscale)
- Landing page: http://100.77.83.10:8090/?v=demo
- Results page: http://100.77.83.10:8090/results.html

## Voiceover (word-for-word)

Most submissions are one feature. NansenScope is a full onchain intelligence workflow from signal detection to verification.

First, we scan smart money activity across multiple chains and rank conviction in seconds.

Second, we move to perps to see where leverage is building and where pressure is strongest.

Third, we run exit-signals to catch distribution risk early, not just entry momentum.

Then we open the results viewer: CLI output is saved to JSON and rendered into an interactive visual dashboard.

Finally, we pivot to wallet-level analysis with DeFi positions and natural language search.

NansenScope turns noisy onchain data into an execution-ready loop: detect, verify, and monitor.

## Shot list (timeline)
- 0s–8s: landing page hero + architecture
- 8s–20s: `scan`
- 20s–30s: `perps`
- 30s–40s: `exit-signals`
- 40s–50s: `results.html` visual view
- 50s–60s: `defi` + `search` + close line

## Terminal sequence
Run:

```bash
cd ~/Desktop/Projets/nansenscope
bash scripts/demo_v1.sh
```

## Backup line (if API outage during recording)
"Live endpoints are currently rate-limited, so this segment replays the latest validated results from our last multi-chain run."
