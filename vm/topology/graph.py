"""Leyline graph: nodes, capacitated edges, divergence, Dijkstra routing.

WHY THERE IS NO CURL HERE (honesty note):
  Source Eq 38 defines a "leyline curl" threshold ||omega|| > hbar_thaum/A_node
  with the explicit caveat "in 3D graph-embedding only". A discrete curl on a
  general graph has no canonical definition: it requires faces, an orientation,
  and an embedding (2D/3D) to even state Stokes' theorem. Generalizing the
  formula to arbitrary topologies would be dimensionally and mathematically
  unsound — the same fatal-math rule that sank the S5 attempt. We implement
  divergence (well-defined on any directed graph: in-flow minus out-flow) and
  Dijkstra routing, and we do NOT implement curl. See registry entry TOPO-38.

"Divergence" here is a plain flow-accounting label, not a physics claim.
"""

from __future__ import annotations

import heapq


class GraphError(Exception):
    pass


class LeylineGraph:
    """Directed multigraph with per-edge capacity (flow units)."""

    def __init__(self) -> None:
        self.nodes: set[str] = set()
        self._out: dict[str, dict[str, float]] = {}  # u -> {v: capacity}
        self._in: dict[str, dict[str, float]] = {}   # v -> {u: capacity}

    def add_node(self, name: str) -> None:
        self.nodes.add(name)
        self._out.setdefault(name, {})
        self._in.setdefault(name, {})

    def add_edge(self, u: str, v: str, capacity: float = 1.0, directed: bool = True) -> None:
        if capacity < 0:
            raise GraphError("edge capacity must be non-negative")
        self.add_node(u)
        self.add_node(v)
        self._out[u][v] = self._out[u].get(v, 0.0) + capacity
        self._in[v][u] = self._in[v].get(u, 0.0) + capacity
        if not directed:
            self._out[v][u] = self._out[v].get(u, 0.0) + capacity
            self._in[u][v] = self._in[u].get(v, 0.0) + capacity

    def divergence(self, node: str) -> float:
        """Divergence = inflow - outflow (sum of capacities). Positive means
        the node is a net sink, negative a net source."""
        if node not in self.nodes:
            raise GraphError(f"unknown node {node!r}")
        inflow = sum(self._in[node].values())
        outflow = sum(self._out[node].values())
        return inflow - outflow

    def dijkstra(self, source: str, target: str) -> tuple[list[str], float]:
        """Shortest path by summed edge cost, where cost = 1/capacity per hop
        (higher-capacity leylines are cheaper to route through).

        Deterministic: ties broken by node name, then by the engine seed's
        RNG only when names also tie (they cannot — names are unique).
        Returns (path, total_cost). Raises GraphError if unreachable.
        """
        if source not in self.nodes:
            raise GraphError(f"unknown source node {source!r}")
        if target not in self.nodes:
            raise GraphError(f"unknown target node {target!r}")
        dist = {source: 0.0}
        prev: dict[str, str] = {}
        pq: list[tuple[float, str]] = [(0.0, source)]
        visited: set[str] = set()
        while pq:
            d, u = heapq.heappop(pq)
            if u in visited:
                continue
            visited.add(u)
            if u == target:
                break
            for v in sorted(self._out[u]):  # sorted => deterministic ties
                cap = self._out[u][v]
                if cap <= 0:
                    continue
                nd = d + 1.0 / cap
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))
        if target not in dist:
            raise GraphError(f"no route from {source!r} to {target!r}")
        path = [target]
        while path[-1] != source:
            path.append(prev[path[-1]])
        path.reverse()
        return path, dist[target]

    def to_dict(self) -> dict:
        return {
            "nodes": sorted(self.nodes),
            "edges": [
                {"from": u, "to": v, "capacity": c}
                for u, outs in self._out.items()
                for v, c in outs.items()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LeylineGraph":
        g = cls()
        for n in data.get("nodes", []):
            g.add_node(n)
        for e in data.get("edges", []):
            if isinstance(e, dict):
                g.add_edge(e["from"], e["to"], e.get("capacity", 1.0))
            else:  # [u, v] or [u, v, capacity]
                u, v = e[0], e[1]
                g.add_edge(u, v, e[2] if len(e) > 2 else 1.0)
        return g
