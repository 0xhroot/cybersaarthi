"""Data access for the append-only audit log."""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, and_, func, or_, select
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
        allowed_case_ids: list[uuid.UUID] | None = None,
        own_actor_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        """Newest-first audit entries matching the optional filters.

        *allowed_case_ids* scopes the result to events on those cases. When
        combined with *own_actor_id*, the caller also keeps their own global
        events (login success/failure have no case) but nothing else (A04).
        """
        filters = []
        if case_id is not None:
            filters.append(AuditLog.case_id == case_id)
        if actor_id is not None:
            filters.append(AuditLog.actor_id == actor_id)
        if action:
            filters.append(AuditLog.action == action)
        if resource_type:
            filters.append(AuditLog.resource_type == resource_type)
        if allowed_case_ids is not None:
            scope: ColumnElement[bool] = AuditLog.case_id.in_(allowed_case_ids)
            if own_actor_id is not None:
                scope = or_(
                    scope,
                    and_(AuditLog.case_id.is_(None), AuditLog.actor_id == own_actor_id),
                )
            filters.append(scope)
        base = select(AuditLog).where(*filters)
        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        result = await self._session.execute(
            base.order_by(AuditLog.created_at.desc(), AuditLog.id).limit(limit).offset(offset)
        )
        return list(result.scalars()), int(total or 0)
