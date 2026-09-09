"""Routes: authentication and user management.

Phase 5 makes registration a public, self-service flow: anyone may create an
account, but it starts PENDING and is unusable until an administrator approves
it and assigns a role. ``/auth/login`` is public and throttled via Redis.
``/auth/me`` returns the current user with their roles and resolved permission
set. Administrative user management (approve/reject/suspend/activate/role)
lives in :mod:`app.api.routes.users`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_roles,
    get_current_user,
    get_user_service,
)
from app.api.errors import (
    CODE_ACCOUNT_PENDING,
    CODE_ACCOUNT_REJECTED,
    CODE_ACCOUNT_SUSPENDED,
    CODE_DUPLICATE_EMAIL,
    CODE_INVALID_CREDENTIALS,
    MESSAGES,
    ApiHTTPException,
)
from app.core.auth import create_access_token
from app.core.config import Settings, get_settings
from app.core.enums import AccountStatus
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
from app.services.token import revoke_token, token_jti
from app.services.users import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_MAX_ATTEMPTS_REACHED = "too many failed login attempts; please retry later"


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        return token or None
    return None


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        status=user.status,
        is_active=user.is_active,
    )


def _account_status_error(status: str) -> ApiHTTPException:
    """Map an account lifecycle status to its stable error code."""
    mapping = {
        AccountStatus.PENDING.value: (403, CODE_ACCOUNT_PENDING),
        AccountStatus.SUSPENDED.value: (403, CODE_ACCOUNT_SUSPENDED),
        AccountStatus.REJECTED.value: (403, CODE_ACCOUNT_REJECTED),
    }
    status_code, code = mapping[status]
    return ApiHTTPException(status_code, code, MESSAGES[code])


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
    ip = throttle.client_ip(request)
    if await throttle.is_throttled(cache, username, ip, settings):
        raise HTTPException(status_code=429, detail=_MAX_ATTEMPTS_REACHED)

    user = await user_service.get_by_username(username) or await user_service.get_by_email(
        username.lower()
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        await throttle.record_failed_attempt(cache, username, ip, settings)
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
        raise ApiHTTPException(401, CODE_INVALID_CREDENTIALS, MESSAGES[CODE_INVALID_CREDENTIALS])
    if user.status != AccountStatus.ACTIVE.value:
        raise _account_status_error(user.status)
    if not user.is_active:
        raise ApiHTTPException(403, CODE_ACCOUNT_SUSPENDED, MESSAGES[CODE_ACCOUNT_SUSPENDED])

    await throttle.clear_attempts(cache, username, ip)
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
    session: AsyncSession = Depends(get_db_session),
    user_service: UserService = Depends(get_user_service),
) -> RegisteredUserOut:
    """Create a PENDING account by public self-registration.

    The caller supplies only identity + password; no role is accepted or
    trusted here. A request role is never auto-granted — administrators assign
    a role at approval time.
    """
    if await user_service.username_exists(payload.username):
        raise ApiHTTPException(409, "DUPLICATE_USERNAME", f"username {payload.username!r} is taken")
    if await user_service.email_exists(payload.email):
        raise ApiHTTPException(409, CODE_DUPLICATE_EMAIL, f"email {payload.email!r} is registered")

    user = await user_service.register_pending(
        username=payload.username,
        email=payload.email,
        password=payload.password,
    )
    await record_audit(
        session,
        actor_id=None,
        action="auth.registration_requested",
        resource_type="user",
        resource_id=user.id,
        metadata={"username": user.username, "email": user.email},
    )
    await session.commit()
    logger.info(
        "registration requested",
        extra={"user_id": str(user.id), "status": user.status},
    )
    return RegisteredUserOut(
        user=_user_out(user),
        created_at=user.created_at,
    )


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> None:
    """Revoke the current bearer token (A07).

    Idempotent: revoking an already-revoked or invalid token is a no-op that
    still succeeds. When ``TOKEN_REVOCATION_ENABLED`` is false the endpoint
    still returns 204 (the client discards the token) with no denylist write.
    """
    if settings.TOKEN_REVOCATION_ENABLED:
        token = _bearer_token(request)
        jti = token_jti(token, secret=settings.SECRET_KEY) if token else None
        if jti is not None:
            await revoke_token(
                request.app.state.cache, jti, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
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
