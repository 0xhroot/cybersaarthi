"""Deterministic entity ranking for AI answers (authoritative, case-scoped).

This module exists so the model never recalculates a ranking from a long text
digest. It computes the answer in code from the authorized case's own rows and
returns a typed, validated record. The model only explains the verified result.

Guarantees:
- Case scope is inherited from the already-authorized ``Case`` row; nothing here
  trusts a model-supplied case id.
- Metrics are explicit and named; when a metric is genuinely unavailable the
  result says so instead of substituting a different metric.
- Ordering is deterministic: primary key ``-value``, tie-break ``entity_id``
  ascending. Two calls on the same data always agree.
- Every ranked row carries its entity id so citations resolve to real records.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, Relationship

# Metrics this module can compute authoritatively. The value is a short,
# human/LLM-readable definition so the model can quote the exact measure.
METRIC_DEFINITIONS: dict[str, str] = {
    "relationship_count": "number of relationships where the entity is source or target",
    "distinct_neighbors": "number of distinct neighbouring entities (undirected, deduplicated)",
    "pagerank": "PageRank centrality over the case relationship graph",
    "degree": "number of distinct neighbouring entities (undirected degree)",
}

SUPPORTED_METRICS = tuple(METRIC_DEFINITIONS)

# How many ranked rows to return. Small enough to fit a tight context budget.
DEFAULT_TOP_N = 5
MAX_TOP_N = 50


class UnsupportedMetricError(ValueError):
    """Raised when a requested metric is not authoritatively computable."""


async def _relationship_counts(session: AsyncSession, case_id: str) -> dict[str, int]:
    """Per-entity relationship count (source or target), active entities only.

    Uses the same join as ``retrieval.entities_digest`` so the two agree.
    """
    rows = (
        await session.execute(
            select(Entity.id, func.count(Relationship.id).label("rel_count"))
            .outerjoin(
                Relationship,
                (Relationship.case_id == case_id)
                & (
                    (Relationship.source_entity_id == Entity.id)
                    | (Relationship.target_entity_id == Entity.id)
                ),
            )
            .where(Entity.case_id == case_id, Entity.status == "active")
            .group_by(Entity.id)
        )
    ).all()
    return {str(entity_id): int(count) for entity_id, count in rows}


async def _entity_labels(session: AsyncSession, case_id: str) -> dict[str, str]:
    """entity_id -> display label (for citations and the explanation)."""
    rows = (
        await session.execute(
            select(Entity.id, Entity.display_value).where(
                Entity.case_id == case_id, Entity.status == "active"
            )
        )
    ).all()
    return {str(entity_id): label for entity_id, label in rows}


async def _pagerank_scores(session: AsyncSession, case_id: str) -> dict[str, float]:
    """PageRank over the case graph, via the deterministic analytics package."""
    from app.analytics.graph import build_graph, pagerank

    rel_rows = (
        await session.execute(
            select(Relationship.source_entity_id, Relationship.target_entity_id).where(
                Relationship.case_id == case_id
            )
        )
    ).all()
    entity_ids = await _relationship_counts(session, case_id)
    nodes = set(entity_ids)
    relationships = [(str(src), str(dst), "related") for src, dst in rel_rows if src != dst]
    if not nodes:
        return {}
    graph = build_graph(nodes, relationships)
    return {node: float(score) for node, score in pagerank(graph).items()}


async def _neighbor_counts(session: AsyncSession, case_id: str) -> dict[str, int]:
    """Per-entity DISTINCT neighbour count (undirected, deduplicated).

    An A<->B association yields one neighbour for each, regardless of how many
    relationship rows connect them.
    """
    from sqlalchemy import case as sql_case

    # Normalise each edge so (A,B) and (B,A) collapse to one undirected pair.
    other = sql_case(
        (Relationship.source_entity_id == Entity.id, Relationship.target_entity_id),
        else_=Relationship.source_entity_id,
    ).label("other")
    rows = (
        await session.execute(
            select(Entity.id, func.count(func.distinct(other)).label("neigh"))
            .join(
                Relationship,
                (Relationship.case_id == case_id)
                & (
                    (Relationship.source_entity_id == Entity.id)
                    | (Relationship.target_entity_id == Entity.id)
                ),
            )
            .where(Entity.case_id == case_id, Entity.status == "active")
            .group_by(Entity.id)
        )
    ).all()
    return {str(entity_id): int(count) for entity_id, count in rows}


async def rank_entities(
    session: AsyncSession,
    case_id: str,
    *,
    metric: str = "relationship_count",
    top_n: int = DEFAULT_TOP_N,
) -> dict[str, Any]:
    """Return the authoritative top-N entities for one metric.

    Returns a typed record:
      {
        "metric": str,
        "metric_definition": str,
        "unit": str,
        "top_n": int,
        "total_entities": int,
        "results": [
          {"rank": 1, "entity_id": str, "label": str, "value": float},
          ...
        ],
      }
    Raises ``UnsupportedMetricError`` when the metric is not computable.
    """
    if metric not in SUPPORTED_METRICS:
        raise UnsupportedMetricError(
            f"unsupported metric {metric!r}; available: {', '.join(SUPPORTED_METRICS)}"
        )
    top_n = max(1, min(int(top_n), MAX_TOP_N))

    if metric == "relationship_count":
        counts = await _relationship_counts(session, case_id)
        values = {eid: float(c) for eid, c in counts.items()}
        unit = "relationships"
    elif metric == "pagerank":
        values = await _pagerank_scores(session, case_id)
        unit = "score"
    else:  # distinct_neighbors and degree are the same undirected measure
        neigh = await _neighbor_counts(session, case_id)
        values = {eid: float(c) for eid, c in neigh.items()}
        unit = "neighbours"

    labels = await _entity_labels(session, case_id)
    # Deterministic ordering: value desc, then entity_id asc. Stable across runs.
    ordered = sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))
    total = len(ordered)

    results = [
        {
            "rank": rank,
            "entity_id": entity_id,
            "label": labels.get(entity_id, entity_id),
            "value": value,
        }
        for rank, (entity_id, value) in enumerate(ordered[:top_n], start=1)
    ]

    return {
        "metric": metric,
        "metric_definition": METRIC_DEFINITIONS[metric],
        "unit": unit,
        "top_n": top_n,
        "total_entities": total,
        "results": results,
    }
