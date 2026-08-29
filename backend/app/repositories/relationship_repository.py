"""Data access for relationships and relationship evidence."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Relationship, RelationshipEvidence


class RelationshipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_relationship(
        self,
        *,
        case_id: uuid.UUID,
        source_entity_id: uuid.UUID,
        target_entity_id: uuid.UUID,
        relationship_type: str,
        confidence: float | None,
        source_record_id: uuid.UUID,
        context: dict[str, object] | None,
        explanation: str | None,
    ) -> Relationship | None:
        """Create one canonical relationship row per logical edge.

        ``(case_id, source_entity_id, target_entity_id, relationship_type)``
        uniquely identifies a logical relationship regardless of which record or
        evidence mechanism discovered it (``source_record_id`` is deliberately
        outside the unique key). Returns ``None`` when the canonical row already
        exists — callers then attach their evidence to that row instead of
        creating a duplicate graph edge.
        """
        statement = (
            pg_insert(Relationship)
            .values(
                case_id=str(case_id),
                source_entity_id=str(source_entity_id),
                target_entity_id=str(target_entity_id),
                relationship_type=relationship_type,
                confidence=confidence,
                source_record_id=str(source_record_id),
                context=context,
                explanation=explanation,
            )
            .on_conflict_do_nothing(
                constraint="uq_relationships_case_src_dst_type",
            )
            .returning(Relationship.id)
        )
        result = await self._session.execute(statement)
        relationship_id = result.scalar_one_or_none()
        if relationship_id is None:
            return None
        return await self._session.get(Relationship, relationship_id)

    async def get_relationship(
        self,
        *,
        case_id: uuid.UUID,
        source_entity_id: uuid.UUID,
        target_entity_id: uuid.UUID,
        relationship_type: str,
    ) -> Relationship | None:
        """Fetch the canonical relationship row for a logical edge, if any."""
        result = await self._session.execute(
            select(Relationship).where(
                Relationship.case_id == str(case_id),
                Relationship.source_entity_id == str(source_entity_id),
                Relationship.target_entity_id == str(target_entity_id),
                Relationship.relationship_type == relationship_type,
            )
        )
        return result.scalar_one_or_none()

    async def create_relationship_evidence(
        self,
        *,
        relationship_id: uuid.UUID,
        source_record_id: uuid.UUID | None,
        evidence_type: str,
        snippet: str | None,
    ) -> None:
        statement = (
            pg_insert(RelationshipEvidence)
            .values(
                relationship_id=str(relationship_id),
                source_record_id=str(source_record_id) if source_record_id else None,
                evidence_type=evidence_type,
                snippet=snippet,
            )
            .on_conflict_do_nothing(
                constraint="uq_relationship_evidence_rel_record_type",
            )
        )
        await self._session.execute(statement)

    async def list_relationships(self, case_id: uuid.UUID, limit: int = 1000) -> list[Relationship]:
        result = await self._session.execute(
            select(Relationship)
            .where(Relationship.case_id == str(case_id))
            .order_by(Relationship.created_at)
            .limit(limit)
        )
        return list(result.scalars())

    async def list_evidence(self, relationship_id: uuid.UUID) -> list[RelationshipEvidence]:
        """Provenance rows recorded against one canonical relationship."""
        result = await self._session.execute(
            select(RelationshipEvidence)
            .where(RelationshipEvidence.relationship_id == str(relationship_id))
            .order_by(RelationshipEvidence.created_at)
        )
        return list(result.scalars())

    async def count_relationships(self, case_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count(Relationship.id)).where(Relationship.case_id == str(case_id))
        )
        return int(result.scalar_one())

    async def count_by_type(self, case_id: uuid.UUID) -> dict[str, int]:
        rows = await self._session.execute(
            select(Relationship.relationship_type, func.count())
            .where(Relationship.case_id == str(case_id))
            .group_by(Relationship.relationship_type)
        )
        return {relationship_type: int(count) for relationship_type, count in rows.all()}
