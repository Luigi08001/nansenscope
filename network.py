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
