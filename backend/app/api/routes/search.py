"""Routes: unified case-scoped search across entities, evidence, findings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_case_or_404, require_permission
from app.core import rbac
from app.db.postgres import get_db_session
from app.models import User
from app.services import search as search_svc

router = APIRouter(prefix="/cases", tags=["search"])


class SearchResultOut(BaseModel):
    kind: str
    id: str
    title: str
    subtitle: str | None
    url: str


class SearchResponse(BaseModel):
    items: list[SearchResultOut]
    total: int
    limit: int
    offset: int


@router.get("/{case_id}/search", response_model=SearchResponse)
async def case_search(
    case_id: uuid.UUID,
    request: Request,
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> SearchResponse:
    await get_case_or_404(case_id, request, session)
    result = await search_svc.search(
        session=session,
        case_id=case_id,
        query=q,
        limit=limit,
        offset=offset,
    )
    return SearchResponse(
        items=[
            SearchResultOut(
                kind=s.kind,
                id=s.id,
                title=s.title,
                subtitle=s.subtitle,
                url=s.url,
            )
            for s in result.items
        ],
        total=result.total,
        limit=limit,
        offset=offset,
    )
