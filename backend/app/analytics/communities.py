"""Deterministic community detection and per-community statistics.

Uses a greedy modularity optimisation: communities are merged along edges that
strictly improve modularity, iterated over edges in sorted order until a pass
makes no move.  The result is deterministic for a given graph because iteration
order is fixed.  Density, internal/external edges and dominant types are then
computed per community from the raw relationships.

Modularity gain of merging communities C and D with m = |E|:
    dQ(C, D) = e_CD / m  -  (deg_C * deg_D) / (2 * m^2)

``quality_threshold`` is the minimum gain required to accept a merge. The
default of 0.0 keeps the standard "merge while modularity improves" behaviour;
a small epsilon guards against floating-point noise. Raising the threshold
yields coarser communities.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from app.analytics.graph import Graph

_MIN_GUARD = 1e-9


def _modularity_gain(
    m: int,
    e_cd: int,
    deg_c: int,
    deg_d: int,
) -> float:
    if m == 0:
        return 0.0
    return e_cd / m - (deg_c * deg_d) / (2.0 * m * m)


def detect_communities(
    graph: Graph,
    quality_threshold: float = 0.0,
) -> list[dict[str, Any]]:
    """Return community records with members, sizes and computed statistics.

    Only nodes with at least one edge are grouped (isolated nodes get their
    own singleton community).
    """
    parent: dict[str, str] = {node: node for node in graph.nodes}
    degree_sum: dict[str, int] = {node: 0 for node in graph.nodes}
    for node in graph.nodes:
        degree_sum[node] = len(graph.adjacency.get(node, ()))

    m = len(graph.edges)

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def internal_edges(component: set[str]) -> int:
        return sum(1 for edge in graph.edges if edge.a in component and edge.b in component)

    def edge_connections(c: set[str], d: set[str]) -> int:
        return sum(
            1
            for edge in graph.edges
            if (edge.a in c and edge.b in d) or (edge.a in d and edge.b in c)
        )

    # Ordered unique edges ensure deterministic iteration.
    edge_list = sorted(graph.edges, key=lambda e: (e.a, e.b))

    merged = True
    while merged:
        merged = False
        for edge in edge_list:
            root_a = find(edge.a)
            root_b = find(edge.b)
            if root_a == root_b:
                continue
            e_cd = edge_connections(
                {n for n in graph.nodes if find(n) == root_a},
                {n for n in graph.nodes if find(n) == root_b},
            )
            gain = _modularity_gain(m, e_cd, degree_sum[root_a], degree_sum[root_b])
            if gain > max(quality_threshold, _MIN_GUARD):
                new_root = min(root_a, root_b)
                parent[root_a] = new_root
                parent[root_b] = new_root
                degree_sum[new_root] = degree_sum[root_a] + degree_sum[root_b]
                merged = True

    members: dict[str, set[str]] = defaultdict(set)
    for node in graph.nodes:
        members[find(node)].add(node)

    communities: list[dict[str, Any]] = []
    for root, member_set in members.items():
        size = len(member_set)
        internal = internal_edges(member_set)
        external = sum(
            1 for edge in graph.edges if (edge.a in member_set) != (edge.b in member_set)
        )
        density = 2.0 * internal / (size * (size - 1)) if size > 1 else 0.0
        communities.append(
            {
                "root": root,
                "member_ids": member_set,
                "community_size": len(member_set),
                "internal": internal,
                "external": external,
                "density": round(density, 6),
            }
        )

    # Stable ordering: largest first, ties by lexicographic id.
    communities.sort(key=lambda c: (-c["community_size"], c["root"]))
    for index, community in enumerate(communities):
        community["community_id"] = f"c{index}"
    return communities


def _dominant(values: Counter[str], cap: int = 3) -> list[str]:
    return [value for value, _ in values.most_common(cap)]


def summarise_communities(
    graph: Graph,
    communities: list[dict[str, Any]],
    entity_types: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Attach explainable statistics and return serialisable records."""
    entity_types = entity_types or {}
    rel_types = _relationship_types_by_edge(graph)
    results: list[dict[str, Any]] = []
    for community in communities:
        members = community["member_ids"]
        member_count = community.get("size", community.get("community_size", len(members)))
        etype_counter: Counter[str] = Counter()
        for node in members:
            etype_counter[entity_types.get(node, "unknown")] += 1
        rel_counter: Counter[str] = Counter()
        for edge in graph.edges:
            if edge.a in members and edge.b in members:
                for rel in rel_types.get((edge.a, edge.b), ()):
                    rel_counter[rel] += 1
                for rel in rel_types.get((edge.b, edge.a), ()):
                    rel_counter[rel] += 1

        results.append(
            {
                "community_id": community["community_id"],
                "member_count": member_count,
                "density": community["density"],
                "internal_edges": community["internal"],
                "external_edges": community["external"],
                "dominant_entity_types": _dominant(etype_counter),
                "dominant_relationship_types": _dominant(rel_counter),
                "member_entity_ids": sorted(members, key=lambda n: str(n)),
                "score": community["density"],
                "explanation": (
                    f"{member_count} entities, {community['internal']} "
                    f"internal edges, {community['external']} external edges, "
                    f"density {community['density']:.3f}"
                ),
            }
        )
    return results


def _relationship_types_by_edge(graph: Graph) -> dict[tuple[str, str], list[str]]:
    mapping: dict[tuple[str, str], list[str]] = defaultdict(list)
    for src, dst, rel_type in graph.directed:
        mapping[(src, dst)].append(rel_type)
    return mapping
