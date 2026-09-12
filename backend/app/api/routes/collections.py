"""Routes: evidence collections (case-scoped)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    assert_case_investigation_mutable,
    get_case_or_404,
    require_permission,
)
from app.core import rbac
from app.db.postgres import get_db_session
from app.models import User
from app.services import audit as audit_svc
from app.services import collections as col_svc
from app.services.timeline import record_event

router = APIRouter(prefix="/cases", tags=["collections"])


class CollectionCreateRequest(BaseModel):
    name: str
    description: str | None = None


class CollectionUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class CollectionOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    name: str
    description: str | None
    status: str
    sealed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CollectionListResponse(BaseModel):
    items: list[CollectionOut]
    total: int
    limit: int
    offset: int


@router.post(
    "/{case_id}/collections",
    response_model=CollectionOut,
    status_code=201,
)
async def create_collection(
    case_id: uuid.UUID,
    body: CollectionCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
) -> CollectionOut:
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    col = await col_svc.create_collection(
        session=session,
        case_id=case_id,
        name=body.name,
        description=body.description,
        owner_id=user.id,
    )
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="collection.created",
        resource_type="collection",
        resource_id=col.id,
        case_id=case_id,
        metadata={"name": col.name},
    )
    await record_event(
        session=session,
        case_id=case_id,
        occurred_at=col.created_at,
        kind="collection_created",
        title=f"Collection '{col.name}' created",
        collection_id=col.id,
        actor_user_id=user.id,
    )
    await session.commit()
    return CollectionOut(
        id=col.id,
        case_id=uuid.UUID(str(col.case_id)),
        name=col.name,
        description=col.description,
        status=col.status,
        sealed_at=col.sealed_at,
        created_at=col.created_at,
        updated_at=col.updated_at,
    )


@router.get("/{case_id}/collections", response_model=CollectionListResponse)
async def list_collections(
    case_id: uuid.UUID,
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> CollectionListResponse:
    await get_case_or_404(case_id, request, session)
    rows, total = await col_svc.list_collections(
        session=session, case_id=case_id, status=status, limit=limit, offset=offset
    )
    return CollectionListResponse(
        items=[
            CollectionOut(
                id=c.id,
                case_id=uuid.UUID(str(c.case_id)),
                name=c.name,
                description=c.description,
                status=c.status,
                sealed_at=c.sealed_at,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}/collections/{collection_id}", response_model=CollectionOut)
async def get_collection(
    case_id: uuid.UUID,
    collection_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> CollectionOut:
    await get_case_or_404(case_id, request, session)
    col = await col_svc.get_collection(session, collection_id)
    if col is None or str(col.case_id) != str(case_id):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"collection {collection_id} not found")
    return CollectionOut(
        id=col.id,
        case_id=uuid.UUID(str(col.case_id)),
        name=col.name,
        description=col.description,
        status=col.status,
        sealed_at=col.sealed_at,
        created_at=col.created_at,
        updated_at=col.updated_at,
    )


@router.patch("/{case_id}/collections/{collection_id}", response_model=CollectionOut)
async def update_collection(
    case_id: uuid.UUID,
    collection_id: uuid.UUID,
    body: CollectionUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
) -> CollectionOut:
    from app.api.dependencies import assert_case_investigation_mutable

    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    col = await col_svc.get_collection(session, collection_id)
    if col is None or str(col.case_id) != str(case_id) or col.status == "sealed":
        from fastapi import HTTPException

        status_code = 404 if col is None or str(col.case_id) != str(case_id) else 409
        detail = (
            f"collection {collection_id} not found"
            if status_code == 404
            else "sealed collections cannot be modified"
        )
        raise HTTPException(status_code=status_code, detail=detail)
    await col_svc.update_collection(
        session=session, collection=col, name=body.name, description=body.description
    )
    await session.commit()
    return CollectionOut(
        id=col.id,
        case_id=uuid.UUID(str(col.case_id)),
        name=col.name,
        description=col.description,
        status=col.status,
        sealed_at=col.sealed_at,
        created_at=col.created_at,
        updated_at=col.updated_at,
    )


@router.post("/{case_id}/collections/{collection_id}/seal", response_model=CollectionOut)
async def seal_collection(
    case_id: uuid.UUID,
    collection_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
) -> CollectionOut:
    from app.api.dependencies import assert_case_investigation_mutable

    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    col = await col_svc.get_collection(session, collection_id)
    if col is None or str(col.case_id) != str(case_id):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"collection {collection_id} not found")
    col = await col_svc.seal_collection(session=session, collection=col)
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="collection.sealed",
        resource_type="collection",
        resource_id=col.id,
        case_id=case_id,
        metadata={"name": col.name},
    )
    await record_event(
        session=session,
        case_id=case_id,
        occurred_at=col.sealed_at or col.updated_at,
        kind="collection_sealed",
        title=f"Collection '{col.name}' sealed",
        collection_id=col.id,
        actor_user_id=user.id,
    )
    await session.commit()
    return CollectionOut(
        id=col.id,
        case_id=uuid.UUID(str(col.case_id)),
        name=col.name,
        description=col.description,
        status=col.status,
        sealed_at=col.sealed_at,
        created_at=col.created_at,
        updated_at=col.updated_at,
    )


@router.delete("/{case_id}/collections/{collection_id}", status_code=204)
async def delete_collection(
    case_id: uuid.UUID,
    collection_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
) -> None:
    from app.api.dependencies import assert_case_investigation_mutable

    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    col = await col_svc.get_collection(session, collection_id)
    if col is None or str(col.case_id) != str(case_id):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"collection {collection_id} not found")
    await col_svc.delete_collection(session=session, collection=col)
    await session.commit()
