"""FastAPI dependencies: repositories, services and the auth/RBAC guard layer.

Every case-scoped route resolves the case through :func:`get_case_or_404`,
which authenticates the caller (401) and enforces case-level access (403,
owner-or-admin model) so IDOR is impossible by construction. Routing handlers
that mutate state additionally request a permission via
:func:`require_permission` or :func:`require_role`.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.findings import AnalyticsService
from app.core.auth import decode_access_token
from app.core.config import get_settings
from app.core.rbac import has_permission, is_admin_role
from app.db.postgres import get_db_session
from app.models import Case, Role, User, UserRole
from app.repositories.analytics_repository import AnalyticsDataRepository
from app.repositories.entity_repository import EntityRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.repositories.relationship_repository import RelationshipRepository
from app.repositories.user_repository import UserRepository
from app.services.entity_service import EntityQueryService
from app.services.graph_sync import GraphSyncService
from app.services.ingestion import IngestionService
from app.services.users import UserService

logger = logging.getLogger(__name__)


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        return token or None
    return None


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Resolve and validate the authenticated user (or raise 401)."""
    cached = getattr(request.state, "user", None)
    if cached is not None:
        return cached
    token = _bearer_token(request)
    if token is None:
        raise HTTPException(status_code=401, detail="authentication required")
    user_id = decode_access_token(token, secret=get_settings().SECRET_KEY)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired access token")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="invalid or inactive account")
    request.state.user = user
    request.state.user_id = user.id
    return user


async def get_current_roles(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[str]:
    """Current user's role names (cached on the request)."""
    cached = getattr(request.state, "roles", None)
    if cached is not None:
        return list(cached)
    result = await session.execute(
        select(Role.name)
        .select_from(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user.id)
        .order_by(Role.name)
    )
    roles = list(result.scalars())
    request.state.roles = roles
    return roles


def require_permission(permission: str) -> Callable[..., Awaitable[User]]:
    """Dependency factory: reject callers whose roles lack *permission* (403)."""

    async def dependency(
        user: User = Depends(get_current_user),
        roles: list[str] = Depends(get_current_roles),
    ) -> User:
        if not has_permission(roles, permission):
            logger.warning(
                "forbidden: user lacks permission",
                extra={"user_id": str(user.id), "permission": permission},
            )
            raise HTTPException(status_code=403, detail=f"permission '{permission}' required")
        return user

    return dependency


def require_role(*roles: str) -> Callable[..., Awaitable[User]]:
    """Dependency factory: reject callers outside the allowed roles (403)."""

    async def dependency(
        user: User = Depends(get_current_user),
        current_roles: list[str] = Depends(get_current_roles),
    ) -> User:
        if not any(role in current_roles for role in roles):
            raise HTTPException(
                status_code=403,
                detail=f"role {', '.join(roles)} required",
            )
        return user

    return dependency


async def _load_roles_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    result = await session.execute(
        select(Role.name)
        .select_from(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.name)
    )
    return list(result.scalars())


async def assert_case_access(
    request: Request,
    case: Case,
    user: User,
    session: AsyncSession,
) -> Case:
    """Enforce owner-or-admin access to a case. Raises 403 otherwise (IDOR guard)."""
    roles = getattr(request.state, "roles", None)
    if roles is None:
        roles = await _load_roles_for_user(session, user.id)
        request.state.roles = roles
    if any(is_admin_role(role) for role in roles):
        return case
    if case.owner_id is not None and user.id == case.owner_id:
        return case
    raise HTTPException(
        status_code=403,
        detail=f"you do not have access to case {case.id}",
    )


async def get_case_or_404(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Case:
    """Fetch a case the caller may access; 404 when missing, 403 on IDOR."""
    result = await session.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")
    user = await get_current_user(request, session)
    return await assert_case_access(request, case, user, session)


# Repositories / services -------------------------------------------------


def _repositories(
    session: AsyncSession,
) -> tuple[EvidenceRepository, EntityRepository, RelationshipRepository]:
    return (
        EvidenceRepository(session),
        EntityRepository(session),
        RelationshipRepository(session),
    )


async def get_evidence_repository(
    session: AsyncSession = Depends(get_db_session),
) -> EvidenceRepository:
    return EvidenceRepository(session)


async def get_entity_repository(
    session: AsyncSession = Depends(get_db_session),
) -> EntityRepository:
    return EntityRepository(session)


async def get_relationship_repository(
    session: AsyncSession = Depends(get_db_session),
) -> RelationshipRepository:
    return RelationshipRepository(session)


async def get_user_service(
    session: AsyncSession = Depends(get_db_session),
) -> UserService:
    return UserService(UserRepository(session))


async def get_ingestion_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> IngestionService:
    evidence_repo, entity_repo, relationship_repo = _repositories(session)
    settings = get_settings()
    return IngestionService(
        session=session,
        evidence_repository=evidence_repo,
        entity_repository=entity_repo,
        relationship_repository=relationship_repo,
        storage=request.app.state.storage,
        graph_sync=GraphSyncService(request.app.state.graph_store, settings),
        settings=settings,
    )


async def get_analytics_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsService:
    return AnalyticsService(
        data_repo=AnalyticsDataRepository(session),
        graph_store=request.app.state.graph_store,
        settings=get_settings(),
    )


async def get_analytics_data_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsDataRepository:
    return AnalyticsDataRepository(session)


async def get_entity_query_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> EntityQueryService:
    evidence_repo, entity_repo, relationship_repo = _repositories(session)
    return EntityQueryService(
        session=session,
        entity_repository=entity_repo,
        evidence_repository=evidence_repo,
        relationship_repository=relationship_repo,
    )
