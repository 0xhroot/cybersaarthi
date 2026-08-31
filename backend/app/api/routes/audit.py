"""Routes: append-only audit log (readable by authorized roles)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_roles, require_permission
from app.core.rbac import PERM_AUDIT_READ, is_admin_role
from app.db.postgres import get_db_session
from app.models import Case, User
from app.repositories.audit_repository import AuditRepository
from app.schemas.audit import AuditLogListResponse, AuditLogOut

router = APIRouter(prefix="/audit-logs", tags=["audit"])


async def _owned_case_ids(user_id: uuid.UUID, session: AsyncSession) -> list[uuid.UUID]:
    result = await session.execute(select(Case.id).where(Case.owner_id == user_id))
    return list(result.scalars())


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    case_id: uuid.UUID | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission(PERM_AUDIT_READ)),
    roles: list[str] = Depends(get_current_roles),
    session: AsyncSession = Depends(get_db_session),
) -> AuditLogListResponse:
    """Return security-relevant events, newest first and filterable.

    A04: ADMIN sees the global log; every other audit.read holder is scoped
    to events on cases they own, so login timings and mutations of other
    users' cases stay confidential.
    """
    allowed_case_ids: list[uuid.UUID] | None = None
    own_actor_id: uuid.UUID | None = None
    if not any(is_admin_role(role) for role in roles):
        allowed_case_ids = await _owned_case_ids(user.id, session)
        own_actor_id = user.id
    items, total = await AuditRepository(session).list_logs(
        case_id=case_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        allowed_case_ids=allowed_case_ids,
        own_actor_id=own_actor_id,
        limit=limit,
        offset=offset,
    )
    return AuditLogListResponse(
        items=[
            AuditLogOut(
                id=log.id,
                actor_id=log.actor_id,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                case_id=log.case_id,
                metadata_=log.metadata_,
                created_at=log.created_at,
            )
            for log in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
