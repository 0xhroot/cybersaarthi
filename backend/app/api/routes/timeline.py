"""Routes: investigation timeline (case-scoped)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_case_or_404, require_permission
from app.core import rbac
from app.db.postgres import get_db_session
from app.models import TimelineEvent, User
from app.services import timeline as tl_svc

router = APIRouter(prefix="/cases", tags=["timeline"])


class TimelineEventCreateRequest(BaseModel):
    occurred_at: datetime
    kind: str
    title: str
    description: str | None = None
    entity_id: uuid.UUID | None = None
    evidence_file_id: uuid.UUID | None = None
    collection_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    payload: dict[str, Any] | None = None


class TimelineEventOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    occurred_at: datetime
    kind: str
    title: str
    description: str | None
    entity_id: uuid.UUID | None
    evidence_file_id: uuid.UUID | None
    collection_id: uuid.UUID | None
    device_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    payload: dict[str, Any] | None
    created_at: datetime


class TimelineEventListResponse(BaseModel):
    items: list[TimelineEventOut]
    total: int
    limit: int
    offset: int


def _event_out(e: TimelineEvent) -> TimelineEventOut:
    return TimelineEventOut(
        id=e.id,
        case_id=uuid.UUID(str(e.case_id)),
        occurred_at=e.occurred_at,
        kind=e.kind,
        title=e.title,
        description=e.description,
        entity_id=uuid.UUID(str(e.entity_id)) if e.entity_id else None,
        evidence_file_id=uuid.UUID(str(e.evidence_file_id)) if e.evidence_file_id else None,
        collection_id=uuid.UUID(str(e.collection_id)) if e.collection_id else None,
        device_id=uuid.UUID(str(e.device_id)) if e.device_id else None,
        actor_user_id=uuid.UUID(str(e.actor_user_id)) if e.actor_user_id else None,
        payload=e.payload,
        created_at=e.created_at,
    )


@router.post(
    "/{case_id}/timeline",
    response_model=TimelineEventOut,
    status_code=201,
)
async def create_timeline_event(
    case_id: uuid.UUID,
    body: TimelineEventCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
) -> TimelineEventOut:
    from app.api.dependencies import assert_case_investigation_mutable

    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    event = await tl_svc.record_event(
        session=session,
        case_id=case_id,
        occurred_at=body.occurred_at,
        kind=body.kind,
        title=body.title,
        description=body.description,
        entity_id=body.entity_id,
        evidence_file_id=body.evidence_file_id,
        collection_id=body.collection_id,
        device_id=body.device_id,
        actor_user_id=user.id,
        payload=body.payload,
    )
    await session.commit()
    return _event_out(event)


@router.get("/{case_id}/timeline", response_model=TimelineEventListResponse)
async def list_timeline_events(
    case_id: uuid.UUID,
    request: Request,
    kind: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    evidence_file_id: uuid.UUID | None = Query(default=None),
    device_id: uuid.UUID | None = Query(default=None),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> TimelineEventListResponse:
    await get_case_or_404(case_id, request, session)
    rows, total = await tl_svc.list_events(
        session=session,
        case_id=case_id,
        kind=kind,
        entity_id=entity_id,
        evidence_file_id=evidence_file_id,
        device_id=device_id,
        from_at=from_at,
        to_at=to_at,
        limit=limit,
        offset=offset,
    )
    return TimelineEventListResponse(
        items=[_event_out(e) for e in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
