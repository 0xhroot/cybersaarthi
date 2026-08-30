"""Routes: append-only audit log (readable by authorized roles)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.core.rbac import PERM_AUDIT_READ
from app.db.postgres import get_db_session
from app.repositories.audit_repository import AuditRepository
from app.schemas.audit import AuditLogListResponse, AuditLogOut

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    case_id: uuid.UUID | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: None = Depends(require_permission(PERM_AUDIT_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> AuditLogListResponse:
    """Return security-relevant events, newest first and filterable."""
    items, total = await AuditRepository(session).list_logs(
        case_id=case_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
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
