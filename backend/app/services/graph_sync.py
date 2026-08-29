"""Idempotent Neo4j graph projection from PostgreSQL-resolved entities.

MERGE is used everywhere so re-syncing a case is always safe: nodes are keyed
by their PostgreSQL entity id and edges by their relationship id. Sub-labels
mirror the entity type (``:Entity:PERSON``) for efficient typed traversals.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from neo4j import AsyncDriver

from app.core.config import Settings
from app.db.neo4j import GraphStore
from app.models import Entity, Relationship

logger = logging.getLogger(__name__)


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

    async def sync_nodes(self, entities: list[Entity], case_id: uuid.UUID) -> int:
        await self.ensure_indexes()
        payload = [
            {
                "id": str(entity.id),
                "case_id": str(case_id),
                "entity_type": entity.entity_type,
                "canonical_value": entity.canonical_value,
                "display_value": entity.display_value,
                "status": entity.status,
                "confidence": entity.confidence,
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
                        n.confidence = row.confidence
                    ON MATCH SET
                        n.case_id = row.case_id,
                        n.entity_type = row.entity_type,
                        n.canonical_value = row.canonical_value,
                        n.display_value = row.display_value,
                        n.status = row.status,
                        n.confidence = row.confidence
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
        payload = [
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
                        edge,
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
    ) -> tuple[int, int]:
        nodes = await self.sync_nodes(entities, case_id)
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
