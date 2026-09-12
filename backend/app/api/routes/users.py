"""Routes: administrative user management (Phase 5).

Only callers with ``users.manage`` (ADMIN) may reach these endpoints. The
workflow covers the account lifecycle: listing (all / pending), inspecting a
single account, approving with an explicit role, rejecting, suspending,
activating and moving a user to a single role.

Safeguards enforced server-side:
    - the client-supplied role is never trusted for privileges by itself (every
      role grant here is an explicit authorized admin action);
    - the final active ADMIN cannot be demoted, suspended or rejected;
    - an administrator cannot suspend, reject or change the role of themselves;
    - every mutation lands in the append-only audit log.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_user_service,
    require_permission,
)
from app.api.errors import (
    CODE_INSUFFICIENT_PERMISSION,
    ApiHTTPException,
)
from app.core.rbac import PERM_USERS_MANAGE, is_valid_role
from app.db.postgres import get_db_session
from app.models import User
from app.schemas.auth import (
    AdminUserList,
    AdminUserOut,
    ApproveRequest,
    RoleChangeRequest,
)
from app.services.audit import record_audit
from app.services.users import AccountTransitionError, UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/users", tags=["users"])


def _conflict_transition(exc: AccountTransitionError) -> ApiHTTPException:
    return ApiHTTPException(409, exc.code, exc.message)


async def _admin_out(service: UserService, user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        status=user.status,
        roles=await service.roles(user.id),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _load_user(service: UserService, user_id: uuid.UUID) -> User:
    user = await service.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"user {user_id} not found")
    return user


def _forbidden(message: str) -> ApiHTTPException:
    return ApiHTTPException(403, CODE_INSUFFICIENT_PERMISSION, message)


@router.get("", response_model=AdminUserList)
async def list_users(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
    _actor: User = Depends(require_permission(PERM_USERS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
    user_service: UserService = Depends(get_user_service),
) -> AdminUserList:
    """List users with optional lifecycle-status and search filters."""
    return await _list_users_service(user_service, limit, offset, status, search)


@router.get("/pending", response_model=AdminUserList)
async def list_pending_users(
    limit: int = 100,
    offset: int = 0,
    _actor: User = Depends(require_permission(PERM_USERS_MANAGE)),
    user_service: UserService = Depends(get_user_service),
) -> AdminUserList:
    """List accounts awaiting approval."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    users, total = await user_service.list_users(limit=limit, offset=offset, status="PENDING")
    items = [await _admin_out(user_service, user) for user in users]
    return AdminUserList(items=items, total=total, limit=limit, offset=offset)


async def _list_users_service(
    service: UserService,
    limit: int,
    offset: int,
    status: str | None,
    search: str | None,
) -> AdminUserList:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    users, total = await service.list_users(
        limit=limit, offset=offset, status=status or None, search=search or None
    )
    items = [await _admin_out(service, user) for user in users]
    return AdminUserList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{user_id}", response_model=AdminUserOut)
async def get_user(
    user_id: uuid.UUID,
    _actor: User = Depends(require_permission(PERM_USERS_MANAGE)),
    user_service: UserService = Depends(get_user_service),
) -> AdminUserOut:
    user = await _load_user(user_service, user_id)
    return await _admin_out(user_service, user)


@router.post("/{user_id}/approve", response_model=AdminUserOut)
async def approve_user(
    user_id: uuid.UUID,
    payload: ApproveRequest,
    actor: User = Depends(require_permission(PERM_USERS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
    user_service: UserService = Depends(get_user_service),
) -> AdminUserOut:
    """Approve a PENDING account, granting exactly one explicit role."""
    user = await _load_user(user_service, user_id)
    if user.status != "PENDING":
        raise ApiHTTPException(409, "CONFLICT", f"user {user.username!r} is not pending approval")
    try:
        approved = await user_service.approve(user.id, payload.role)
    except AccountTransitionError as exc:
        raise _conflict_transition(exc) from exc
    assert approved is not None
    user = approved
    await record_audit(
        session,
        actor_id=actor.id,
        action="auth.user_approved",
        resource_type="user",
        resource_id=user.id,
        metadata={"username": user.username, "role": payload.role},
    )
    await session.commit()
    return await _admin_out(user_service, user)


@router.post("/{user_id}/reject", response_model=AdminUserOut)
async def reject_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_permission(PERM_USERS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
    user_service: UserService = Depends(get_user_service),
) -> AdminUserOut:
    user = await _load_user(user_service, user_id)
    await _guard_admin_self(user, actor)
    await _guard_sole_admin(user_service, user)
    try:
        rejected = await user_service.reject(user.id)
    except AccountTransitionError as exc:
        raise _conflict_transition(exc) from exc
    assert rejected is not None
    user = rejected
    await record_audit(
        session,
        actor_id=actor.id,
        action="auth.user_rejected",
        resource_type="user",
        resource_id=user.id,
        metadata={"username": user.username},
    )
    await session.commit()
    return await _admin_out(user_service, user)


@router.post("/{user_id}/suspend", response_model=AdminUserOut)
async def suspend_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_permission(PERM_USERS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
    user_service: UserService = Depends(get_user_service),
) -> AdminUserOut:
    user = await _load_user(user_service, user_id)
    await _guard_admin_self(user, actor)
    await _guard_sole_admin(user_service, user)
    try:
        suspended = await user_service.suspend(user.id)
    except AccountTransitionError as exc:
        raise _conflict_transition(exc) from exc
    assert suspended is not None
    user = suspended
    await record_audit(
        session,
        actor_id=actor.id,
        action="auth.user_suspended",
        resource_type="user",
        resource_id=user.id,
        metadata={"username": user.username},
    )
    await session.commit()
    return await _admin_out(user_service, user)


@router.post("/{user_id}/activate", response_model=AdminUserOut)
async def activate_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_permission(PERM_USERS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
    user_service: UserService = Depends(get_user_service),
) -> AdminUserOut:
    user = await _load_user(user_service, user_id)
    try:
        activated = await user_service.activate(user.id)
    except AccountTransitionError as exc:
        raise _conflict_transition(exc) from exc
    assert activated is not None
    user = activated
    await record_audit(
        session,
        actor_id=actor.id,
        action="auth.user_activated",
        resource_type="user",
        resource_id=user.id,
        metadata={"username": user.username},
    )
    await session.commit()
    return await _admin_out(user_service, user)


@router.patch("/{user_id}/role", response_model=AdminUserOut)
async def change_role(
    user_id: uuid.UUID,
    payload: RoleChangeRequest,
    actor: User = Depends(require_permission(PERM_USERS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
    user_service: UserService = Depends(get_user_service),
) -> AdminUserOut:
    """Assign a single role (replacing any existing role)."""
    user = await _load_user(user_service, user_id)
    if user.id == actor.id:
        raise _forbidden("administrators cannot change their own role")
    if payload.role != "ADMIN" and await user_service.is_sole_active_admin(user.id):
        raise _forbidden("cannot demote the last active administrator")
    if not is_valid_role(payload.role):
        raise ApiHTTPException(
            422, "VALIDATION_ERROR", f"role {payload.role!r} is not a valid role"
        )
    try:
        updated = await user_service.change_role(user.id, payload.role)
    except AccountTransitionError as exc:
        raise _conflict_transition(exc) from exc
    assert updated is not None
    user = updated
    await record_audit(
        session,
        actor_id=actor.id,
        action="auth.role_changed",
        resource_type="user",
        resource_id=user.id,
        metadata={"username": user.username, "role": payload.role},
    )
    await session.commit()
    return await _admin_out(user_service, user)


async def _guard_admin_self(user: User, actor: User) -> None:
    if user.id == actor.id:
        raise _forbidden("administrators cannot suspend or reject themselves")


async def _guard_sole_admin(user_service: UserService, user: User) -> None:
    if await user_service.is_sole_active_admin(user.id):
        raise _forbidden("cannot suspend or reject the last active administrator")
