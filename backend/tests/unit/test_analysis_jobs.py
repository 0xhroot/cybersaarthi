"""Unit tests: analysis job state machine (lifecycle, cancel, timeout, progress).

The transition table is what guarantees the master-prompt requirements:
canceled jobs can never be reported successful, terminal states are final,
progress is bounded, and cancellation wins over timeout.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from app.models import AnalysisJob
from app.services.analysis_jobs import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    InvalidJobTransition,
    UnknownJobFeature,
    advance,
    create_job,
    is_terminal,
    is_timed_out,
    request_cancel,
    should_stop,
    transition,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _job(status: str = "pending", *, timeout_seconds: int = 600) -> AnalysisJob:
    return AnalysisJob(
        status=status,
        progress=0,
        total_records=0,
        processed_records=0,
        attempts=0,
        timeout_seconds=timeout_seconds,
        cancel_requested=False,
        started_at=None,
        completed_at=None,
    )


def test_happy_path_pending_running_succeeded() -> None:
    job = _job()
    now = datetime.now(UTC)
    transition(job, "running", now=now)
    assert job.status == "running"
    assert job.started_at == now
    assert job.attempts == 1
    transition(job, "succeeded", now=now + timedelta(seconds=5))
    assert job.status == "succeeded"
    assert job.completed_at == now + timedelta(seconds=5)


def test_partial_is_a_valid_terminal_state() -> None:
    job = _job("running")
    job.started_at = datetime.now(UTC)
    transition(job, "partial")
    assert job.status == "partial"
    assert is_terminal(job.status)


def test_illegal_transitions_are_rejected() -> None:
    # pending may not jump straight to a success state
    with pytest.raises(InvalidJobTransition):
        transition(_job(), "succeeded")
    with pytest.raises(InvalidJobTransition):
        transition(_job(), "partial")
    # running cannot restart itself
    with pytest.raises(InvalidJobTransition):
        transition(_job("running"), "running")
    # terminal states are final
    for terminal in sorted(TERMINAL_STATUSES):
        for target in ("running", "succeeded", "failed", "canceled"):
            if target in ALLOWED_TRANSITIONS[terminal]:
                continue
            with pytest.raises(InvalidJobTransition):
                transition(_job(terminal), target)


def test_canceled_job_can_never_become_succeeded() -> None:
    job = _job("canceled")
    with pytest.raises(InvalidJobTransition):
        transition(job, "succeeded")
    assert job.status == "canceled"


def test_attempts_and_timestamps_set_once() -> None:
    job = _job()
    first = datetime.now(UTC)
    transition(job, "running", now=first)
    transition(job, "failed", now=first + timedelta(seconds=1))
    assert job.attempts == 1
    assert job.started_at == first
    assert job.completed_at is not None


def test_request_cancel_only_before_terminal() -> None:
    pending = _job()
    assert request_cancel(pending) is True
    assert pending.cancel_requested is True

    done = _job("succeeded")
    assert request_cancel(done) is False
    assert done.cancel_requested is False


def test_advance_computes_bounded_progress() -> None:
    job = _job("running")
    advance(job, processed=2, total=4)
    assert job.progress == 50
    assert job.processed_records == 2
    advance(job, processed=99, total=4)  # overcount clamps at 100
    assert job.progress == 100
    advance(job, processed=-1, total=4)  # negatives clamp at 0
    assert job.processed_records == 0
    assert job.progress == 0


def test_advance_without_total_keeps_percent_at_zero() -> None:
    job = _job("running")
    advance(job, processed=5)
    assert job.processed_records == 5
    assert job.progress == 0
    assert job.total_records == 0


def test_timeout_detection_requires_running_with_start_time() -> None:
    now = datetime.now(UTC)
    running = _job("running", timeout_seconds=600)
    running.started_at = now - timedelta(seconds=601)
    assert is_timed_out(running, now=now) is True

    fresh = _job("running", timeout_seconds=600)
    fresh.started_at = now - timedelta(seconds=10)
    assert is_timed_out(fresh, now=now) is False

    pending = _job("pending", timeout_seconds=600)
    assert is_timed_out(pending, now=now) is False

    no_start = _job("running")
    assert is_timed_out(no_start, now=now) is False


def test_should_stop_prefers_cancellation_over_timeout() -> None:
    now = datetime.now(UTC)
    job = _job("running", timeout_seconds=1)
    job.started_at = now - timedelta(seconds=60)
    job.cancel_requested = True
    assert should_stop(job, now=now) == "cancel"

    job.cancel_requested = False
    assert should_stop(job, now=now) == "timeout"

    healthy = _job("running", timeout_seconds=600)
    healthy.started_at = now
    assert should_stop(healthy, now=now) is None


async def test_create_job_validates_feature_before_touching_the_db() -> None:
    session = cast(AsyncSession, object())
    with pytest.raises(UnknownJobFeature):
        await create_job(
            session,
            case_id=uuid.uuid4(),
            feature="not_a_feature",
            idempotency_key="key-1",
        )


async def test_create_job_rejects_bad_idempotency_keys() -> None:
    session = cast(AsyncSession, object())
    with pytest.raises(ValueError):
        await create_job(
            session, case_id=uuid.uuid4(), feature="ingestion", idempotency_key=""
        )
    with pytest.raises(ValueError):
        await create_job(
            session, case_id=uuid.uuid4(), feature="ingestion", idempotency_key="x" * 129
        )
