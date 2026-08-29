"""Investigation patterns and structural anomalies.

Each detector operates on the deterministic in-memory `Graph` plus entity
metadata and returns finding drafts with explicit signals.  "Suspicious" here
simply means "structurally unusual for this case": shared identifiers, cut
points, high fan-out, closed loops, combined location+identifier linkage, and
indirect connections. No criminal conclusion is ever asserted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.analytics.graph import Graph, articulation_points, find_triangles
from app.core.config import Settings

IDENTIFIER_TYPES = ("phone", "account", "vehicle", "organization")
ACTOR_TYPES = ("person", "organization")
LOCATION_TYPES = ("location",)
LOCATION_REL_TYPES = ("located_at", "visited")


@dataclass(frozen=True)
class EntityMeta:
    entity_id: str
    entity_type: str
    display_value: str
    confidence: float | None = None


@dataclass
class PatternDraft:
    title: str
    summary: str
    severity: str
    score: float
    confidence: float
    affected_entities: list[str]
    affected_relationships: list[str] = field(default_factory=list)
    signals: list[dict[str, object]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)


def _meta(entity_id: str, entities: dict[str, EntityMeta]) -> EntityMeta:
    return entities.get(entity_id, EntityMeta(entity_id, "unknown", entity_id))


def _display(entities: dict[str, EntityMeta], entity_ids: list[str]) -> str:
    return " / ".join(_meta(eid, entities).display_value for eid in entity_ids)


def _clamp01(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 6)


def detect_shared_identifiers(
    graph: Graph,
    entities: dict[str, EntityMeta],
    settings: Settings,
    max_results: int = 5,
) -> list[PatternDraft]:
    """Multiple entities connected to the same phone / account / vehicle / org."""
    degree = graph.degree
    threshold = settings.ANALYTICS_PATTERN_SHARED_IDENTIFIER_MIN
    drafts: list[PatternDraft] = []
    max_degree = max(degree.values()) if degree else 1
    for node in sorted(graph.nodes):
        meta = _meta(node, entities)
        if meta.entity_type not in IDENTIFIER_TYPES:
            continue
        count = degree[node]
        if count < threshold:
            continue
        neighbors = sorted(graph.adjacency.get(node, ()))
        score = _clamp01(count / max_degree)
        confidence = _clamp01(0.5 + 0.1 * (count - threshold) / max(1, threshold))
        drafts.append(
            PatternDraft(
                title=f"Shared identifier: {meta.display_value}",
                summary=(
                    f"{count} entities connect to the same {meta.entity_type} "
                    f"'{meta.display_value}': {_display(entities, neighbors)}."
                ),
                severity="HIGH" if count >= threshold + 2 else "MEDIUM",
                score=score,
                confidence=confidence,
                affected_entities=[node, *neighbors],
                signals=[
                    {
                        "name": "connected_entities",
                        "value": count,
                        "weight": 1.0,
                        "description": f"entities linked to identifier (threshold {threshold})",
                    },
                    {
                        "name": "normalized_degree",
                        "value": score,
                        "weight": 1.0,
                        "description": f"degree {count} / case max {max_degree}",
                    },
                ],
                metadata={"pattern": "shared_identifier", "identifier_entity_id": node},
            )
        )
    drafts.sort(key=lambda d: (-d.score, d.affected_entities[0]))
    return drafts[:max_results]


def detect_bridge_entities(
    graph: Graph,
    entities: dict[str, EntityMeta],
    max_results: int = 5,
) -> list[PatternDraft]:
    """Entities whose removal would split the network (cut vertices)."""
    cuts = articulation_points(graph)
    drafts: list[PatternDraft] = []
    total_pairs = len(graph.nodes) * (len(graph.nodes) - 1) // 2 or 1
    for node in sorted(cuts):
        meta = _meta(node, entities)
        # cheap proxy: how many of its neighbors lie beyond (bridge-like embeds)
        drafts.append(
            PatternDraft(
                title=f"Bridge entity: {meta.display_value}",
                summary=(
                    f"Removing '{meta.display_value}' splits the case network into "
                    f"separate parts; it is a structural cut point."
                ),
                severity="MEDIUM",
                score=1.0,
                confidence=0.8,
                affected_entities=[node],
                signals=[
                    {
                        "name": "is_cut_vertex",
                        "value": 1,
                        "weight": 1.0,
                        "description": "articulation point in the undirected graph",
                    },
                    {
                        "name": "pairs_if_removed",
                        "value": total_pairs,
                        "weight": 0.5,
                        "description": "node pairs whose unique paths transit the node",
                    },
                ],
                metadata={"pattern": "bridge_entity"},
            )
        )
    return drafts[:max_results]


def detect_relationship_concentration(
    graph: Graph,
    entities: dict[str, EntityMeta],
    settings: Settings,
    max_results: int = 5,
) -> list[PatternDraft]:
    """Entities with an unusually high number of direct connections (fan-out)."""
    degree = graph.degree
    if not degree:
        return []
    values = sorted(degree.values())
    tail = values[max(0, int(len(values) * settings.ANALYTICS_PATTERN_ANOMALY_TAIL)) - 1]
    threshold = max(settings.ANALYTICS_PATTERN_CONCENTRATION_MIN, tail)
    drafts: list[PatternDraft] = []
    max_degree = max(degree.values())
    for node in sorted(graph.nodes):
        count = degree[node]
        if count < threshold:
            continue
        meta = _meta(node, entities)
        score = _clamp01(count / max_degree)
        drafts.append(
            PatternDraft(
                title=f"Relationship concentration: {meta.display_value}",
                summary=(
                    f"'{meta.display_value}' holds {count} direct network connections, "
                    f"above the case tail of {threshold}."
                ),
                severity="HIGH" if count >= threshold * 2 else "MEDIUM",
                score=score,
                confidence=_clamp01(0.5 + 0.2 * (count - threshold) / max(1, threshold)),
                affected_entities=[node],
                signals=[
                    {
                        "name": "degree",
                        "value": count,
                        "weight": 1.0,
                        "description": "direct connections (undirected)",
                    },
                    {
                        "name": "case_percentile_95",
                        "value": tail,
                        "weight": 0.5,
                        "description": "degree tail threshold",
                    },
                    {
                        "name": "normalized_degree",
                        "value": score,
                        "weight": 1.0,
                        "description": f"degree {count} / case max {max_degree}",
                    },
                ],
                metadata={"pattern": "relationship_concentration"},
            )
        )
    drafts.sort(key=lambda d: (-d.score, d.affected_entities[0]))
    return drafts[:max_results]


def detect_circular_structures(
    graph: Graph,
    entities: dict[str, EntityMeta],
    max_results: int = 5,
) -> list[PatternDraft]:
    """Closed loops (3-cycles) — A <-> B <-> C <-> A style structure."""
    triangles = find_triangles(graph)
    drafts: list[PatternDraft] = []
    for triangle in triangles[:max_results]:
        members = sorted(triangle)
        score = 1.0
        drafts.append(
            PatternDraft(
                title="Closed connection loop",
                summary=(
                    f"{_display(entities, members)} form a closed loop "
                    f"(each is connected to the other two)."
                ),
                severity="MEDIUM",
                score=score,
                confidence=0.9,
                affected_entities=members,
                signals=[
                    {
                        "name": "cycle_members",
                        "value": len(members),
                        "weight": 1.0,
                        "description": "entities in the 3-cycle",
                    },
                ],
                metadata={"pattern": "circular_structure", "members": members},
            )
        )
    return drafts[:max_results]


def _undirected_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def detect_location_identifier_combination(
    graph: Graph,
    entities: dict[str, EntityMeta],
    edge_relationships: dict[tuple[str, str], list[str]],
    max_results: int = 5,
) -> list[PatternDraft]:
    """One entity simultaneously ties a location and an identifier/asset."""
    rel_by_pair: dict[tuple[str, str], list[str]] = {
        (min(a, b), max(a, b)): ids for (a, b), ids in edge_relationships.items()
    }
    drafts: list[PatternDraft] = []
    for node in sorted(graph.nodes):
        meta = _meta(node, entities)
        if meta.entity_type not in ACTOR_TYPES:
            continue
        neighbors = graph.adjacency.get(node, set())
        loc = [n for n in neighbors if _meta(n, entities).entity_type in LOCATION_TYPES]
        idf = [n for n in neighbors if _meta(n, entities).entity_type in IDENTIFIER_TYPES]
        if not loc or not idf:
            continue
        score = _clamp01((len(loc) + len(idf)) / max(4, 1))
        relationship_ids = [
            rid for n in (loc + idf) for rid in rel_by_pair.get(_undirected_key(node, n), ())
        ]
        drafts.append(
            PatternDraft(
                title=f"Location + identifier linkage: {meta.display_value}",
                summary=(
                    f"'{meta.display_value}' combines {len(loc)} location "
                    f"connection(s) ({_display(entities, loc)}) with "
                    f"{len(idf)} identifier connection(s) ({_display(entities, idf)})."
                ),
                severity="MEDIUM",
                score=score,
                confidence=0.7,
                affected_entities=[node, *loc, *idf],
                affected_relationships=list(dict.fromkeys(relationship_ids)),
                signals=[
                    {
                        "name": "location_links",
                        "value": len(loc),
                        "weight": 0.5,
                        "description": "distinct locations connected to the actor",
                    },
                    {
                        "name": "identifier_links",
                        "value": len(idf),
                        "weight": 0.5,
                        "description": "distinct identifiers connected to the actor",
                    },
                ],
                metadata={
                    "pattern": "location_identifier_combination",
                    "locations": loc,
                    "identifiers": idf,
                },
            )
        )
    drafts.sort(key=lambda d: -d.score)
    return drafts[:max_results]


def detect_rapid_expansion(
    entities: dict[str, EntityMeta],
    relationship_spread_seconds: dict[str, float],
    min_spread_seconds: int = 3600,
    max_results: int = 3,
) -> list[PatternDraft]:
    """Explosive growth in an entity's relationship timestamps.

    Uses real relationship ``created_at`` timestamps: when an entity's links were
    created across distinct moments (spread >= the configured horizon) it is
    flagged. Cases ingested in one batch show no spread and the detector
    reports nothing rather than fabricate temporal data.
    """
    drafts: list[PatternDraft] = []
    for node, spread in relationship_spread_seconds.items():
        if spread < min_spread_seconds:
            continue
        meta = _meta(node, entities)
        if meta.entity_type not in ACTOR_TYPES:
            continue
        drafts.append(
            PatternDraft(
                title=f"Rapid connection growth: {meta.display_value}",
                summary=(
                    f"Relationships involving '{meta.display_value}' span "
                    f"{spread / 3600:.1f} hours of distinct timing "
                    f"(>= {min_spread_seconds // 3600} hour threshold); review the "
                    f"evidence sequence for clustering."
                ),
                severity="LOW",
                score=0.6,
                confidence=0.6,
                affected_entities=[node],
                signals=[
                    {
                        "name": "relationship_time_spread_seconds",
                        "value": round(spread, 0),
                        "weight": 1.0,
                        "description": "max - min created_at of the entity's relationships",
                    },
                ],
                metadata={"pattern": "rapid_expansion"},
            )
        )
    return drafts[:max_results]


def detect_patterns(
    graph: Graph,
    entities: dict[str, EntityMeta],
    settings: Settings,
    edge_relationships: dict[tuple[str, str], list[str]] | None = None,
    relationship_spread_seconds: dict[str, float] | None = None,
    max_results_per_type: int = 5,
) -> list[PatternDraft]:
    """Run all structural detectors and merge their drafts."""
    drafts: list[PatternDraft] = []
    drafts.extend(detect_shared_identifiers(graph, entities, settings, max_results_per_type))
    drafts.extend(detect_bridge_entities(graph, entities, max_results_per_type))
    drafts.extend(
        detect_relationship_concentration(graph, entities, settings, max_results_per_type)
    )
    drafts.extend(detect_circular_structures(graph, entities, max_results_per_type))
    drafts.extend(
        detect_location_identifier_combination(
            graph, entities, edge_relationships or {}, max_results_per_type
        )
    )
    drafts.extend(
        detect_rapid_expansion(
            entities,
            relationship_spread_seconds or {},
            min_spread_seconds=settings.ANALYTICS_PATTERN_RAPID_SPREAD_SECONDS,
            max_results=max_results_per_type,
        )
    )
    drafts.sort(key=lambda d: (-d.score, d.title))
    return drafts
