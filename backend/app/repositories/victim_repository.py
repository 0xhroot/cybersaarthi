"""Data access for victim records."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Victim


class VictimRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, victim_id: uuid.UUID) -> Victim | None:
        return await self._session.get(Victim, victim_id)

    async def create(
        self,
        *,
        case_id: uuid.UUID,
        created_by: uuid.UUID | None,
        **fields: object,
    ) -> Victim:
        victim = Victim(
            case_id=case_id,
            created_by=created_by,
            **fields,
        )
        self._session.add(victim)
        await self._session.flush()
        await self._session.refresh(victim)
        return victim

    async def update(self, victim: Victim, **fields: object) -> Victim:
        for key, value in fields.items():
            if value is not None:
                setattr(victim, key, value)
        await self._session.flush()
        await self._session.refresh(victim)
        return victim

    async def list_by_case(
        self,
        case_id: uuid.UUID,
        *,
        status: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Victim], int]:
        filters = [Victim.case_id == case_id]
        if status:
            filters.append(Victim.status == status)
        if query:
            filters.append(Victim.name.ilike(f"%{query}%"))

        base = select(Victim).where(*filters)
        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        result = await self._session.execute(
            base.order_by(Victim.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars()), int(total or 0)

    async def count_by_case(self, case_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count(Victim.id)).where(Victim.case_id == case_id)
        )
        return int(result.scalar_one())

    async def delete(self, victim: Victim) -> None:
        await self._session.delete(victim)
        await self._session.flush()
