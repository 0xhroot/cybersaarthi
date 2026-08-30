"""Finding lifecycle: human-driven status transitions.

The inference engine always creates findings as ``NEW`` and never auto-assigns
``CONFIRMED``; only a human (with the right permission) may move a finding.
The transition rules encode the workflow contract:

    NEW      -> REVIEWED | DISMISSED | CONFIRMED
    REVIEWED -> DISMISSED | CONFIRMED
    DISMISSED/CONFIRMED -> closed: only an explicitly authorized actor
                           (ADMIN) may move them again.

A no-op transition (same status) is idempotent and produces no audit event.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.models import Finding

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "NEW": frozenset({"REVIEWED", "DISMISSED", "CONFIRMED"}),
    "REVIEWED": frozenset({"DISMISSED", "CONFIRMED"}),
    "DISMISSED": frozenset(),
    "CONFIRMED": frozenset(),
}

# Permission required to move a finding TO the given status.
PERMISSION_BY_TARGET = {
    "REVIEWED": rbac.PERM_FINDINGS_REVIEW,
    "DISMISSED": rbac.PERM_FINDINGS_DISMISS,
    "CONFIRMED": rbac.PERM_FINDINGS_CONFIRM,
}


def required_permission_for(target: str) -> str:
    return PERMISSION_BY_TARGET[target]


def transition_allowed(current: str, target: str, *, is_admin: bool) -> bool:
    if current == target:
        return True
    if target in ALLOWED_TRANSITIONS.get(current, frozenset()):
        return True
    return is_admin


class InvalidFindingTransition(ValueError):
    """Raised when a transition violates the workflow contract."""


class FindingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def apply_status_change(
        self,
        *,
        finding: Finding,
        new_status: str,
        actor_id: uuid.UUID,
        reason: str | None,
        is_admin: bool,
    ) -> tuple[Finding, bool]:
        """Apply a status change; returns ``(finding, changed)``.

        ``changed`` is False for an idempotent no-op (no audit event emitted).
        Invalid transitions raise :class:`InvalidFindingTransition`.
        """
        current = finding.status
        if current == new_status:
            return finding, False
        if not transition_allowed(current, new_status, is_admin=is_admin):
            raise InvalidFindingTransition(
                f"invalid status transition from {current} to {new_status}"
            )
        finding.status = new_status
        finding.reviewed_by = actor_id
        finding.reviewed_at = datetime.now(UTC)
        finding.review_comment = reason
        await self._session.flush()
        return finding, True
