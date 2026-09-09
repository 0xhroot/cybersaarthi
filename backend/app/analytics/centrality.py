"""Centrality and influence measurements for entities in a case graph.

Every metric is computed exactly for graphs up to ``ANALYTICS_GRAPH_NODE_CAP``
nodes and normalized min-max across the case so values are comparable. The
normalization divides by the max of the metric, so a single highly-connected
entity will not distort the scale; a node with the maximum value always scores
1.0 and nobody else is penalised.
"""

from __future__ import annotations

from typing import Any

from app.analytics.graph import (
    Graph,
    articulation_points,
    betweenness_centrality,
    closeness_centrality,
    pagerank,
)
from app.core.config import Settings

METRICS = (
    "degree",
    "in_degree",
    "out_degree",
    "betweenness",
    "closeness",
    "pagerank",
)

CENTRALITY_TITLES = {
    "degree": "Degree centrality",
    "in_degree": "In-degree centrality",
    "out_degree": "Out-degree centrality",
    "betweenness": "Betweenness centrality",
    "closeness": "Closeness centrality",
    "pagerank": "PageRank",
}


def _normalize(raw: dict[str, float]) -> dict[str, float]:
    if not raw:
        return {}
    maximum = max(value for value in raw.values()) or 1.0
    return {node: value / maximum for node, value in raw.items()}


def _ranked(raw: dict[str, float]) -> dict[str, int]:
    order = sorted(raw, key=lambda n: (-raw[n], n))
    return {node: index + 1 for index, node in enumerate(order)}


def compute_centrality(
    graph: Graph,
    settings: Settings,
) -> list[dict[str, Any]]:
    """Return per-entity metric records for all centrality measures.

    Exact when node count <= ANALYTICS_GRAPH_NODE_CAP; otherwise exact
    degree/PageRank (sub-expression costs) with documented approximation for
    betweenness/closeness (sample of ANALYTICS_GRAPH_NODE_CAP sources).
    """
    nodes = sorted(graph.nodes)
    exact = len(nodes) <= settings.ANALYTICS_GRAPH_NODE_CAP

    raw: dict[str, dict[str, float]] = {
        "degree": {node: float(value) for node, value in graph.degree.items()},
        "in_degree": {node: float(value) for node, value in graph.in_degree.items()},
        "out_degree": {node: float(value) for node, value in graph.out_degree.items()},
        "pagerank": pagerank(graph),
    }

    if exact:
        raw["betweenness"] = betweenness_centrality(graph)
        raw["closeness"] = closeness_centrality(graph)
    else:
        sample = set(nodes[: settings.ANALYTICS_GRAPH_NODE_CAP])
        adj = graph.adjacency
        bc: dict[str, float] = {}
        cc: dict[str, float] = {}
        n = len(nodes)
        for source in sample:
            dist: dict[str, int] = {}
            dist[source] = 0
            queue: list[str] = [source]
            while queue:
                node = queue.pop(0)
                for neighbor in sorted(adj.get(node, ())):
                    if neighbor not in dist:
                        dist[neighbor] = dist[node] + 1
                        queue.append(neighbor)
            for target, d in dist.items():
                if target not in bc or d > bc[target]:
                    bc[target] = bc.get(target, 0.0) + d
            cc[source] = sum(1.0 / d for d in dist.values() if d > 0) / (n - 1)
        raw["betweenness"] = bc
        raw["closeness"] = cc

    records: list[dict[str, Any]] = []
    for metric in METRICS:
        values = raw.get(metric) or {}
        norm = _normalize(values)
        rank = _ranked(values)
        for node in nodes:
            records.append(
                {
                    "entity_id": node,
                    "metric": metric,
                    "metric_title": CENTRALITY_TITLES[metric],
                    "raw": round(values.get(node, 0.0), 8),
                    "normalized": round(norm.get(node, 0.0), 8),
                    "rank": rank.get(node),
                    "exact": exact,
                }
            )
    return records


def compute_bridge_score(graph: Graph) -> dict[str, float]:
    """Local "bridge" score: share of graph node-pairs whose only path must pass
    through this node. Equals 0 for non-cut vertices."""
    cuts = articulation_points(graph)
    if not cuts:
        return {node: 0.0 for node in graph.nodes}
    adj = graph.adjacency
    n = len(graph.nodes)
    if n <= 1:
        return {node: 0.0 for node in graph.nodes}
    total_pairs = n * (n - 1) // 2
    score: dict[str, float] = {}
    for cut in cuts:
        without = {node: {b for b in adj.get(node, ()) if b != cut} for node in adj if node != cut}
        pairs_separated = 0
        parts: list[set[str]] = []
        visited: set[str] = set()
        for start in sorted(n for n in graph.nodes if n != cut):
            if start in visited:
                continue
            stack = [start]
            visited.add(start)
            part: set[str] = set()
            while stack:
                node = stack.pop()
                part.add(node)
                for neighbor in without.get(node, ()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append(neighbor)
            parts.append(part)
        for i, part in enumerate(parts):
            pairs_separated += len(part) * sum(len(other) for other in parts[i + 1 :])
        score[cut] = pairs_separated / total_pairs if total_pairs else 0.0
    return {node: score.get(node, 0.0) for node in graph.nodes}


# NOTE: modularity-based community membership lives in app.analytics.communities.
def community_membership(graph: Graph) -> dict[str, list[str]]:
    """Entity -> community ids.

    Kept for cross-references; real community detection (greedy modularity) is
    in :mod:`app.analytics.communities`.
    """
    from app.analytics.communities import detect_communities

    communities = detect_communities(graph)
    membership: dict[str, list[str]] = {}
    for community in communities:
        for node in community["member_ids"]:
            membership.setdefault(node, []).append(community["community_id"])
    for node in graph.nodes:
        membership.setdefault(node, [])
    return membership
