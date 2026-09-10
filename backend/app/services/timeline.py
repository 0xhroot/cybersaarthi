"""Timeline service: record and query case events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TimelineEvent


async def record_event(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    occurred_at: datetime,
    kind: str,
    title: str,
    description: str | None = None,
    entity_id: uuid.UUID | None = None,
    evidence_file_id: uuid.UUID | None = None,
    collection_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> TimelineEvent:
    event = TimelineEvent(
        case_id=str(case_id),
        occurred_at=occurred_at,
        kind=kind,
        title=title,
        description=description,
        entity_id=str(entity_id) if entity_id else None,
        evidence_file_id=str(evidence_file_id) if evidence_file_id else None,
        collection_id=str(collection_id) if collection_id else None,
        device_id=str(device_id) if device_id else None,
        actor_user_id=str(actor_user_id) if actor_user_id else None,
        payload=payload,
    )
    session.add(event)
    await session.flush()
    return event


async def list_events(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    kind: str | None = None,
    entity_id: uuid.UUID | None = None,
    evidence_file_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[TimelineEvent], int]:
    where = [TimelineEvent.case_id == str(case_id)]
    if kind is not None:
        where.append(TimelineEvent.kind == kind)
    if entity_id is not None:
        where.append(TimelineEvent.entity_id == str(entity_id))
    if evidence_file_id is not None:
        where.append(TimelineEvent.evidence_file_id == str(evidence_file_id))
    if device_id is not None:
        where.append(TimelineEvent.device_id == str(device_id))
    if from_at is not None:
        where.append(TimelineEvent.occurred_at >= from_at)
    if to_at is not None:
        where.append(TimelineEvent.occurred_at <= to_at)
    count_q = select(func.count()).select_from(TimelineEvent).where(*where)
    total = (await session.execute(count_q)).scalar_one()
    q = (
        select(TimelineEvent)
        .where(*where)
        .order_by(TimelineEvent.occurred_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list((await session.execute(q)).scalars())
    return rows, total
