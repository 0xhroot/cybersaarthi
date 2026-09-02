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
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_case_or_404,
    require_permission,
)
from app.core import rbac
from app.core.rbac import is_admin_role
from app.db.postgres import get_db_session
from app.models import Case, CaseMember, Role, User, UserRole
from app.schemas.cases import (
    CaseCreateRequest,
    CaseListResponse,
    CaseMemberAddRequest,
    CaseMemberListResponse,
    CaseMemberOut,
    CaseOut,
    CaseUpdateRequest,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/cases", tags=["cases"])

# Case lifecycle (open -> in_progress -> closed, plus reopen). ``archived`` is
# a terminal state reached only through the archive endpoint and never via PATCH.
_CASE_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"in_progress", "closed"}),
    "in_progress": frozenset({"open", "closed"}),
    "closed": frozenset({"open", "in_progress"}),
    "archived": frozenset(),
}


def _assert_case_transition(current: str, target: str) -> None:
    allowed = _CASE_TRANSITIONS.get(current, frozenset())
    if current == target:
        return
    if target not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"illegal case transition {current!r} -> {target!r}",
        )


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


async def _case_filters(
    session: AsyncSession, user: User, user_roles: list[str]
) -> list[ColumnElement[bool]]:
    """Visibility predicate for list: admins see everything, everyone else sees
    cases they own or are a member of."""
    if any(is_admin_role(role) for role in user_roles):
        return []
    member_ids = (
        select(Case.id)
        .select_from(CaseMember)
        .where(CaseMember.user_id == user.id)
        .scalar_subquery()
    )
    return [or_(Case.owner_id == user.id, Case.id.in_(member_ids))]


@router.get("", response_model=CaseListResponse)
async def list_cases(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, max_length=200),
    status: str | None = Query(None, pattern="^(open|in_progress|closed|archived)$"),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> CaseListResponse:
    """List the cases the caller can access (owner or admin).

    ``search`` matches the title or case number (case-insensitive substring);
    ``status`` narrows to a single lifecycle state. Filtering, pagination and
    the ``total`` are computed in SQL rather than post-processing a full id
    list in Python, which keeps large catalogs memory-bounded.
    """
    roles = getattr(request.state, "roles", None) or []
    conditions = await _case_filters(session, user, roles)
    if status is not None:
        conditions.append(Case.status == status)
    if search:
        needle = f"%{search.strip()}%"
        conditions.append(or_(Case.title.ilike(needle), Case.case_number.ilike(needle)))

    total = await session.scalar(select(func.count(Case.id)).where(*conditions)) or 0
    result = await session.execute(
        select(Case)
        .where(*conditions)
        .order_by(Case.created_at.desc(), Case.id)
        .limit(limit)
        .offset(offset)
    )
    items = list(result.scalars())
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
    """Update editable case fields with lifecycle-aware status transitions."""
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
        _assert_case_transition(case.status, payload.status)
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
    if previous_status == "archived":
        raise HTTPException(status_code=409, detail="case is already archived")
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


# Case membership ---------------------------------------------------------


async def _require_owner_or_admin(
    request: Request, case: Case, user: User, session: AsyncSession
) -> None:
    """Only the case owner or an ADMIN may manage membership."""
    roles = getattr(request.state, "roles", None)
    if roles is None:
        result = await session.execute(
            select(Role.name)
            .select_from(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user.id)
        )
        roles = list(result.scalars())
        request.state.roles = roles
    if any(is_admin_role(role) for role in roles):
        return
    if case.owner_id is not None and user.id == case.owner_id:
        return
    raise HTTPException(
        status_code=403,
        detail=f"only the owner or an admin can manage members of case {case.id}",
    )


@router.get("/{case_id}/members", response_model=CaseMemberListResponse)
async def list_case_members(
    case_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> CaseMemberListResponse:
    """List the users who share access to a case."""
    case = await get_case_or_404(case_id, request, session)
    result = await session.execute(
        select(CaseMember).where(CaseMember.case_id == case.id).order_by(CaseMember.created_at)
    )
    members = result.scalars().all()
    return CaseMemberListResponse(
        items=[
            CaseMemberOut(user_id=m.user_id, role=m.role, created_at=m.created_at) for m in members
        ],
        case_id=case.id,
    )


@router.post("/{case_id}/members", response_model=CaseMemberListResponse, status_code=201)
async def add_case_member(
    case_id: uuid.UUID,
    payload: CaseMemberAddRequest,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> CaseMemberListResponse:
    """Grant a user access to a case (owner or admin only)."""
    case = await get_case_or_404(case_id, request, session)
    await _require_owner_or_admin(request, case, user, session)
    existing = await session.execute(
        select(CaseMember).where(
            CaseMember.case_id == case.id,
            CaseMember.user_id == payload.user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="user is already a member of this case")
    target = await session.get(User, payload.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"user {payload.user_id} not found")
    member = CaseMember(case_id=case.id, user_id=payload.user_id, role=payload.role)
    session.add(member)
    member_count = await session.scalar(
        select(func.count(CaseMember.user_id)).where(CaseMember.case_id == case.id)
    )
    await record_audit(
        session,
        actor_id=user.id,
        action="case.member_added",
        resource_type="case",
        resource_id=case.id,
        case_id=case.id,
        metadata={
            "member_id": str(payload.user_id),
            "role": payload.role,
            "member_count": (member_count or 0) + 1,
        },
    )
    await session.commit()
    return await list_case_members(case_id, request, user, session)


@router.delete("/{case_id}/members/{member_id}", response_model=CaseMemberListResponse)
async def remove_case_member(
    case_id: uuid.UUID,
    member_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> CaseMemberListResponse:
    """Revoke a user's access to a case (owner or admin only)."""
    case = await get_case_or_404(case_id, request, session)
    await _require_owner_or_admin(request, case, user, session)
    member = await session.execute(
        select(CaseMember).where(
            CaseMember.case_id == case.id,
            CaseMember.user_id == member_id,
        )
    )
    row = member.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="case member not found")
    await session.delete(row)
    await record_audit(
        session,
        actor_id=user.id,
        action="case.member_removed",
        resource_type="case",
        resource_id=case.id,
        case_id=case.id,
        metadata={"member_id": str(member_id)},
    )
    await session.commit()
    return await list_case_members(case_id, request, user, session)
