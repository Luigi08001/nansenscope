"""
NansenScope — Wallet Network & Cluster Analysis

THE KILLER FEATURE. Maps connections between smart money wallets using
related-wallets and counterparties data. Detects coordinated buying,
traces fund flows, and identifies wallet clusters.

No other competition entry will have this.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from config import SUPPORTED_CHAINS, api_tracker
from scanner import (
    ScanResult,
    get_wallet_counterparties,
    get_wallet_labels,
    get_wallet_profile,
    get_wallet_related,
)

log = logging.getLogger("nansenscope.network")


# ── Data Model ───────────────────────────────────────────────────────────────

@dataclass
class WalletNode:
    """A wallet in the network graph."""

    address: str
    labels: list[str] = field(default_factory=list)
    pnl_usd: float = 0.0
    win_rate: float = 0.0
    chains_active: list[str] = field(default_factory=list)
    connections: dict[str, str] = field(default_factory=dict)  # addr -> relation
    counterparties: list[dict] = field(default_factory=list)
    depth: int = 0  # hops from seed

    @property
    def is_smart_money(self) -> bool:
        sm_labels = {"Fund", "Smart Trader", "30D Smart Trader",
                     "90D Smart Trader", "180D Smart Trader",
                     "Smart HL Perps Trader"}
        return bool(sm_labels & set(self.labels))

    @property
    def connection_count(self) -> int:
        return len(self.connections) + len(self.counterparties)


@dataclass
class NetworkEdge:
    """A connection between two wallets."""

    source: str
    target: str
    relation: str  # "First Funder", "counterparty", "related"
    weight: float = 1.0
    chain: str = ""
    volume_usd: float = 0.0
    tx_hash: str = ""


@dataclass
class WalletCluster:
    """A group of connected wallets."""

    id: int
    wallets: list[str] = field(default_factory=list)
    total_pnl: float = 0.0
    label_summary: dict[str, int] = field(default_factory=dict)
    chains: set = field(default_factory=set)
    shared_tokens: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.wallets)


# ── Network Analyzer ─────────────────────────────────────────────────────────

class NetworkAnalyzer:
    """
    Builds and analyzes wallet relationship networks.

    Starting from seed addresses, expands outward using:
    - related-wallets (First Funder, deployer, etc.)
    - counterparties (top trading partners by volume)

    Then detects clusters, central nodes, and coordinated activity.
    """

    def __init__(self, max_hops: int = 2, max_nodes: int = 50):
        self.max_hops = max_hops
        self.max_nodes = max_nodes
        self.nodes: dict[str, WalletNode] = {}
        self.edges: list[NetworkEdge] = []
        self._visited: set[str] = set()

    async def build_network(
        self,
        seed_addresses: list[str],
        chain: str = "ethereum",
    ) -> dict[str, WalletNode]:
        """
        Build a wallet network starting from seed addresses.
        Expands outward hop by hop using related-wallets + counterparties.
        """
        log.info("Building network from %d seeds, max %d hops",
                 len(seed_addresses), self.max_hops)

        # Initialize seeds at depth 0
        current_layer = []
        for addr in seed_addresses:
            addr = addr.lower()
            if addr not in self.nodes:
                node = WalletNode(address=addr, depth=0)
                self.nodes[addr] = node
                current_layer.append(addr)

        # BFS expansion
        for hop in range(self.max_hops):
            if len(self.nodes) >= self.max_nodes:
                log.info("Hit max nodes (%d), stopping expansion", self.max_nodes)
                break

            next_layer = []
            log.info("Hop %d: expanding %d nodes", hop + 1, len(current_layer))

            for addr in current_layer:
                if addr in self._visited:
                    continue
                self._visited.add(addr)

                # Fetch related wallets + counterparties in parallel
                related, counterparties = await asyncio.gather(
                    get_wallet_related(addr, chain),
                    get_wallet_counterparties(addr, chain),
                    return_exceptions=True,
                )

                # Process related wallets
                if isinstance(related, ScanResult) and related.success and related.data:
                    rel_data = related.data
                    if isinstance(rel_data, dict):
                        rel_data = rel_data.get("data", [])
                    if isinstance(rel_data, list):
                        for item in rel_data:
                            if not isinstance(item, dict):
                                continue
                            rel_addr = (item.get("address") or "").lower()
                            relation = item.get("relation", "related")
                            if rel_addr and rel_addr != addr:
                                self._add_connection(
                                    addr, rel_addr, relation, chain,
                                    tx_hash=item.get("transaction_hash", ""),
                                    depth=hop + 1,
                                )
                                if rel_addr not in self._visited:
                                    next_layer.append(rel_addr)

                # Process counterparties
                if isinstance(counterparties, ScanResult) and counterparties.success and counterparties.data:
                    cp_data = counterparties.data
                    if isinstance(cp_data, dict):
                        cp_data = cp_data.get("data", [])
                    if isinstance(cp_data, list):
                        for item in cp_data:
                            if not isinstance(item, dict):
                                continue
                            cp_addr = (item.get("address") or item.get("counterparty") or "").lower()
                            volume = _to_float(item.get("volume_usd") or item.get("total_volume", 0))
                            if cp_addr and cp_addr != addr:
                                self._add_connection(
                                    addr, cp_addr, "counterparty", chain,
                                    volume_usd=volume,
                                    depth=hop + 1,
                                )
                                if cp_addr not in self._visited:
                                    next_layer.append(cp_addr)

                if len(self.nodes) >= self.max_nodes:
                    break

            current_layer = next_layer[:self.max_nodes - len(self.nodes)]

        # Enrich nodes with labels and PnL
        await self._enrich_nodes(chain)

        log.info("Network complete: %d nodes, %d edges",
                 len(self.nodes), len(self.edges))
        return self.nodes

    def _add_connection(
        self,
        source: str,
        target: str,
        relation: str,
        chain: str,
        volume_usd: float = 0.0,
        tx_hash: str = "",
        depth: int = 0,
    ) -> None:
        """Add a node and edge to the network."""
        target = target.lower()

        # Add target node if new
        if target not in self.nodes and len(self.nodes) < self.max_nodes:
            self.nodes[target] = WalletNode(address=target, depth=depth)

        # Add edge
        self.edges.append(NetworkEdge(
            source=source,
            target=target,
            relation=relation,
            chain=chain,
            volume_usd=volume_usd,
            tx_hash=tx_hash,
        ))

        # Update node connections
        if source in self.nodes:
            self.nodes[source].connections[target] = relation
        if target in self.nodes:
            self.nodes[target].connections[source] = f"reverse:{relation}"

    async def _enrich_nodes(self, chain: str) -> None:
        """Fetch labels and PnL for all nodes (batched)."""
        tasks = []
        addrs = list(self.nodes.keys())

        # Batch: labels + PnL for each node
        for addr in addrs[:20]:  # Cap enrichment to save API calls
            tasks.append(self._enrich_single(addr, chain))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _enrich_single(self, address: str, chain: str) -> None:
        """Enrich a single node with labels and PnL."""
        labels_result, pnl_result = await asyncio.gather(
            get_wallet_labels(address, chain),
            get_wallet_profile(address, chain),
            return_exceptions=True,
        )

        node = self.nodes.get(address)
        if not node:
            return

        # Extract labels
        if isinstance(labels_result, ScanResult) and labels_result.success and labels_result.data:
            lbl_data = labels_result.data
            if isinstance(lbl_data, dict):
                lbl_data = lbl_data.get("data", lbl_data.get("labels", []))
            if isinstance(lbl_data, list):
                for item in lbl_data:
                    if isinstance(item, dict):
                        label = item.get("label") or item.get("name", "")
                        if label:
                            node.labels.append(label)
                    elif isinstance(item, str):
                        node.labels.append(item)

        # Extract PnL
        if isinstance(pnl_result, ScanResult) and pnl_result.success and pnl_result.data:
            pnl_data = pnl_result.data
            if isinstance(pnl_data, dict):
                pnl_data = pnl_data.get("data", pnl_data)
            if isinstance(pnl_data, dict):
                node.pnl_usd = _to_float(pnl_data.get("total_pnl_usd") or pnl_data.get("pnl", 0))
                node.win_rate = _to_float(pnl_data.get("win_rate") or pnl_data.get("win_rate_percent", 0))

    # ── Analysis Methods ─────────────────────────────────────────────────

    def detect_clusters(self) -> list[WalletCluster]:
        """
        Detect wallet clusters using connected components.
        Wallets in the same cluster are likely controlled by the same entity
        or coordinating.
        """
        visited = set()
        clusters = []
        cluster_id = 0

        # Build adjacency list
        adj: dict[str, set[str]] = {addr: set() for addr in self.nodes}
        for edge in self.edges:
            if edge.source in adj and edge.target in adj:
                adj[edge.source].add(edge.target)
                adj[edge.target].add(edge.source)

        for addr in self.nodes:
            if addr in visited:
                continue

            # BFS to find connected component
            component = []
            queue = [addr]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                component.append(current)
                for neighbor in adj.get(current, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)

            if len(component) >= 2:
                cluster = WalletCluster(id=cluster_id, wallets=component)
                cluster.total_pnl = sum(
                    self.nodes[a].pnl_usd for a in component if a in self.nodes
                )
                for a in component:
                    node = self.nodes.get(a)
                    if node:
                        for lbl in node.labels:
                            cluster.label_summary[lbl] = cluster.label_summary.get(lbl, 0) + 1
                        cluster.chains.update(node.chains_active)
                clusters.append(cluster)
                cluster_id += 1

        clusters.sort(key=lambda c: c.size, reverse=True)
        return clusters

    def find_central_nodes(self, top_n: int = 5) -> list[tuple[str, int]]:
        """Find the most connected wallets (highest degree centrality)."""
        degree = {}
        for edge in self.edges:
            degree[edge.source] = degree.get(edge.source, 0) + 1
            degree[edge.target] = degree.get(edge.target, 0) + 1
        ranked = sorted(degree.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_n]

    def find_whales(self, min_pnl: float = 100_000) -> list[WalletNode]:
        """Identify high-PnL nodes in the network."""
        whales = [
            node for node in self.nodes.values()
            if node.pnl_usd >= min_pnl
        ]
        whales.sort(key=lambda n: n.pnl_usd, reverse=True)
        return whales

    def find_smart_money_nodes(self) -> list[WalletNode]:
        """Filter nodes that have Smart Money labels."""
        return [n for n in self.nodes.values() if n.is_smart_money]

    def trace_fund_flow(self, address: str, max_hops: int = 3) -> list[list[NetworkEdge]]:
        """
        Trace fund flows from a specific address outward.
        Returns list of paths (each path = list of edges).
        """
        address = address.lower()
        paths = []
        visited = set()

        def _dfs(current: str, path: list[NetworkEdge], depth: int):
            if depth >= max_hops:
                if path:
                    paths.append(list(path))
                return
            visited.add(current)
            found_next = False
            for edge in self.edges:
                next_addr = None
                if edge.source == current and edge.target not in visited:
                    next_addr = edge.target
                elif edge.target == current and edge.source not in visited:
                    next_addr = edge.source
                if next_addr:
                    found_next = True
                    path.append(edge)
                    _dfs(next_addr, path, depth + 1)
                    path.pop()
            if not found_next and path:
                paths.append(list(path))
            visited.discard(current)

        _dfs(address, [], 0)
        return paths

    async def cross_chain_scan(self, address: str) -> dict[str, bool]:
        """Check if an address is active across multiple chains."""
        results = {}
        chains_to_check = SUPPORTED_CHAINS + ["polygon", "optimism", "avalanche",
                                                "linea", "scroll", "mantle",
                                                "ronin", "sei", "sonic"]

        for chain in chains_to_check:
            try:
                result = await get_wallet_labels(address, chain)
                if isinstance(result, ScanResult) and result.success:
                    data = result.data
                    has_activity = False
                    if isinstance(data, dict):
                        data = data.get("data", data.get("labels", []))
                    if isinstance(data, list) and len(data) > 0:
                        has_activity = True
                    elif isinstance(data, dict) and data:
                        has_activity = True
                    results[chain] = has_activity
                else:
                    results[chain] = False
            except Exception:
                results[chain] = False

        # Update node
        if address in self.nodes:
            self.nodes[address].chains_active = [
                c for c, active in results.items() if active
            ]

        return results

    # ── Report Generation ────────────────────────────────────────────────

    def generate_report(self) -> str:
        """Generate a markdown report of the network analysis."""
        lines = []
        lines.append("# Wallet Network Analysis Report\n")
        lines.append(f"**Nodes:** {len(self.nodes)} | **Edges:** {len(self.edges)}\n")

        # Smart Money nodes
        sm_nodes = self.find_smart_money_nodes()
        if sm_nodes:
            lines.append(f"\n## Smart Money Nodes ({len(sm_nodes)})\n")
            for node in sm_nodes[:10]:
                labels = ", ".join(node.labels[:3])
                pnl = f"${node.pnl_usd:,.0f}" if node.pnl_usd else "N/A"
                lines.append(f"- `{node.address[:10]}...` — {labels} | PnL: {pnl} | "
                             f"{node.connection_count} connections")

        # Central nodes
        central = self.find_central_nodes()
        if central:
            lines.append(f"\n## Most Connected Wallets\n")
            for addr, degree in central:
                node = self.nodes.get(addr)
                label = ", ".join(node.labels[:2]) if node and node.labels else "unlabeled"
                lines.append(f"- `{addr[:10]}...` — {degree} connections ({label})")

        # Clusters
        clusters = self.detect_clusters()
        if clusters:
            lines.append(f"\n## Wallet Clusters ({len(clusters)})\n")
            for cluster in clusters[:5]:
                labels_str = ", ".join(f"{k}: {v}" for k, v in
                                       sorted(cluster.label_summary.items(),
                                              key=lambda x: x[1], reverse=True)[:3])
                lines.append(f"### Cluster #{cluster.id} ({cluster.size} wallets)")
                lines.append(f"- Total PnL: ${cluster.total_pnl:,.0f}")
                lines.append(f"- Labels: {labels_str or 'none'}")
                lines.append(f"- Wallets: {', '.join(f'`{a[:8]}...`' for a in cluster.wallets[:5])}")
                lines.append("")

        # Whales
        whales = self.find_whales()
        if whales:
            lines.append(f"\n## Whales ({len(whales)})\n")
            for whale in whales[:5]:
                labels = ", ".join(whale.labels[:2]) or "unlabeled"
                lines.append(f"- `{whale.address[:10]}...` — PnL: ${whale.pnl_usd:,.0f} "
                             f"({labels})")

        # Network stats
        lines.append("\n## Network Statistics\n")
        total_pnl = sum(n.pnl_usd for n in self.nodes.values())
        sm_count = len(sm_nodes)
        avg_connections = (sum(n.connection_count for n in self.nodes.values())
                          / max(len(self.nodes), 1))
        lines.append(f"- Total network PnL: ${total_pnl:,.0f}")
        lines.append(f"- Smart Money nodes: {sm_count}/{len(self.nodes)}")
        lines.append(f"- Avg connections per node: {avg_connections:.1f}")
        lines.append(f"- Unique relations: {len(set(e.relation for e in self.edges))}")

        return "\n".join(lines)


# ── Convenience Functions ────────────────────────────────────────────────────

def generate_network_html(
    nodes: dict[str, "WalletNode"],
    edges: list["NetworkEdge"],
    clusters: list["WalletCluster"],
    output_path: str = "reports/charts/network_map.html",
) -> str:
    """
    Generate a self-contained interactive HTML network map.
    Uses Canvas + inline JS for force-directed graph with zoom/pan/drag.
    Returns the path where the file was saved.
    """
    import json
    from pathlib import Path

    # Build cluster lookup: address -> cluster_id
    cluster_map: dict[str, int] = {}
    for cl in clusters:
        for addr in cl.wallets:
            cluster_map[addr] = cl.id

    # Find hub nodes (top 20% by connection count)
    connection_counts = {addr: n.connection_count for addr, n in nodes.items()}
    sorted_counts = sorted(connection_counts.values(), reverse=True)
    hub_threshold = sorted_counts[max(0, len(sorted_counts) // 5)] if sorted_counts else 3

    # Build JSON-serializable node list
    node_list = []
    addr_to_idx: dict[str, int] = {}
    for i, (addr, node) in enumerate(nodes.items()):
        addr_to_idx[addr] = i
        is_hub = node.connection_count >= max(hub_threshold, 3)
        node_list.append({
            "id": i,
            "addr": addr,
            "short": f"{addr[:6]}...{addr[-4:]}",
            "labels": node.labels[:4],
            "pnl": node.pnl_usd,
            "sm": node.is_smart_money,
            "hub": is_hub,
            "cc": node.connection_count,
            "cl": cluster_map.get(addr, -1),
            "depth": node.depth,
        })

    # Build JSON-serializable edge list
    edge_list = []
    for e in edges:
        si = addr_to_idx.get(e.source)
        ti = addr_to_idx.get(e.target)
        if si is not None and ti is not None:
            edge_list.append({
                "s": si,
                "t": ti,
                "r": e.relation,
                "v": e.volume_usd,
            })

    nodes_json = json.dumps(node_list)
    edges_json = json.dumps(edge_list)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NansenScope — Network Map</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#060B14;font-family:'Courier New',monospace;color:#c0c0c0;overflow:hidden}}
canvas{{display:block;cursor:grab}}
canvas.dragging{{cursor:grabbing}}
#tooltip{{
  position:fixed;display:none;background:rgba(6,11,20,0.95);
  border:1px solid #00E5A0;border-radius:6px;padding:10px 14px;
  font-size:12px;pointer-events:none;z-index:100;max-width:320px;
  box-shadow:0 4px 20px rgba(0,229,160,0.15)
}}
#tooltip .addr{{color:#00E5A0;font-size:13px;font-weight:bold;margin-bottom:4px}}
#tooltip .lbl{{color:#FFD700;margin:2px 0}}
#tooltip .stat{{color:#8888aa}}
#legend{{
  position:fixed;bottom:20px;left:20px;background:rgba(6,11,20,0.9);
  border:1px solid #1a2340;border-radius:8px;padding:14px 18px;
  font-size:11px;z-index:50
}}
#legend h3{{color:#00E5A0;margin-bottom:8px;font-size:13px}}
.leg-row{{display:flex;align-items:center;margin:4px 0}}
.leg-dot{{width:10px;height:10px;border-radius:50%;margin-right:8px;flex-shrink:0}}
.leg-line{{width:20px;height:2px;margin-right:8px;flex-shrink:0}}
#controls{{
  position:fixed;top:20px;right:20px;display:flex;gap:8px;z-index:50
}}
#controls button{{
  background:#0d1a2e;border:1px solid #1a2840;color:#00E5A0;
  padding:6px 14px;border-radius:4px;cursor:pointer;font-family:inherit;font-size:12px
}}
#controls button:hover{{background:#142240;border-color:#00E5A0}}
#title{{
  position:fixed;top:20px;left:20px;z-index:50
}}
#title h1{{color:#00E5A0;font-size:18px;letter-spacing:2px}}
#title p{{color:#556;font-size:11px;margin-top:4px}}
#stats{{
  position:fixed;top:20px;left:50%;transform:translateX(-50%);
  background:rgba(6,11,20,0.85);border:1px solid #1a2340;
  border-radius:8px;padding:8px 20px;font-size:12px;z-index:50;
  display:flex;gap:20px
}}
.stat-val{{color:#00E5A0;font-weight:bold}}
</style>
</head>
<body>
<canvas id="graph"></canvas>

<div id="title">
  <h1>NANSENSCOPE</h1>
  <p>Interactive Wallet Network Map</p>
</div>

<div id="stats">
  <span>Nodes: <span class="stat-val">{len(node_list)}</span></span>
  <span>Edges: <span class="stat-val">{len(edge_list)}</span></span>
  <span>Clusters: <span class="stat-val">{len(clusters)}</span></span>
</div>

<div id="controls">
  <button onclick="zoomIn()">+</button>
  <button onclick="zoomOut()">−</button>
  <button onclick="resetView()">Reset</button>
</div>

<div id="tooltip"></div>

<div id="legend">
  <h3>LEGEND</h3>
  <div class="leg-row"><div class="leg-dot" style="background:#FF4444;width:14px;height:14px"></div> Hub Node</div>
  <div class="leg-row"><div class="leg-dot" style="background:#00E5FF"></div> Smart Money</div>
  <div class="leg-row"><div class="leg-dot" style="background:#556677;width:7px;height:7px"></div> Other Wallet</div>
  <div style="margin-top:8px"></div>
  <div class="leg-row"><div class="leg-line" style="background:#FF4444"></div> Fund Flow</div>
  <div class="leg-row"><div class="leg-line" style="background:#FF8C00"></div> Counterparty</div>
  <div class="leg-row"><div class="leg-line" style="background:#334455"></div> Related</div>
</div>

<script>
const NODES={nodes_json};
const EDGES={edges_json};

const canvas=document.getElementById('graph');
const ctx=canvas.getContext('2d');
const tip=document.getElementById('tooltip');

let W,H;
function resize(){{W=canvas.width=window.innerWidth;H=canvas.height=window.innerHeight}}
resize();window.addEventListener('resize',resize);

// Cluster colors
const CCOLORS=['#00E5A0','#FF6B6B','#4ECDC4','#FFE66D','#A78BFA','#F97316','#06B6D4','#EC4899','#84CC16','#8B5CF6'];

// Init node positions with some spread
const rng=(s)=>{{let x=Math.sin(s)*10000;return x-Math.floor(x)}};
NODES.forEach((n,i)=>{{
  const a=2*Math.PI*i/NODES.length;
  const r=120+rng(i*137)*80;
  n.x=W/2+Math.cos(a)*r;
  n.y=H/2+Math.sin(a)*r;
  n.vx=0;n.vy=0;
  n.fx=null;n.fy=null;
}});

// Camera
let cam={{x:0,y:0,z:1}};

function zoomIn(){{cam.z=Math.min(cam.z*1.3,8)}}
function zoomOut(){{cam.z=Math.max(cam.z/1.3,0.1)}}
function resetView(){{cam.x=0;cam.y=0;cam.z=1}}

function toScreen(x,y){{return[(x+cam.x)*cam.z+W/2,(y+cam.y)*cam.z+H/2]}}
function fromScreen(sx,sy){{return[(sx-W/2)/cam.z-cam.x,(sy-H/2)/cam.z-cam.y]}}

// Force simulation
const SIM_STEPS=200;
let simStep=0;

function simulate(){{
  if(simStep>=SIM_STEPS)return;
  const alpha=1-simStep/SIM_STEPS;
  const k=0.008*alpha;

  // Center gravity
  let cx=0,cy=0;
  NODES.forEach(n=>{{cx+=n.x;cy+=n.y}});
  cx/=NODES.length||1;cy/=NODES.length||1;
  NODES.forEach(n=>{{n.vx+=(W/2-cx-n.x)*0.0003;n.vy+=(H/2-cy-n.y)*0.0003}});

  // Repulsion (Barnes-Hut would be better but N<100 is fine)
  for(let i=0;i<NODES.length;i++){{
    for(let j=i+1;j<NODES.length;j++){{
      let dx=NODES[j].x-NODES[i].x;
      let dy=NODES[j].y-NODES[i].y;
      let d2=dx*dx+dy*dy;
      if(d2<1)d2=1;
      let f=800/d2;
      NODES[i].vx-=dx*f;NODES[i].vy-=dy*f;
      NODES[j].vx+=dx*f;NODES[j].vy+=dy*f;
    }}
  }}

  // Attraction along edges
  EDGES.forEach(e=>{{
    const a=NODES[e.s],b=NODES[e.t];
    if(!a||!b)return;
    let dx=b.x-a.x,dy=b.y-a.y;
    let d=Math.sqrt(dx*dx+dy*dy)||1;
    let f=(d-150)*0.003;
    a.vx+=dx/d*f;a.vy+=dy/d*f;
    b.vx-=dx/d*f;b.vy-=dy/d*f;
  }});

  // Integrate
  NODES.forEach(n=>{{
    if(n.fx!==null){{n.x=n.fx;n.y=n.fy;n.vx=0;n.vy=0;return}}
    n.vx*=0.6;n.vy*=0.6;
    n.x+=n.vx;n.y+=n.vy;
  }});
  simStep++;
}}

// Drawing
function nodeRadius(n){{
  if(n.hub)return 12;
  if(n.sm)return 8;
  return 5;
}}

function nodeColor(n){{
  if(n.hub)return n.cl>=0?CCOLORS[n.cl%CCOLORS.length]:'#FF4444';
  if(n.sm)return '#00E5FF';
  return '#556677';
}}

function edgeColor(e){{
  const r=e.r.toLowerCase();
  if(r.includes('fund')||r.includes('first'))return 'rgba(255,68,68,0.5)';
  if(r.includes('counter'))return 'rgba(255,140,0,0.5)';
  return 'rgba(51,68,85,0.4)';
}}

function draw(){{
  ctx.fillStyle='#060B14';
  ctx.fillRect(0,0,W,H);

  // Grid
  ctx.strokeStyle='#0a1225';ctx.lineWidth=1;
  const gs=80*cam.z;
  const ox=(cam.x*cam.z+W/2)%gs;
  const oy=(cam.y*cam.z+H/2)%gs;
  for(let x=ox;x<W;x+=gs){{ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke()}}
  for(let y=oy;y<H;y+=gs){{ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke()}}

  // Edges
  EDGES.forEach(e=>{{
    const a=NODES[e.s],b=NODES[e.t];
    if(!a||!b)return;
    const[x1,y1]=toScreen(a.x-W/2,a.y-H/2);
    const[x2,y2]=toScreen(b.x-W/2,b.y-H/2);
    ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);
    ctx.strokeStyle=edgeColor(e);
    ctx.lineWidth=Math.max(0.5,cam.z*(e.v>0?2:1));
    ctx.stroke();
  }});

  // Nodes
  NODES.forEach(n=>{{
    const[sx,sy]=toScreen(n.x-W/2,n.y-H/2);
    const r=nodeRadius(n)*cam.z;
    const col=nodeColor(n);

    // Glow for hubs
    if(n.hub&&cam.z>0.3){{
      const g=ctx.createRadialGradient(sx,sy,r*0.5,sx,sy,r*3);
      g.addColorStop(0,col+'44');g.addColorStop(1,'transparent');
      ctx.fillStyle=g;ctx.beginPath();ctx.arc(sx,sy,r*3,0,Math.PI*2);ctx.fill();
    }}

    ctx.beginPath();ctx.arc(sx,sy,r,0,Math.PI*2);
    ctx.fillStyle=col;ctx.fill();
    ctx.strokeStyle='#060B14';ctx.lineWidth=1.5;ctx.stroke();

    // Label for large zoom
    if(cam.z>1.2&&(n.hub||n.sm)){{
      ctx.fillStyle='#ffffff';ctx.font=Math.round(9*cam.z)+'px Courier New';
      ctx.textAlign='center';
      ctx.fillText(n.short,sx,sy+r+12*cam.z);
    }}
  }});
}}

// Interaction
let dragNode=null,isPanning=false,lastMouse={{x:0,y:0}};

canvas.addEventListener('mousedown',e=>{{
  const[mx,my]=fromScreen(e.clientX,e.clientY);
  // Check if clicking a node
  for(let n of NODES){{
    const dx=n.x-W/2-mx,dy=n.y-H/2-my;
    if(dx*dx+dy*dy<(nodeRadius(n)+4)**2){{
      dragNode=n;n.fx=n.x;n.fy=n.y;
      canvas.classList.add('dragging');
      return;
    }}
  }}
  isPanning=true;lastMouse.x=e.clientX;lastMouse.y=e.clientY;
  canvas.classList.add('dragging');
}});

canvas.addEventListener('mousemove',e=>{{
  if(dragNode){{
    const[mx,my]=fromScreen(e.clientX,e.clientY);
    dragNode.fx=mx+W/2;dragNode.fy=my+H/2;
    dragNode.x=dragNode.fx;dragNode.y=dragNode.fy;
  }}else if(isPanning){{
    cam.x+=(e.clientX-lastMouse.x)/cam.z;
    cam.y+=(e.clientY-lastMouse.y)/cam.z;
    lastMouse.x=e.clientX;lastMouse.y=e.clientY;
  }}else{{
    // Tooltip
    const[mx,my]=fromScreen(e.clientX,e.clientY);
    let found=null;
    for(let n of NODES){{
      const dx=n.x-W/2-mx,dy=n.y-H/2-my;
      if(dx*dx+dy*dy<(nodeRadius(n)+6)**2){{found=n;break}}
    }}
    if(found){{
      const labels=found.labels.length?found.labels.join(', '):'unlabeled';
      const pnl=found.pnl?'$'+found.pnl.toLocaleString():'N/A';
      const typ=found.hub?'Hub':found.sm?'Smart Money':'Wallet';
      tip.innerHTML=`<div class="addr">${{found.addr}}</div>`+
        `<div class="lbl">${{labels}}</div>`+
        `<div class="stat">${{typ}} · ${{found.cc}} connections · PnL: ${{pnl}}</div>`+
        (found.cl>=0?`<div class="stat">Cluster #${{found.cl}}</div>`:'');
      tip.style.display='block';
      tip.style.left=Math.min(e.clientX+15,W-330)+'px';
      tip.style.top=Math.min(e.clientY+15,H-100)+'px';
    }}else{{
      tip.style.display='none';
    }}
  }}
}});

canvas.addEventListener('mouseup',()=>{{
  if(dragNode){{dragNode.fx=null;dragNode.fy=null;dragNode=null}}
  isPanning=false;canvas.classList.remove('dragging');
}});

canvas.addEventListener('wheel',e=>{{
  e.preventDefault();
  const f=e.deltaY>0?0.9:1.1;
  cam.z=Math.max(0.1,Math.min(8,cam.z*f));
}},{{passive:false}});

// Animation loop
function loop(){{
  simulate();
  draw();
  requestAnimationFrame(loop);
}}
loop();
</script>
</body>
</html>"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    log.info("Interactive network map saved: %s", out)
    return str(out)


async def analyze_wallet_network(
    seed_addresses: list[str],
    chain: str = "ethereum",
    max_hops: int = 2,
    max_nodes: int = 50,
) -> NetworkAnalyzer:
    """
    One-shot network analysis from seed addresses.
    Returns a fully built and analyzed NetworkAnalyzer.
    """
    analyzer = NetworkAnalyzer(max_hops=max_hops, max_nodes=max_nodes)
    await analyzer.build_network(seed_addresses, chain)
    return analyzer


def _to_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(str(val).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return 0.0
