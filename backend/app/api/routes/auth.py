"""Routes: authentication and user management.

``/auth/register`` requires the ``users.manage`` permission, so accounts are
created by an administrator (or the seeded admin account) - never by anonymous
callers. ``/auth/login`` is the only public endpoint and is throttled via
Redis. ``/auth/me`` returns the current user with their roles and resolved
permissions.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_roles,
    get_current_user,
    get_user_service,
    require_permission,
)
from app.core.auth import create_access_token
from app.core.config import Settings, get_settings
from app.core.rbac import PERM_USERS_MANAGE
from app.core.security import verify_password
from app.db.postgres import get_db_session
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    RegisteredUserOut,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services import throttle
from app.services.audit import record_audit
from app.services.users import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_MAX_ATTEMPTS_REACHED = "too many failed login attempts; please retry later"


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, email=user.email, is_active=user.is_active)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    user_service: UserService = Depends(get_user_service),
) -> TokenResponse:
    """Authenticate against PostgreSQL users and return a short-lived token."""
    cache = request.app.state.cache
    username = payload.username.strip()
    if (
        settings.LOGIN_MAX_ATTEMPTS > 0
        and await throttle.attempts(cache, username, settings) >= settings.LOGIN_MAX_ATTEMPTS
    ):
        raise HTTPException(status_code=429, detail=_MAX_ATTEMPTS_REACHED)

    user = await user_service.get_by_username(username) or await user_service.get_by_email(
        username.lower()
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        await throttle.record_failed_attempt(cache, username, settings)
        if user is not None:
            await record_audit(
                session,
                actor_id=user.id,
                action="auth.login_failed",
                resource_type="user",
                resource_id=user.id,
                metadata={"reason": "invalid_credentials"},
            )
        await session.commit()
        raise HTTPException(status_code=401, detail="invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="account is deactivated")

    await throttle.clear_attempts(cache, username)
    token = create_access_token(
        user.id,
        secret=settings.SECRET_KEY,
        expires_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    await record_audit(
        session,
        actor_id=user.id,
        action="auth.login_succeeded",
        resource_type="user",
        resource_id=user.id,
        metadata={"expires_in_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES},
    )
    await session.commit()
    logger.info("user logged in", extra={"user_id": str(user.id)})
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_user_out(user),
    )


@router.post("/register", response_model=RegisteredUserOut, status_code=201)
async def register(
    payload: RegisterRequest,
    request: Request,
    actor: User = Depends(require_permission(PERM_USERS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
    user_service: UserService = Depends(get_user_service),
) -> RegisteredUserOut:
    """Create a user account with an initial role (administrator action)."""
    if await user_service.username_exists(payload.username):
        raise HTTPException(status_code=409, detail=f"username {payload.username!r} is taken")
    if await user_service.email_exists(payload.email):
        raise HTTPException(status_code=409, detail=f"email {payload.email!r} is registered")

    user = await user_service.create_user_with_role(
        username=payload.username,
        email=payload.email.lower(),
        password=payload.password,
        role=payload.role,
    )
    roles = await user_service.roles(user.id)
    await record_audit(
        session,
        actor_id=actor.id,
        action="auth.user_created",
        resource_type="user",
        resource_id=user.id,
        metadata={"username": user.username, "role": payload.role},
    )
    await session.commit()
    logger.info(
        "user created",
        extra={"user_id": str(user.id), "actor": str(actor.id), "role": payload.role},
    )
    return RegisteredUserOut(
        user=_user_out(user),
        roles=roles,
        created_at=user.created_at,
    )


@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(get_current_user),
    roles: list[str] = Depends(get_current_roles),
    user_service: UserService = Depends(get_user_service),
) -> MeResponse:
    """Identify the caller and their resolved roles + permissions."""
    permissions = await user_service.permissions(user.id)
    return MeResponse(
        user=_user_out(user),
        roles=roles,
        permissions=permissions,
    )
