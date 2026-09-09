"""Data access for entities, aliases, candidates and resolution matches."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, EntityAlias, EntityCandidate, EntityMatch


class EntityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # Entities -------------------------------------------------------------
    async def get_entity(self, entity_id: uuid.UUID) -> Entity | None:
        return await self._session.get(Entity, entity_id)

    async def find_by_blocking_key(
        self,
        *,
        case_id: uuid.UUID,
        entity_type: str,
        blocking_key: str,
        limit: int = 25,
    ) -> list[Entity]:
        result = await self._session.execute(
            select(Entity)
            .where(
                Entity.case_id == str(case_id),
                Entity.entity_type == entity_type,
                Entity.blocking_key == blocking_key,
                Entity.status == "active",
            )
            .limit(limit)
        )
        return list(result.scalars())

    async def create_entity(
        self,
        *,
        case_id: uuid.UUID,
        entity_type: str,
        canonical_value: str,
        blocking_key: str,
        display_value: str,
        confidence: float | None,
        status: str = "active",
    ) -> Entity:
        """Create an entity or return the existing one with the same key (A08).

        Concurrency-safe: two workers ingesting the same new canonical value
        race on ``uq_entities_case_type_value``; ``on_conflict_do_nothing``
        makes one insert win and the other refetch the row instead of raising
        an ``IntegrityError``. Callers rely on the returned ORM instance.
        """
        statement = (
            pg_insert(Entity)
            .values(
                case_id=str(case_id),
                entity_type=entity_type,
                canonical_value=canonical_value,
                blocking_key=blocking_key,
                display_value=display_value,
                confidence=confidence,
                status=status,
            )
            .on_conflict_do_nothing(constraint="uq_entities_case_type_value")
            .returning(Entity.id)
        )
        result = await self._session.execute(statement)
        entity_id = result.scalar_one_or_none()
        if entity_id is not None:
            return await self._session.get(Entity, entity_id)  # type: ignore[return-value]
        # Another worker inserted the same key; return the existing row.
        existing = await self._session.scalar(
            select(Entity).where(
                Entity.case_id == str(case_id),
                Entity.entity_type == entity_type,
                Entity.canonical_value == canonical_value,
            )
        )
        return existing  # type: ignore[return-value]

    async def update_entity_context(
        self,
        entity_id: uuid.UUID,
        context: dict[str, object],
    ) -> None:
        entity = await self._session.get(Entity, entity_id)
        if entity is None:
            return
        entity.context = context
        await self._session.flush()

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
        filters = [Entity.case_id == str(case_id)]
        if entity_type:
            filters.append(Entity.entity_type == entity_type)
        if status:
            filters.append(Entity.status == status)
        if query:
            filters.append(Entity.display_value.ilike(f"%{query}%"))

        base = select(Entity).where(*filters)
        count_value = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        result = await self._session.execute(
            base.order_by(Entity.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars()), int(count_value or 0)

    async def count_entities_by_type(self, case_id: uuid.UUID) -> dict[str, int]:
        rows = await self._session.execute(
            select(Entity.entity_type, func.count())
            .where(Entity.case_id == str(case_id))
            .group_by(Entity.entity_type)
        )
        return {entity_type: int(count) for entity_type, count in rows.all()}

    # Aliases --------------------------------------------------------------
    async def add_alias(
        self,
        *,
        entity_id: uuid.UUID,
        alias_value: str,
        alias_type: str = "value",
        source_record_id: uuid.UUID | None = None,
    ) -> EntityAlias | None:
        statement = (
            pg_insert(EntityAlias)
            .values(
                entity_id=str(entity_id),
                alias_value=alias_value,
                alias_type=alias_type,
                source_record_id=str(source_record_id) if source_record_id else None,
            )
            .on_conflict_do_nothing(constraint="uq_entity_aliases_entity_value")
            .returning(EntityAlias.id)
        )
        result = await self._session.execute(statement)
        alias_id = result.scalar_one_or_none()
        if alias_id is None:
            return None
        return await self._session.get(EntityAlias, alias_id)

    async def get_aliases(self, entity_id: uuid.UUID) -> list[EntityAlias]:
        result = await self._session.execute(
            select(EntityAlias)
            .where(EntityAlias.entity_id == str(entity_id))
            .order_by(EntityAlias.alias_value)
        )
        return list(result.scalars())

    async def get_aliases_bulk(
        self,
        entity_ids: list[uuid.UUID],
    ) -> dict[str, list[EntityAlias]]:
        """Aliases for many entities in one query, grouped by entity id."""
        if not entity_ids:
            return {}
        result = await self._session.execute(
            select(EntityAlias)
            .where(EntityAlias.entity_id.in_([str(entity_id) for entity_id in entity_ids]))
            .order_by(EntityAlias.alias_value)
        )
        grouped: dict[str, list[EntityAlias]] = {}
        for alias in result.scalars():
            grouped.setdefault(str(alias.entity_id), []).append(alias)
        return grouped

    # Candidates -----------------------------------------------------------
    async def create_candidate(
        self,
        *,
        source_record_id: uuid.UUID,
        entity_type: str,
        raw_value: str,
        normalized_value: str,
        blocking_key: str,
        confidence: float | None,
        source: str,
        context: dict[str, object] | None,
    ) -> EntityCandidate | None:
        statement = (
            pg_insert(EntityCandidate)
            .values(
                source_record_id=str(source_record_id),
                entity_type=entity_type,
                raw_value=raw_value,
                normalized_value=normalized_value,
                blocking_key=blocking_key,
                confidence=confidence,
                source=source,
                context=context,
            )
            .on_conflict_do_nothing(
                constraint="uq_entity_candidates_record_type_value",
            )
            .returning(EntityCandidate.id)
        )
        result = await self._session.execute(statement)
        candidate_id = result.scalar_one_or_none()
        if candidate_id is None:
            return None
        return await self._session.get(EntityCandidate, candidate_id)

    async def get_candidate(self, candidate_id: uuid.UUID) -> EntityCandidate | None:
        return await self._session.get(EntityCandidate, candidate_id)

    async def get_candidate_by_record_and_value(
        self,
        source_record_id: uuid.UUID,
        entity_type: str,
        normalized_value: str,
    ) -> EntityCandidate | None:
        result = await self._session.execute(
            select(EntityCandidate).where(
                EntityCandidate.source_record_id == str(source_record_id),
                EntityCandidate.entity_type == entity_type,
                EntityCandidate.normalized_value == normalized_value,
            )
        )
        return result.scalar_one_or_none()

    async def link_candidate(
        self,
        candidate_id: uuid.UUID,
        *,
        entity_id: uuid.UUID | None,
        resolution_status: str,
        confidence: float | None,
    ) -> None:
        candidate = await self._session.get(EntityCandidate, candidate_id)
        if candidate is None:
            return
        candidate.entity_id = str(entity_id) if entity_id else None
        candidate.resolution_status = resolution_status
        candidate.confidence = confidence
        await self._session.flush()

    # Matches --------------------------------------------------------------
    async def create_match(
        self,
        *,
        case_id: uuid.UUID,
        source_candidate_id: uuid.UUID,
        target_entity_id: uuid.UUID | None,
        decision: str,
        score: float,
        signals: dict[str, object] | None,
        status: str = "review",
    ) -> EntityMatch:
        match = EntityMatch(
            case_id=str(case_id),
            source_candidate_id=str(source_candidate_id),
            target_entity_id=str(target_entity_id) if target_entity_id else None,
            decision=decision,
            score=score,
            signals=signals,
            status=status,
        )
        self._session.add(match)
        await self._session.flush()
        return match

    async def list_matches(
        self, case_id: uuid.UUID, *, decision: str, limit: int = 200
    ) -> list[EntityMatch]:
        result = await self._session.execute(
            select(EntityMatch)
            .where(
                EntityMatch.case_id == str(case_id),
                EntityMatch.decision == decision,
            )
            .order_by(EntityMatch.score.desc())
            .limit(limit)
        )
        return list(result.scalars())
