"""Unit tests for the findings lifecycle (transition rules + service)."""

from __future__ import annotations

import uuid

import pytest
from app.models import Finding
from app.services.findings_service import (
    ALLOWED_TRANSITIONS,
    PERMISSION_BY_TARGET,
    FindingsService,
    InvalidFindingTransition,
    required_permission_for,
    transition_allowed,
)


class _RecordingSession:
    """Stand-in AsyncSession: records flushes, never touches a database."""

    def __init__(self) -> None:
        self.flush_count = 0

    async def flush(self) -> None:
        self.flush_count += 1


def _finding(status: str = "NEW") -> Finding:
    return Finding(
        id=uuid.uuid4(),
        case_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
        finding_type="pattern",
        title="shared identifier",
        summary="two people share one phone",
        severity="high",
        score=0.9,
        confidence="high",
        status=status,
        affected_entities=[str(uuid.uuid4())],
        affected_relationships=[],
        evidence_ids=[],
        explanation={"approach": "x"},
        details={},
    )


def test_allowed_transitions_shape() -> None:
    assert ALLOWED_TRANSITIONS["NEW"] == frozenset({"REVIEWED", "DISMISSED", "CONFIRMED"})
    assert ALLOWED_TRANSITIONS["REVIEWED"] == frozenset({"DISMISSED", "CONFIRMED"})
    assert ALLOWED_TRANSITIONS["DISMISSED"] == frozenset()
    assert ALLOWED_TRANSITIONS["CONFIRMED"] == frozenset()


def test_permission_by_target() -> None:
    from app.core import rbac

    assert PERMISSION_BY_TARGET["REVIEWED"] == rbac.PERM_FINDINGS_REVIEW
    assert PERMISSION_BY_TARGET["DISMISSED"] == rbac.PERM_FINDINGS_DISMISS
    assert PERMISSION_BY_TARGET["CONFIRMED"] == rbac.PERM_FINDINGS_CONFIRM
    assert required_permission_for("REVIEWED") == rbac.PERM_FINDINGS_REVIEW


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("NEW", "REVIEWED"),
        ("NEW", "DISMISSED"),
        ("NEW", "CONFIRMED"),
        ("REVIEWED", "DISMISSED"),
        ("REVIEWED", "CONFIRMED"),
    ],
)
def test_forward_transitions_are_allowed_for_non_admin(current: str, target: str) -> None:
    assert transition_allowed(current, target, is_admin=False) is True


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("NEW", "NEW"),
        ("REVIEWED", "REVIEWED"),
        ("DISMISSED", "DISMISSED"),
        ("CONFIRMED", "CONFIRMED"),
    ],
)
def test_same_status_is_idempotent(current: str, target: str) -> None:
    assert transition_allowed(current, target, is_admin=False) is True


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("DISMISSED", "REVIEWED"),
        ("DISMISSED", "CONFIRMED"),
        ("CONFIRMED", "REVIEWED"),
        ("CONFIRMED", "DISMISSED"),
        ("REVIEWED", "NEW"),
        ("DISMISSED", "NEW"),
    ],
)
def test_closed_and_backwards_transitions_require_admin(current: str, target: str) -> None:
    assert transition_allowed(current, target, is_admin=False) is False
    assert transition_allowed(current, target, is_admin=True) is True


async def test_apply_status_change_marks_review_fields() -> None:
    session = _RecordingSession()
    actor_id = uuid.uuid4()
    finding = _finding("NEW")
    service = FindingsService(session)  # type: ignore[arg-type]

    updated, changed = await service.apply_status_change(
        finding=finding,
        new_status="REVIEWED",
        actor_id=actor_id,
        reason="checked against call records",
        is_admin=False,
    )
    assert changed is True
    assert updated.status == "REVIEWED"
    assert updated.reviewed_by == actor_id
    assert updated.reviewed_at is not None
    assert updated.review_comment == "checked against call records"
    assert session.flush_count == 1


async def test_apply_same_status_is_a_noop() -> None:
    session = _RecordingSession()
    finding = _finding("REVIEWED")
    service = FindingsService(session)  # type: ignore[arg-type]

    updated, changed = await service.apply_status_change(
        finding=finding,
        new_status="REVIEWED",
        actor_id=uuid.uuid4(),
        reason=None,
        is_admin=False,
    )
    assert changed is False
    assert updated.reviewed_at is None
    assert session.flush_count == 0


async def test_invalid_transition_raises_for_non_admin() -> None:
    session = _RecordingSession()
    finding = _finding("DISMISSED")
    service = FindingsService(session)  # type: ignore[arg-type]

    with pytest.raises(InvalidFindingTransition):
        await service.apply_status_change(
            finding=finding,
            new_status="CONFIRMED",
            actor_id=uuid.uuid4(),
            reason=None,
            is_admin=False,
        )
    assert finding.status == "DISMISSED"
    assert session.flush_count == 0


async def test_admin_can_make_a_closed_finding_move_again() -> None:
    session = _RecordingSession()
    actor_id = uuid.uuid4()
    finding = _finding("DISMISSED")
    service = FindingsService(session)  # type: ignore[arg-type]

    updated, changed = await service.apply_status_change(
        finding=finding,
        new_status="CONFIRMED",
        actor_id=actor_id,
        reason="new corroborating evidence",
        is_admin=True,
    )
    assert changed is True
    assert updated.status == "CONFIRMED"
    assert session.flush_count == 1
