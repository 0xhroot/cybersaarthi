"""Unit tests for the deterministic Phase 3 analytics algorithms.

These are pure-Python tests over synthetic in-memory graphs; no database,
graph store, cache or object storage is touched.
"""

from __future__ import annotations

import math

from app.analytics.communities import detect_communities
from app.analytics.graph import (
    Graph,
    articulation_points,
    betweenness_centrality,
    build_graph,
    closeness_centrality,
    common_neighbors,
    connected_components,
    find_triangles,
    pagerank,
)
from app.analytics.hypotheses import generate_hypotheses
from app.analytics.network_dna import NetworkProfileResult, build_network_profile, tier_for
from app.analytics.patterns import (
    EntityMeta,
    detect_bridge_entities,
    detect_circular_structures,
    detect_patterns,
    detect_rapid_expansion,
    detect_relationship_concentration,
    detect_shared_identifiers,
)
from app.analytics.priority import compute_priority, hypothesis_weight, pattern_weight
from app.analytics.strength import EvidenceStats, compute_strength_signals
from app.core.config import get_settings


def _graph(edges: list[tuple[str, str]]) -> Graph:
    nodes = {node for edge in edges for node in edge}
    return build_graph(nodes, [(a, b, "test") for a, b in edges])


def _meta(entity_id: str, label: str, kind: str = "person") -> EntityMeta:
    return EntityMeta(entity_id, kind, label, confidence=0.9)


def test_connected_components_detects_two_components() -> None:
    graph = _graph([("a", "b"), ("b", "c"), ("x", "y")])
    components = connected_components(graph)
    assert [len(c) for c in components] == [3, 2]


def test_articulation_points_center_of_star() -> None:
    graph = _graph([("hub", "a"), ("hub", "b"), ("hub", "c")])
    assert articulation_points(graph) == frozenset({"hub"})


def test_articulation_points_none_in_triangle() -> None:
    graph = _graph([("a", "b"), ("b", "c"), ("c", "a")])
    assert articulation_points(graph) == frozenset()


def test_articulation_points_two_node_component() -> None:
    graph = _graph([("a", "b")])
    assert articulation_points(graph) == frozenset()


def test_articulation_points_disconnected_with_isolated_nodes() -> None:
    graph = _graph([("a", "b"), ("b", "c"), ("y", "z")])
    assert articulation_points(graph) == frozenset({"b"})


def test_articulation_points_long_chain_exceeds_recursion_limit() -> None:
    """Regression: a 1500-node chain used to raise RecursionError (A01).

    The DFS is iterative, so deep graphs are analysed without touching the
    interpreter recursion limit.  Every interior node of a chain is a cut
    vertex: the two endpoints are not.
    """
    size = 1500
    edges = [(f"n{i}", f"n{i + 1}") for i in range(size - 1)]
    graph = build_graph(
        {node for edge in edges for node in edge},
        [(a, b, "chain") for a, b in edges],
    )
    cuts = articulation_points(graph)
    assert len(cuts) == size - 2
    assert "n0" not in cuts and f"n{size - 1}" not in cuts
    assert "n749" in cuts


def test_articulation_points_large_star() -> None:
    """A 1500-node star has exactly one cut vertex (its hub)."""
    size = 1500
    graph = build_graph(
        {f"leaf{i}" for i in range(size)} | {"hub"},
        [(f"leaf{i}", "hub", "called") for i in range(size)],
    )
    assert articulation_points(graph) == frozenset({"hub"})


def test_articulation_points_is_deterministic() -> None:
    """Repeated runs over the same graph return an identical cut set."""
    edges = [(f"n{i}", f"n{i + 1}") for i in range(1200 - 1)]
    graph = build_graph(
        {node for edge in edges for node in edge},
        [(a, b, "chain") for a, b in edges],
    )
    first = articulation_points(graph)
    for _ in range(3):
        assert articulation_points(graph) == first


def test_betweenness_bridge_middleman() -> None:
    graph = _graph([("a", "b"), ("b", "c"), ("c", "d")])
    betweenness = betweenness_centrality(graph)
    assert betweenness["b"] == betweenness["c"]
    assert betweenness["b"] > betweenness["a"]
    assert betweenness["a"] == 0.0
    assert betweenness["b"] > 0.0


def test_betweenness_isolated_node_is_zero() -> None:
    graph = build_graph({"lonely"}, [])
    betweenness = betweenness_centrality(graph)
    assert betweenness["lonely"] == 0.0


def test_closeness_center_is_most_central() -> None:
    graph = _graph([("a", "b"), ("b", "c"), ("b", "d")])
    closeness = closeness_centrality(graph)
    assert closeness["b"] == max(closeness.values())
    assert closeness["a"] == closeness["d"]


def test_pagerank_converges_and_sums_to_one() -> None:
    graph = _graph([("a", "b"), ("b", "c"), ("c", "a")])
    graph = build_graph(
        {"a", "b", "c"},
        [("a", "b", "test"), ("b", "c", "test"), ("c", "a", "test")],
    )
    ranks = pagerank(graph)
    assert all(value > 0 for value in ranks.values())
    assert math.isclose(sum(ranks.values()), 1.0, abs_tol=1e-6)


def test_common_neighbors_and_triangles() -> None:
    graph = _graph([("a", "b"), ("b", "c"), ("c", "a"), ("c", "d")])
    assert common_neighbors(graph, "a", "d") == {"c"}
    assert find_triangles(graph) == [frozenset({"a", "b", "c"})]


def test_detect_communities_two_dense_cliques() -> None:
    clique_a = _graph([("a1", "a2"), ("a2", "a3"), ("a3", "a1"), ("a1", "a3")])
    clique_b = _graph([("b1", "b2"), ("b2", "b3"), ("b3", "b1")])
    combined = build_graph(
        set(clique_a.nodes) | set(clique_b.nodes) | {"bridge"},
        [
            *clique_a.directed[:-1],
            *clique_b.directed,
            ("a1", "bridge", "test"),
            ("bridge", "b1", "test"),
        ],
    )
    communities = detect_communities(combined, quality_threshold=0.0)
    member_sets = [c["member_ids"] for c in communities]
    assert any("a1" in members and "a2" in members and "a3" in members for members in member_sets)
    assert any("b1" in members and "b2" in members for members in member_sets)
    assert all(c["community_size"] >= 1 for c in communities)


def test_detect_shared_identifiers_passes_threshold() -> None:
    settings = get_settings()
    phone = "p1"
    entities = {
        "p1": _meta("p1", "+91-7000000001", "phone"),
        **{f"person{i}": _meta(f"person{i}", f"person{i}") for i in range(3)},
    }
    graph = build_graph(
        set(entities),
        [("person0", phone, "called"), ("person1", phone, "called"), ("person2", phone, "called")],
    )
    drafts = detect_shared_identifiers(graph, entities, settings)
    assert len(drafts) == 1
    assert drafts[0].metadata["pattern"] == "shared_identifier"
    assert drafts[0].metadata["identifier_entity_id"] == phone
    assert len(drafts[0].affected_entities) == 4


def test_detect_shared_identifiers_below_threshold_empty() -> None:
    settings = get_settings()
    entities = {
        "p1": _meta("p1", "phone", "phone"),
        "person0": _meta("person0", "person0"),
        "person1": _meta("person1", "person1"),
    }
    graph = build_graph(
        set(entities),
        [("person0", "p1", "called"), ("person1", "p1", "called")],
    )
    assert detect_shared_identifiers(graph, entities, settings) == []


def test_detect_bridge_entities_reports_cut_point() -> None:
    entities = {
        "bridge": _meta("bridge", "Bridge Person"),
        "a": _meta("a", "A"),
        "b": _meta("b", "B"),
    }
    graph = build_graph(set(entities), [("a", "bridge", "called"), ("bridge", "b", "called")])
    titles = [d.title for d in detect_bridge_entities(graph, entities)]
    assert any("Bridge Person" in title for title in titles)


def test_detect_relationship_concentration_tail() -> None:
    settings = get_settings()
    entities = {"hub": _meta("hub", "hub"), "c": _meta("c", "c")}
    edges = [(f"neighbor{i}", "hub") for i in range(10)] + [("neighbor0", "c")]
    nodes = set(entities) | {a for a, b in edges} | {b for a, b in edges}
    graph = build_graph(nodes, [(a, b, "test") for a, b in edges])
    drafts = detect_relationship_concentration(graph, entities, settings)
    assert drafts and drafts[0].affected_entities == ["hub"]


def test_detect_circular_structures_finds_loop() -> None:
    entities = {n: _meta(n, n) for n in ("a", "b", "c")}
    graph = _graph([("a", "b"), ("b", "c"), ("c", "a")])
    drafts = detect_circular_structures(graph, entities)
    assert len(drafts) == 1
    assert set(drafts[0].affected_entities) == {"a", "b", "c"}


def test_detect_rapid_expansion_requires_real_timing() -> None:
    entities = {"actor": _meta("actor", "actor")}
    drafts = detect_rapid_expansion(entities, {"actor": 0.0}, min_spread_seconds=3600)
    assert drafts == []
    drafts = detect_rapid_expansion(entities, {"actor": 7200.0}, min_spread_seconds=3600)
    assert len(drafts) == 1
    assert drafts[0].metadata["pattern"] == "rapid_expansion"


def test_detect_patterns_merges_detectors() -> None:
    settings = get_settings()
    phone = "phone"
    entities = {
        **{f"person{i}": _meta(f"person{i}", f"person{i}") for i in range(3)},
        "phone": _meta("phone", "+91-7000000001", "phone"),
    }
    graph = build_graph(
        set(entities),
        [
            ("person0", phone, "called"),
            ("person1", phone, "called"),
            ("person2", phone, "called"),
            ("person0", "person2", "called"),
        ],
    )
    drafts = detect_patterns(graph, entities, settings)
    patterns = {d.metadata["pattern"] for d in drafts}
    assert "shared_identifier" in patterns


def test_generate_hypotheses_for_shared_neighbours() -> None:
    settings = get_settings()
    entities = {
        "a": _meta("a", "Alice"),
        "b": _meta("b", "Bob"),
        "c1": _meta("c1", "c1"),
        "c2": _meta("c2", "c2"),
        "p": _meta("p", "phone", "phone"),
    }
    node_ids = set(entities)
    graph = build_graph(
        node_ids,
        [
            ("a", "c1", "called"),
            ("a", "c2", "called"),
            ("b", "c1", "called"),
            ("b", "c2", "called"),
            ("a", "p", "called"),
        ],
    )
    edge_relationships = {
        (min(s, t), max(s, t)): [rid]
        for s, t, rid in [
            ("a", "c1", "r1"),
            ("a", "c2", "r2"),
            ("b", "c1", "r3"),
            ("b", "c2", "r4"),
        ]
    }
    drafts = generate_hypotheses(graph, entities, settings, edge_relationships)
    assert any(d.candidate_relation_type == "called" for d in drafts)
    assert all(len(d.affected_entities) >= 2 for d in drafts)


def test_generate_hypotheses_never_mutates_graph() -> None:
    """Missing-link hypotheses are projections; they must not add edges."""
    settings = get_settings()
    entities = {
        "a": _meta("a", "Alice"),
        "b": _meta("b", "Bob"),
        "c1": _meta("c1", "c1"),
        "c2": _meta("c2", "c2"),
    }
    graph = build_graph(
        set(entities),
        [("a", "c1", "called"), ("a", "c2", "called"), ("b", "c1", "called")],
    )
    edges_before = len(graph.edges)
    directed_before = len(graph.directed)

    generate_hypotheses(
        graph,
        entities,
        settings,
        edge_relationships={
            (min(s, t), max(s, t)): [rid]
            for s, t, rid in [("a", "c1", "r1"), ("a", "c2", "r2"), ("b", "c1", "r3")]
        },
    )

    assert len(graph.edges) == edges_before
    assert len(graph.directed) == directed_before


def test_hypothesis_candidate_relation_type_is_canonical() -> None:
    from app.models import RELATIONSHIP_TYPES

    settings = get_settings()
    entities = {
        "a": _meta("a", "Alice"),
        "b": _meta("b", "Bob"),
        "c1": _meta("c1", "c1"),
        "c2": _meta("c2", "c2"),
    }
    graph = build_graph(
        set(entities),
        [("a", "c1", "called"), ("a", "c2", "called"), ("b", "c1", "called")],
    )
    drafts = generate_hypotheses(
        graph,
        entities,
        settings,
        edge_relationships={
            (min(s, t), max(s, t)): [rid]
            for s, t, rid in [("a", "c1", "r1"), ("a", "c2", "r2"), ("b", "c1", "r3")]
        },
    )
    assert drafts
    for draft in drafts:
        assert draft.candidate_relation_type in {*RELATIONSHIP_TYPES, None}


def test_hypotheses_reproduce_across_hash_seeds() -> None:
    """Hypothesis selection must not depend on PYTHONHASHSEED.

    Guard against set-iteration-order leaking into the bounded candidate list:
    the star fixture produces many hypotheses with *identical* scores, so the
    sort key is not a total order and the ``[:max_hypotheses]`` cutoff is only
    deterministic if actor/neighbour iteration is canonical.
    """
    import os
    import subprocess
    import sys

    probe = r"""
import json, sys
sys.path.insert(0, ".")
from app.analytics.graph import build_graph
from app.analytics.hypotheses import generate_hypotheses
from app.analytics.patterns import EntityMeta
from app.core.config import get_settings

def meta(entity_id: str, kind: str = "person") -> EntityMeta:
    return EntityMeta(entity_id, kind, entity_id, confidence=0.9)

ids = [f"p{i}" for i in range(1, 9)] + ["hub"]
entities = {i: meta(i, "person") for i in ids}
graph = build_graph(
    set(entities),
    [(speak, "hub", "called") for speak in ids if speak != "hub"],
)
drafts = generate_hypotheses(graph, entities, get_settings(), {})
snapshot = sorted(
    [
        str(draft.score),
        draft.severity,
        tuple(draft.affected_entities),
        draft.candidate_relation_type,
    ]
    for draft in drafts
)
print(json.dumps(snapshot))
"""

    def snapshot(seed: str) -> str:
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        env["ANALYTICS_MAX_HYPOTHESES"] = "5"
        proc = subprocess.run(  # noqa: S603 - fixed constant probe, no untrusted input
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            env=env,
            cwd=".",
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip().splitlines()[-1]

    outputs = {snapshot(seed) for seed in ("1", "2", "3", "7")}
    assert len(outputs) == 1, "hypotheses differ across PYTHONHASHSEED values"


def test_network_dna_profile_and_tiers() -> None:
    result = build_network_profile(
        entity_id="e1",
        entity_type="person",
        raw={"prominence": 10.0, "influence": 0.5, "bridging": 0.4},
        case_max={"prominence": 10.0, "influence": 1.0, "bridging": 1.0},
    )
    assert isinstance(result, NetworkProfileResult)
    assert 0.0 <= result.overall_score <= 1.0
    assert result.tier in {"PERIPHERAL", "MONITORED", "SIGNIFICANT", "FOCAL"}
    assert all(0.0 <= f["normalized"] <= 1.0 for f in result.features)
    full = build_network_profile(
        entity_id="e1",
        entity_type="person",
        raw={
            name: 1.0
            for name in (
                "prominence",
                "influence",
                "bridging",
                "reach",
                "anchorage",
                "activity",
                "evidence_depth",
                "community_span",
            )
        },
        case_max={
            name: 1.0
            for name in (
                "prominence",
                "influence",
                "bridging",
                "reach",
                "anchorage",
                "activity",
                "evidence_depth",
                "community_span",
            )
        },
    )
    assert full.tier == "FOCAL"
    assert tier_for(0.0) == "PERIPHERAL"


def test_priority_formula_and_tiers() -> None:
    score, tier = compute_priority(
        prominence=1.0,
        influence=1.0,
        bridging=1.0,
        reach=1.0,
        finding_severities=["HIGH", "CRITICAL"],
        hypothesis_count=3,
    )
    assert tier == "CRITICAL"
    assert score >= 0.75
    low_score, _ = compute_priority(prominence=0.0, influence=0.0, bridging=0.0, reach=0.0)
    assert low_score == 0.0
    assert pattern_weight(["HIGH", "high", "MEDIUM"]) == 1.0
    assert hypothesis_weight(3) == 1.0
    assert pattern_weight(["LOW"]) == 0.1


def test_strength_signals_formula() -> None:
    result = compute_strength_signals(
        evidence=EvidenceStats(
            count=5,
            types=("called", "called"),
            source_record_ids=("s1", "s2"),
            evidence_file_ids=("f1", "f2"),
        ),
        entity_confidences=(0.9, 0.9),
        case_max_evidence=5,
        case_distinct_sources=10,
        case_independent_files=10,
    )
    assert 0.0 <= result.strength <= 1.0
    assert result.evidence_count == 5
    assert result.distinct_sources == 2
    assert result.independent_files == 2
    assert len(result.signals) == 5
    single = compute_strength_signals(
        evidence=EvidenceStats(
            count=1,
            types=("field", "co_occurrence"),
            source_record_ids=("s1",),
            evidence_file_ids=("f1",),
        ),
        entity_confidences=(None, None),
        case_max_evidence=1,
        case_distinct_sources=1,
        case_independent_files=1,
    )
    assert math.isclose(single.strength, 1.0, abs_tol=1e-6)


def test_build_graph_drops_self_loops_and_dedupes() -> None:
    graph = build_graph(
        {"a", "b"}, [("a", "a", "test"), ("a", "b", "test"), ("b", "a", "test"), ("a", "b", "test")]
    )
    assert len(graph.edges) == 1
    assert len(graph.directed) == 3
