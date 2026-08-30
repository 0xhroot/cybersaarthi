"""Data access for the append-only audit log."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_logs(
        self,
        *,
        case_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        """Newest-first audit entries matching the optional filters."""
        filters = []
        if case_id is not None:
            filters.append(AuditLog.case_id == case_id)
        if actor_id is not None:
            filters.append(AuditLog.actor_id == actor_id)
        if action:
            filters.append(AuditLog.action == action)
        if resource_type:
            filters.append(AuditLog.resource_type == resource_type)
        base = select(AuditLog).where(*filters)
        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        result = await self._session.execute(
            base.order_by(AuditLog.created_at.desc(), AuditLog.id).limit(limit).offset(offset)
        )
        return list(result.scalars()), int(total or 0)
