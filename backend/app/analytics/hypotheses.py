"""Missing-link hypotheses — plausible but not yet evidenced connections.

Generated only for entity pairs with *no* direct relationship that share real
structural signals (a common neighbour such as a phone, account, vehicle,
organization or location; or co-membership in the same detected community).
Each hypothesis lists the exact shared signals and the graph paths that
support it, and its score never creates a real edge in the graph.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from app.analytics.communities import detect_communities
from app.analytics.graph import Graph, common_neighbors
from app.analytics.patterns import EntityMeta
from app.core.config import Settings


def _undirected_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


ACTOR_TYPES = ("person", "organization")
IDENTIFIER_TYPES = ("phone", "account", "vehicle")


@dataclass
class HypothesisDraft:
    title: str
    summary: str
    severity: str
    score: float
    confidence: float
    affected_entities: list[str]
    affected_relationships: list[str]
    candidate_relation_type: str | None
    signals: list[dict[str, object]]
    metadata: dict[str, object]


def _meta(entity_id: str, entities: dict[str, EntityMeta]) -> EntityMeta:
    return entities.get(entity_id, EntityMeta(entity_id, "unknown", entity_id))


def _display(entity_id: str, entities: dict[str, EntityMeta]) -> str:
    return _meta(entity_id, entities).display_value


def generate_hypotheses(
    graph: Graph,
    entities: dict[str, EntityMeta],
    settings: Settings,
    edge_relationships: dict[tuple[str, str], list[str]],
) -> list[HypothesisDraft]:
    """Generate bounded, deterministic missing-link hypotheses.

    ``max_hypotheses`` candidates (sorted by score) are produced. The
    relationship types running through the shared neighbours suggest a
    candidate relation type; nothing is written back to the graph.
    """
    max_hypotheses = settings.ANALYTICS_MAX_HYPOTHESES
    if max_hypotheses <= 0:
        return []

    actors = sorted(
        node for node in graph.nodes if _meta(node, entities).entity_type in ACTOR_TYPES
    )
    if len(actors) < 2:
        return []

    communities = detect_communities(graph, quality_threshold=settings.ANALYTICS_COMMUNITY_QUALITY)
    community_membership: dict[str, str] = {}
    for community in communities:
        for member in community["member_ids"]:
            community_membership[member] = community["community_id"]

    adj = graph.adjacency
    # Map pair -> shared neighbours (identity of common neighbours is a traceable
    # structural signal).
    shared: dict[tuple[str, str], set[str]] = defaultdict(set)
    for a_index, a in enumerate(actors):
        for b in actors[a_index + 1 :]:
            if b in adj.get(a, ()):
                continue  # already directly connected
            shared_neighbors = common_neighbors(graph, a, b)
            if shared_neighbors:
                shared[(a, b)] = shared_neighbors

    if not shared:
        return []

    max_shared = max(len(v) for v in shared.values()) or 1
    rel_by_undirected: dict[tuple[str, str], list[str]] = {
        (min(s, t), max(s, t)): ids for (s, t), ids in edge_relationships.items()
    }
    # relationship types observed between every directed pair (for suggesting
    # the candidate relation type of a missing edge)
    rel_types_between: dict[tuple[str, str], list[str]] = defaultdict(list)
    for src, dst, rel_type in graph.directed:
        rel_types_between[(src, dst)].append(rel_type)

    hypotheses: list[HypothesisDraft] = []
    for (a, b), neighbors in sorted(shared.items(), key=lambda item: (item[0][0], item[0][1])):
        type_counter = Counter(_meta(n, entities).entity_type for n in sorted(neighbors))
        same_community = community_membership.get(a) == community_membership.get(b)

        shared_score = len(neighbors) / max_shared

        supporting_rels: list[str] = []
        relation_type_votes = Counter[str]()
        for node in sorted(neighbors):
            for endpoint in (a, b):
                pair = _undirected_key(endpoint, node)
                supporting_rels.extend(rel_by_undirected.get(pair, ()))
                for other_type in rel_types_between.get((endpoint, node), ()):
                    relation_type_votes[other_type] += 1
                for other_type in rel_types_between.get((node, endpoint), ()):
                    relation_type_votes[other_type] += 1

        candidate_type: str | None = None
        if relation_type_votes:
            candidate_type = relation_type_votes.most_common(1)[0][0]

        score = round(
            0.55 * shared_score + 0.30 * (1.0 if same_community else 0.0) + 0.15,
            6,
        )
        confidence = round(min(1.0, 0.35 + 0.15 * len(neighbors)), 6)
        severity = "MEDIUM" if len(neighbors) >= 2 else "LOW"

        person_a, person_b = _display(a, entities), _display(b, entities)
        shared_desc = "; ".join(f"{count} {etype}" for etype, count in type_counter.most_common())
        hypotheses.append(
            HypothesisDraft(
                title=f"Possible connection: {person_a} ↔ {person_b}",
                summary=(
                    f"No direct relationship exists, but {person_a} and {person_b} "
                    f"share {len(neighbors)} structural connection(s) "
                    f"({shared_desc}): each could be linked via an unseen edge."
                ),
                severity=severity,
                score=score,
                confidence=confidence,
                affected_entities=[a, b],
                affected_relationships=list(dict.fromkeys(supporting_rels)),
                candidate_relation_type=candidate_type,
                signals=[
                    {
                        "name": "shared_neighbors",
                        "value": len(neighbors),
                        "weight": 0.55,
                        "description": f"common connection(s): {shared_desc}",
                    },
                    {
                        "name": "same_community",
                        "value": 1 if same_community else 0,
                        "weight": 0.30,
                        "description": "both members of the same detected community",
                    },
                    {
                        "name": "supported_by_rels",
                        "value": len(supporting_rels),
                        "weight": 0.15,
                        "description": "existing relationships linking the pair via shared nodes",
                    },
                ],
                metadata={
                    "hypothesis": "missing_link",
                    "shared_neighbor_ids": sorted(neighbors),
                    "community_id": community_membership.get(a),
                    "candidate_relation_type": candidate_type,
                },
            )
        )

    hypotheses.sort(key=lambda h: (-h.score, h.affected_entities[0]))
    return hypotheses[:max_hypotheses]
