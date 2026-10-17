"""Background-path authorization rechecks (shared by evidence-intelligence jobs).

FastAPI request routes authorize through ``app.api.dependencies``; background
jobs have no request context and must not trust anything cached at submission
time. The functions here re-derive the same decisions from the database on
every sensitive step so a revoked membership, role or account takes effect
before the next read or model call.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.enums import AccountStatus
from app.models import Role, User, UserRole
from app.services.citations import case_visible_to


async def still_authorized_for_case(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    case_id: uuid.UUID,
    permission: str,
) -> bool:
    """True only while the account is active, may see the case, and holds
    *permission* - each proven from fresh rows, never from request caches.

    Callers use this before assembling model context and between bounded
    batches, so evidence whose access was revoked mid-run stops being read.
    """
    user = await session.get(User, user_id)
    if user is None or user.status != AccountStatus.ACTIVE.value:
        return False
    if not await case_visible_to(session, user, case_id):
        return False
    role_rows = await session.execute(
        select(Role.name)
        .select_from(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user.id)
    )
    return rbac.has_permission(list(role_rows.scalars()), permission)
