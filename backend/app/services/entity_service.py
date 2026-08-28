"""Read-side service for entities and the projected knowledge graph."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import GraphSyncStatus
from app.models import Entity, EntityAlias, EntityMatch, Relationship
from app.repositories.entity_repository import EntityRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.repositories.relationship_repository import RelationshipRepository


class EntityQueryService:
    def __init__(
        self,
        session: AsyncSession,
        entity_repository: EntityRepository,
        evidence_repository: EvidenceRepository,
        relationship_repository: RelationshipRepository,
    ) -> None:
        self._session = session
        self._entities = entity_repository
        self._evidence = evidence_repository
        self._relationships = relationship_repository

    async def list_entities(
        self,
        *,
        case_id: uuid.UUID,
        entity_type: str | None = None,
        status: str | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Entity], int]:
        return await self._entities.list_entities(
            case_id=case_id,
            entity_type=entity_type,
            status=status,
            query=query,
            limit=limit,
            offset=offset,
        )

    async def get_entity_detail(
        self, entity_id: uuid.UUID
    ) -> tuple[Entity | None, list[EntityAlias]]:
        entity = await self._entities.get_entity(entity_id)
        if entity is None:
            return None, []
        aliases = await self._entities.get_aliases(entity_id)
        return entity, aliases

    async def review_matches(self, case_id: uuid.UUID, limit: int = 200) -> list[EntityMatch]:
        return await self._entities.list_matches(case_id, decision="review", limit=limit)

    async def review_matches_detailed(
        self, case_id: uuid.UUID, limit: int = 200
    ) -> list[dict[str, object]]:
        """Review matches enriched with candidate and target display values."""
        matches = await self.review_matches(case_id, limit=limit)
        rows: list[dict[str, object]] = []
        for match in matches:
            candidate = await self._entities.get_candidate(
                uuid.UUID(str(match.source_candidate_id))
            )
            target = None
            if match.target_entity_id:
                target = await self._entities.get_entity(uuid.UUID(str(match.target_entity_id)))
            rows.append(
                {
                    "match_id": match.id,
                    "candidate_id": match.source_candidate_id,
                    "candidate_value": candidate.raw_value if candidate else "",
                    "candidate_type": candidate.entity_type if candidate else "person",
                    "target_entity_id": match.target_entity_id,
                    "target_value": target.display_value if target else None,
                    "score": match.score,
                    "decision": match.decision,
                    "signals": match.signals,
                    "created_at": match.created_at,
                }
            )
        return rows

    async def list_relationships(self, case_id: uuid.UUID, limit: int = 1000) -> list[Relationship]:
        return await self._relationships.list_relationships(case_id, limit=limit)

    async def build_graph(self, case_id: uuid.UUID) -> dict[str, Any]:
        entities, _ = await self._entities.list_entities(case_id=case_id, limit=10000)
        relationships = await self._relationships.list_relationships(case_id, limit=10000)

        entity_ids = {str(entity.id) for entity in entities}
        valid_edges = [
            rel
            for rel in relationships
            if str(rel.source_entity_id) in entity_ids and str(rel.target_entity_id) in entity_ids
        ]

        alias_map: dict[str, list[str]] = {str(entity.id): [] for entity in entities}
        for entity in entities:
            aliases = await self._entities.get_aliases(entity.id)
            alias_map[str(entity.id)] = [alias.alias_value for alias in aliases]

        nodes = [
            {
                "id": str(entity.id),
                "entity_type": entity.entity_type,
                "canonical_value": entity.canonical_value,
                "display_value": entity.display_value,
                "status": entity.status,
                "confidence": entity.confidence,
                "aliases": alias_map.get(str(entity.id), []),
            }
            for entity in entities
        ]
        edges = [
            {
                "id": str(rel.id),
                "source": str(rel.source_entity_id),
                "target": str(rel.target_entity_id),
                "relationship_type": rel.relationship_type,
                "confidence": rel.confidence,
                "context": rel.context,
            }
            for rel in valid_edges
        ]
        return {"nodes": nodes, "edges": edges}

    async def graph_synced(self, case_id: uuid.UUID) -> bool:
        jobs = await self._evidence.list_jobs(case_id)
        return any(str(job.graph_sync_status) == GraphSyncStatus.SYNCED for job in jobs)
