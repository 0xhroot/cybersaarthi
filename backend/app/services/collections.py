"""Collection service: case-scoped evidence grouping CRUD."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Collection, EvidenceFile


async def create_collection(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    name: str,
    description: str | None,
    owner_id: uuid.UUID | None,
) -> Collection:
    collection = Collection(
        case_id=str(case_id),
        name=name,
        description=description,
        owner_id=str(owner_id) if owner_id else None,
        status="draft",
    )
    session.add(collection)
    await session.flush()
    return collection


async def get_collection(
    session: AsyncSession,
    collection_id: uuid.UUID,
) -> Collection | None:
    return await session.get(Collection, collection_id)


async def list_collections(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Collection], int]:
    where = [Collection.case_id == str(case_id)]
    if status is not None:
        where.append(Collection.status == status)
    count_q = select(func.count()).select_from(Collection).where(*where)
    total = (await session.execute(count_q)).scalar_one()
    q = (
        select(Collection)
        .where(*where)
        .order_by(Collection.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list((await session.execute(q)).scalars())
    return rows, total


async def update_collection(
    *,
    session: AsyncSession,
    collection: Collection,
    name: str | None = None,
    description: str | None = None,
) -> Collection:
    if name is not None:
        collection.name = name
    if description is not None:
        collection.description = description
    await session.flush()
    return collection


async def seal_collection(
    *,
    session: AsyncSession,
    collection: Collection,
) -> Collection:
    collection.status = "sealed"
    collection.sealed_at = datetime.now(UTC)
    await session.flush()
    return collection


async def link_evidence(
    *,
    session: AsyncSession,
    evidence: EvidenceFile,
    collection_id: uuid.UUID,
) -> EvidenceFile:
    evidence.collection_id = str(collection_id)
    await session.flush()
    return evidence


async def unlink_evidence(
    *,
    session: AsyncSession,
    evidence: EvidenceFile,
) -> EvidenceFile:
    evidence.collection_id = None
    await session.flush()
    return evidence


async def delete_collection(
    *,
    session: AsyncSession,
    collection: Collection,
) -> None:
    await session.delete(collection)
    await session.flush()
