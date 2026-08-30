"""Routes: case management.

Cases belong to a single owner (creator) and are invisible to everyone else
unless they hold the ``ADMIN`` role. Read/list require ``case.read``; mutation
endpoints require their specific permission (``case.create`` / ``case.update``
/ ``case.archive``). ``case_number`` is derived deterministically from the
server-generated id, so the API always returns a stable, unique reference.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_case_or_404,
    require_permission,
)
from app.core import rbac
from app.core.rbac import is_admin_role
from app.db.postgres import get_db_session
from app.models import Case, User
from app.schemas.cases import (
    CaseCreateRequest,
    CaseListResponse,
    CaseOut,
    CaseUpdateRequest,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/cases", tags=["cases"])


def _case_out(case: Case) -> CaseOut:
    return CaseOut(
        id=case.id,
        case_number=case.case_number,
        title=case.title,
        description=case.description,
        status=case.status,
        owner_id=case.owner_id,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def _derive_case_number(case_id: uuid.UUID) -> str:
    return f"CS-{case_id.hex[:8].upper()}"


async def _accessible_case_ids(
    session: AsyncSession,
    user: User,
    user_roles: list[str],
) -> list[uuid.UUID]:
    if any(is_admin_role(role) for role in user_roles):
        result = await session.execute(select(Case.id).order_by(Case.created_at.desc(), Case.id))
    else:
        result = await session.execute(
            select(Case.id)
            .where(Case.owner_id == user.id)
            .order_by(Case.created_at.desc(), Case.id)
        )
    return list(result.scalars())


@router.get("", response_model=CaseListResponse)
async def list_cases(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> CaseListResponse:
    """List the cases the caller can access (owner or admin)."""
    roles = getattr(request.state, "roles", None) or []
    accessible = await _accessible_case_ids(session, user, roles)
    total = len(accessible)
    page_ids = accessible[offset : offset + limit]
    items: list[Case] = []
    if page_ids:
        result = await session.execute(select(Case).where(Case.id.in_(page_ids)))
        cases_by_id = {case.id: case for case in result.scalars()}
        items = [cases_by_id[cid] for cid in page_ids]
    return CaseListResponse(
        items=[_case_out(case) for case in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=CaseOut, status_code=201)
async def create_case(
    payload: CaseCreateRequest,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_CREATE)),
    session: AsyncSession = Depends(get_db_session),
) -> CaseOut:
    """Create a case owned by the caller."""
    case = Case(
        id=uuid.uuid4(),
        case_number=payload.case_number or _derive_case_number(uuid.uuid4()),
        title=payload.title,
        description=payload.description,
        status=payload.status,
        owner_id=user.id,
    )
    session.add(case)
    await session.flush()
    await record_audit(
        session,
        actor_id=user.id,
        action="case.created",
        resource_type="case",
        resource_id=case.id,
        case_id=case.id,
        metadata={"title": case.title, "case_number": case.case_number},
    )
    await session.commit()
    await session.refresh(case)
    return _case_out(case)


@router.get("/{case_id}", response_model=CaseOut)
async def get_case(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> CaseOut:
    """A single case the caller may access."""
    case = await get_case_or_404(case_id, request, session)
    return _case_out(case)


@router.patch("/{case_id}", response_model=CaseOut)
async def update_case(
    case_id: uuid.UUID,
    payload: CaseUpdateRequest,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> CaseOut:
    """Update editable case fields (open/in_progress/closed via PATCH)."""
    case = await get_case_or_404(case_id, request, session)
    if payload.status == "archived":
        raise HTTPException(status_code=422, detail="use the archive endpoint to archive a case")
    changes: dict[str, object] = {}
    if payload.title is not None and payload.title != case.title:
        changes["title"] = payload.title
    if "description" in payload.model_dump(exclude_unset=True):
        if payload.description != case.description:
            changes["description"] = payload.description
    if payload.status is not None and payload.status != case.status:
        changes["status"] = payload.status
    if not changes:
        return _case_out(case)
    for field, value in changes.items():
        setattr(case, field, value)
    await record_audit(
        session,
        actor_id=user.id,
        action="case.updated",
        resource_type="case",
        resource_id=case.id,
        case_id=case.id,
        metadata={"changes": changes},
    )
    await session.commit()
    await session.refresh(case)
    return _case_out(case)


@router.post("/{case_id}/archive", response_model=CaseOut)
async def archive_case(
    case_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_ARCHIVE)),
    session: AsyncSession = Depends(get_db_session),
) -> CaseOut:
    """Archive a case (status ``archived``; irreversible through the API)."""
    case = await get_case_or_404(case_id, request, session)
    previous_status = case.status
    case.status = "archived"
    await record_audit(
        session,
        actor_id=user.id,
        action="case.archived",
        resource_type="case",
        resource_id=case.id,
        case_id=case.id,
        metadata={"from_status": previous_status},
    )
    await session.commit()
    await session.refresh(case)
    return _case_out(case)
