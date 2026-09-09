"""Bounded multi-hop path queries executed in Neo4j.

Neo4j is used here because traversal is its strength (shortest paths, k-hop
fan-out) while heavyweight global algorithms (components, communities,
centrality, PageRank) run exactly in :mod:`app.analytics.graph` — Neo4j
Community Edition ships no algorithm library (GDS) to compute them.

All queries are parameterized; the relationship-type filter is a fixed,
canonical list produced from the model constants (never user input).
"""

from __future__ import annotations

import logging

from neo4j import AsyncDriver

from app.db.neo4j import GraphStore
from app.models import RELATIONSHIP_TYPES

logger = logging.getLogger(__name__)

_REL_TYPES_UPPER = "|".join(rel.upper() for rel in RELATIONSHIP_TYPES)


def _rel_pattern(lo: int, hi: int) -> str:
    return f"[:{_REL_TYPES_UPPER}*{lo}..{hi}]"


async def bounded_ego_paths(
    graph_store: GraphStore,
    case_id: str,
    entity_id: str,
    max_hops: int,
    limit: int,
) -> list[dict[str, object]]:
    """All shortest paths (bounded hops) from an entity to its neighbours.

    Returns: [{"node_ids": [...], "relationship_ids": [...],
               "relationship_types": [...], "hops": int}]
    """
    if max_hops < 1:
        return []
    driver: AsyncDriver = graph_store.driver()
    # Materialise `other` distinct from `start` BEFORE the shortest-path search:
    # allShortestPaths rejects a common start/end node, so the self row must
    # never reach it.
    cypher = f"""
        MATCH (start:Entity {{id: $entity_id, case_id: $case_id}})
        WITH start
        MATCH (other:Entity {{case_id: $case_id}})
        WHERE other.id <> start.id
        WITH start, other
        MATCH path = allShortestPaths(
            (start)-{_rel_pattern(1, max_hops)}-(other)
        )
        WHERE all(n IN nodes(path)[1..] WHERE n.id <> start.id)
        WITH path, other
        ORDER BY length(path), other.id
        RETURN
            [n IN nodes(path) | n.id] AS node_ids,
            [r IN relationships(path) | r.id] AS relationship_ids,
            [r IN relationships(path) | type(r)] AS relationship_types,
            length(path) AS hops
        LIMIT $limit
    """
    async with driver.session() as session:
        result = await session.run(
            cypher,
            {
                "case_id": case_id,
                "entity_id": entity_id,
                "limit": limit,
            },
        )
        paths = []
        async for record in result:
            paths.append(
                {
                    "node_ids": list(record["node_ids"]),
                    "relationship_ids": list(record["relationship_ids"]),
                    "relationship_types": list(record["relationship_types"]),
                    "hops": int(record["hops"]),
                }
            )
        return paths


async def bounded_pair_paths(
    graph_store: GraphStore,
    case_id: str,
    source_id: str,
    target_id: str,
    max_hops: int,
    limit: int,
) -> list[dict[str, object]]:
    """Shortest paths between two entities of length 2 .. max_hops (no direct edge)."""
    if max_hops < 2:
        return []
    driver: AsyncDriver = graph_store.driver()
    # allShortestPaths only allows a minimal length of 0 or 1; strip direct
    # edges by filtering for hops >= 2 after the search.
    cypher = f"""
        MATCH (start:Entity {{id: $source_id, case_id: $case_id}})
        MATCH (end:Entity {{id: $target_id, case_id: $case_id}})
        MATCH path = allShortestPaths(
            (start)-{_rel_pattern(1, max_hops)}-(end)
        )
        WHERE length(path) >= 2
        WITH path
        ORDER BY length(path)
        RETURN
            [n IN nodes(path) | n.id] AS node_ids,
            [r IN relationships(path) | r.id] AS relationship_ids,
            [r IN relationships(path) | type(r)] AS relationship_types,
            length(path) AS hops
        LIMIT $limit
    """
    async with driver.session() as session:
        result = await session.run(
            cypher,
            {
                "case_id": case_id,
                "source_id": source_id,
                "target_id": target_id,
                "limit": limit,
            },
        )
        paths = []
        async for record in result:
            paths.append(
                {
                    "node_ids": list(record["node_ids"]),
                    "relationship_ids": list(record["relationship_ids"]),
                    "relationship_types": list(record["relationship_types"]),
                    "hops": int(record["hops"]),
                }
            )
        return paths
