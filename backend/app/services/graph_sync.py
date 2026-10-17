"""Idempotent Neo4j graph projection from PostgreSQL-resolved entities.

MERGE is used everywhere so re-syncing a case is always safe: nodes are keyed
by their PostgreSQL entity id and edges by their relationship id. Sub-labels
mirror the entity type (``:Entity:PERSON``) for efficient typed traversals.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TypedDict

from neo4j import AsyncDriver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.neo4j import GraphStore
from app.models import Entity, EntityAlias, Relationship
from app.models.relationship import RELATIONSHIP_TYPES

logger = logging.getLogger(__name__)


class RelationshipPayload(TypedDict):
    """One edge projected into Neo4j during a case graph sync."""

    id: str
    case_id: str
    source: str
    target: str
    type: str
    confidence: float | None
    explanation: str | None
    created_at: str


def _assert_legal_relationship_types(payload: list[RelationshipPayload]) -> None:
    """A11: guard the only interpolated Cypher fragment (the relationship
    label). PostgreSQL constrains these values today, but explicit defence-in-
    depth means a future looser type cannot inject Cypher."""
    allowed = {t.upper() for t in RELATIONSHIP_TYPES}
    for edge in payload:
        label = edge["type"]
        if label not in allowed:
            raise ValueError(f"illegal relationship type for graph sync: {label!r}")


async def load_alias_map(
    session: AsyncSession, entity_ids: list[str]
) -> dict[str, list[str]]:
    """Batch-load alias values (one query) so projections carry identity
    context — including Phase 3 reviewed ``resolution`` aliases."""
    if not entity_ids:
        return {}
    result = await session.execute(
        select(EntityAlias.entity_id, EntityAlias.alias_value).where(
            EntityAlias.entity_id.in_(entity_ids)
        )
    )
    alias_map: dict[str, list[str]] = {}
    for entity_id, alias_value in result.all():
        alias_map.setdefault(str(entity_id), []).append(str(alias_value))
    return alias_map


class GraphSyncService:
    def __init__(self, graph_store: GraphStore, settings: Settings) -> None:
        self._graph_store = graph_store
        self._chunk_size = settings.GRAPH_CHUNK_SIZE

    def driver(self) -> AsyncDriver:
        return self._graph_store.driver()

    async def ensure_indexes(self) -> None:
        """Create the uniqueness constraints that make MERGE idempotent."""
        constraints = (
            "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS "
            "FOR (n:Entity) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT entity_key_unique IF NOT EXISTS "
            "FOR (n:Entity) REQUIRE (n.case_id, n.entity_type, n.canonical_value) IS UNIQUE",
            "CREATE INDEX entity_case_index IF NOT EXISTS FOR (n:Entity) ON (n.case_id)",
        )
        async with self.driver().session() as session:
            for statement in constraints:
                await session.run(statement)

    async def sync_nodes(
        self,
        entities: list[Entity],
        case_id: uuid.UUID,
        aliases_by_entity: dict[str, list[str]] | None = None,
    ) -> int:
        await self.ensure_indexes()
        alias_map = aliases_by_entity or {}
        payload = [
            {
                "id": str(entity.id),
                "case_id": str(case_id),
                "entity_type": entity.entity_type,
                "canonical_value": entity.canonical_value,
                "display_value": entity.display_value,
                "status": entity.status,
                "confidence": entity.confidence,
                "aliases": sorted(set(alias_map.get(str(entity.id), []))),
            }
            for entity in entities
        ]
        if not payload:
            return 0
        async with self.driver().session() as session:
            for start in range(0, len(payload), self._chunk_size):
                chunk = payload[start : start + self._chunk_size]
                await session.run(
                    """
                    UNWIND $batch AS row
                    MERGE (n:Entity {id: row.id})
                    ON CREATE SET
                        n.case_id = row.case_id,
                        n.entity_type = row.entity_type,
                        n.canonical_value = row.canonical_value,
                        n.display_value = row.display_value,
                        n.status = row.status,
                        n.confidence = row.confidence,
                        n.aliases = row.aliases
                    ON MATCH SET
                        n.case_id = row.case_id,
                        n.entity_type = row.entity_type,
                        n.canonical_value = row.canonical_value,
                        n.display_value = row.display_value,
                        n.status = row.status,
                        n.confidence = row.confidence,
                        n.aliases = row.aliases
                    """,
                    {"batch": chunk},
                )
        return len(payload)

    async def sync_edges(
        self,
        relationships: list[Relationship],
        case_id: uuid.UUID,
    ) -> int:
        now = datetime.now(UTC).isoformat()
        payload: list[RelationshipPayload] = [
            {
                "id": str(rel.id),
                "case_id": str(case_id),
                "source": str(rel.source_entity_id),
                "target": str(rel.target_entity_id),
                "type": rel.relationship_type.upper(),
                "confidence": rel.confidence,
                "explanation": rel.explanation,
                "created_at": now,
            }
            for rel in relationships
        ]
        if not payload:
            return 0
        # A11: the relationship label is the only interpolated Cypher fragment.
        _assert_legal_relationship_types(payload)
        async with self.driver().session() as session:
            for start in range(0, len(payload), self._chunk_size):
                chunk = payload[start : start + self._chunk_size]
                for edge in chunk:
                    await session.run(
                        f"""
                        MATCH (a:Entity {{id: $source}})
                        MATCH (b:Entity {{id: $target}})
                        MERGE (a)-[r:{edge["type"]}]->(b)
                        ON CREATE SET
                            r.id = $id,
                            r.case_id = $case_id,
                            r.confidence = $confidence,
                            r.explanation = $explanation,
                            r.created_at = $created_at
                        ON MATCH SET
                            r.id = $id,
                            r.case_id = $case_id,
                            r.confidence = $confidence,
                            r.explanation = $explanation,
                            r.created_at = $created_at
                        """,
                        dict(edge),
                    )
        return len(payload)

    async def prune_duplicate_edges(self, case_id: uuid.UUID, canonical_edge_ids: list[str]) -> int:
        """Collapse the Neo4j projection to one canonical edge per node pair.

        Edge identity is ``(source, target, type)``: PostgreSQL guarantees one
        canonical relationship row per logical edge (unique constraint), and
        ``sync_edges`` merges on those endpoints, but legacy projections (or
        anything writing before the constraint existed) may carry several edges
        for the same logical relationship. This keeps exactly one — preferring
        edges whose ``id`` is a canonical relationship id — and deletes the rest.
        """
        async with self.driver().session() as session:
            result = await session.run(
                """
                MATCH (a:Entity {case_id: $cid})-[r]->(b:Entity {case_id: $cid})
                WITH a, b, type(r) AS t, collect(r) AS rs
                WHERE size(rs) > 1
                UNWIND rs AS edge
                WITH a, b, t, edge
                ORDER BY CASE WHEN edge.id IN $ids THEN 0 ELSE 1 END, edge.id
                WITH a, b, t, collect(edge) AS ordered
                UNWIND ordered[1..] AS edge
                DETACH DELETE edge
                RETURN count(*) AS removed
                """,
                {"cid": str(case_id), "ids": canonical_edge_ids},
            )
            record = await result.single()
            return int(record["removed"]) if record else 0

    async def sync_case(
        self,
        *,
        case_id: uuid.UUID,
        entities: list[Entity],
        relationships: list[Relationship],
        aliases_by_entity: dict[str, list[str]] | None = None,
    ) -> tuple[int, int]:
        nodes = await self.sync_nodes(entities, case_id, aliases_by_entity)
        edges = await self.sync_edges(relationships, case_id)
        removed = await self.prune_duplicate_edges(case_id, [str(rel.id) for rel in relationships])
        if removed:
            logger.info(
                "pruned %d duplicate graph edges",
                removed,
                extra={"case_id": str(case_id)},
            )
        logger.info(
            "graph sync complete",
            extra={"case_id": str(case_id), "nodes": nodes, "edges": edges},
        )
        return nodes, edges

    async def sync_entities_by_id(self, session: AsyncSession, entity_ids: list[str]) -> int:
        """Targeted refresh of specific entities (with their aliases) in the
        projection.

        Used by write paths that change entities *after* ingestion — review
        approvals (additive aliases) and merges (status flips) — so the graph
        never serves a stale identity view. Reads the canonical rows from
        PostgreSQL (post-commit truth) and reuses the idempotent MERGE. Raises
        on driver failure so callers can surface ``graph_synced: false``
        instead of pretending the projection is current.
        """
        ids = [eid for eid in entity_ids if eid]
        if not ids:
            return 0
        result = await session.execute(select(Entity).where(Entity.id.in_(ids)))
        entities = list(result.scalars())
        if not entities:
            return 0
        alias_map = await load_alias_map(session, ids)
        nodes = 0
        by_case: dict[str, list[Entity]] = {}
        for entity in entities:
            by_case.setdefault(str(entity.case_id), []).append(entity)
        for case_id, group in by_case.items():
            nodes += await self.sync_nodes(
                group,
                uuid.UUID(case_id),
                {str(entity.id): alias_map.get(str(entity.id), []) for entity in group},
            )
        return nodes

    async def delete_case(self, case_id: uuid.UUID) -> tuple[int, int]:
        """Remove every node and relationship of a case from the projection.

        Case removal is not yet an API operation, but cleanup / maintenance
        tooling calls this so a PostgreSQL case deletion never leaves orphaned
        graph state (A02). Deleting relationships first is only an
        optimisation: ``DETACH DELETE`` also clears any incident edges.
        """
        cid = str(case_id)
        async with self.driver().session() as session:
            rel_result = await session.run(
                """
                MATCH (n:Entity {case_id: $cid})-[r]->()
                DELETE r
                RETURN count(r) AS removed
                """,
                {"cid": cid},
            )
            rel_record = await rel_result.single()
            edges = int(rel_record["removed"]) if rel_record else 0
            node_result = await session.run(
                """
                MATCH (n:Entity {case_id: $cid})
                DETACH DELETE n
                RETURN count(n) AS removed
                """,
                {"cid": cid},
            )
            node_record = await node_result.single()
            nodes = int(node_record["removed"]) if node_record else 0
        logger.info(
            "graph case removed",
            extra={"case_id": cid, "nodes": nodes, "edges": edges},
        )
        return nodes, edges

    async def case_graph(
        self, case_id: uuid.UUID
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """Read back the projected graph for a case as (nodes, edges)."""
        async with self.driver().session() as session:
            node_result = await session.run(
                "MATCH (n:Entity) WHERE n.case_id = $case_id RETURN n ORDER BY n.id",
                {"case_id": str(case_id)},
            )
            nodes = []
            async for record in node_result:
                props = record["n"]
                nodes.append(
                    {
                        "id": props["id"],
                        "entity_type": props["entity_type"],
                        "canonical_value": props["canonical_value"],
                        "display_value": props["display_value"],
                        "status": props["status"],
                        "confidence": props.get("confidence"),
                        "aliases": list(props.get("aliases") or []),
                    }
                )
            edge_result = await session.run(
                """
                MATCH (n:Entity {case_id: $case_id})-[r]->(m:Entity {case_id: $case_id})
                RETURN r, startNode(r).id AS source, endNode(r).id AS target,
                       type(r) AS relationship_type, r.id AS id
                ORDER BY r.id
                """,
                {"case_id": str(case_id)},
            )
            edges = []
            async for record in edge_result:
                edges.append(
                    {
                        "id": record["id"],
                        "source": record["source"],
                        "target": record["target"],
                        "relationship_type": record["relationship_type"].lower(),
                        "confidence": record["r"].get("confidence"),
                    }
                )
            return nodes, edges
