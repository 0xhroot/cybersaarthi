"""Analysis job lifecycle: state machine + durable, idempotent persistence.

The transition table is the contract that keeps long-running evidence-
intelligence work honest:

- ``pending`` -> ``running`` -> ``succeeded`` | ``partial`` | ``failed`` | ``canceled``
- ``pending`` may go straight to ``failed`` or ``canceled`` (start rejection),
  and a canceled job can never be marked succeeded afterwards.
- ``attempts`` increments on every start; ``started_at``/``completed_at`` are set
  exactly once per lifecycle.

Runners poll :func:`should_stop` between bounded batches so cancellation and
timeout are cooperative but deterministic. There is no durable queue in this
deployment: jobs run in-process, and a job orphaned by a restart is retried
safely because ``create_job`` is idempotent on (case_id, idempotency_key).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisJob
from app.models.analysis_job import ANALYSIS_JOB_FEATURES

TERMINAL_STATUSES = frozenset({"succeeded", "partial", "failed", "canceled"})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running", "failed", "canceled"}),
    "running": TERMINAL_STATUSES,
    "succeeded": frozenset(),
    "partial": frozenset(),
    "failed": frozenset(),
    "canceled": frozenset(),
}


class InvalidJobTransition(ValueError):
    """Raised when a caller attempts a transition the state table forbids."""


class UnknownJobFeature(ValueError):
    """Raised when a job is requested for a feature that does not exist."""


def transition(job: AnalysisJob, to_status: str, *, now: datetime | None = None) -> AnalysisJob:
    """Move *job* to *to_status* or raise. Terminal states are final."""
    allowed = ALLOWED_TRANSITIONS.get(job.status, frozenset())
    if to_status not in allowed:
        raise InvalidJobTransition(
            f"cannot move analysis job from {job.status!r} to {to_status!r}"
        )
    stamp = now or datetime.now(UTC)
    if to_status == "running":
        if job.started_at is None:
            job.started_at = stamp
        job.attempts = (job.attempts or 0) + 1
    job.status = to_status
    if to_status in TERMINAL_STATUSES:
        job.completed_at = stamp
    return job


def request_cancel(job: AnalysisJob) -> bool:
    """Flag cooperative cancellation. Returns False once the job is terminal."""
    if job.status in TERMINAL_STATUSES:
        return False
    job.cancel_requested = True
    return True


def advance(job: AnalysisJob, *, processed: int, total: int | None = None) -> None:
    """Record progress deterministically (0-100; total=0 leaves percent at 0)."""
    if total is not None:
        job.total_records = max(0, total)
    job.processed_records = max(0, processed)
    if job.total_records > 0:
        job.progress = min(100, int(job.processed_records * 100 / job.total_records))
    else:
        job.progress = 0


def is_timed_out(job: AnalysisJob, *, now: datetime | None = None) -> bool:
    """True when a running job has exceeded its timeout budget."""
    if job.status != "running" or job.started_at is None:
        return False
    deadline = job.started_at + timedelta(seconds=job.timeout_seconds or 0)
    return (now or datetime.now(UTC)) > deadline


def should_stop(job: AnalysisJob, *, now: datetime | None = None) -> str | None:
    """Cooperative stop signal for runners: 'cancel' | 'timeout' | None.

    Cancellation wins over timeout so a canceled job is reported as canceled,
    never as failed.
    """
    if job.cancel_requested:
        return "cancel"
    if is_timed_out(job, now=now):
        return "timeout"
    return None


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


async def create_job(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    feature: str,
    idempotency_key: str,
    actor_id: uuid.UUID | None = None,
    evidence_file_id: uuid.UUID | None = None,
    total_records: int = 0,
    timeout_seconds: int = 600,
) -> tuple[AnalysisJob, bool]:
    """Create (or idempotently return) a pending job.

    Returns ``(job, created)``; ``created=False`` means an identical request
    already exists and no duplicate work must be started.
    """
    if feature not in ANALYSIS_JOB_FEATURES:
        raise UnknownJobFeature(f"unknown analysis feature {feature!r}")
    if not idempotency_key or len(idempotency_key) > 128:
        raise ValueError("idempotency_key must be 1-128 characters")
    existing = await session.execute(
        select(AnalysisJob).where(
            AnalysisJob.case_id == str(case_id),
            AnalysisJob.idempotency_key == idempotency_key,
        )
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        return row, False
    job = AnalysisJob(
        case_id=str(case_id),
        feature=feature,
        status="pending",
        idempotency_key=idempotency_key,
        progress=0,
        total_records=max(0, total_records),
        processed_records=0,
        attempts=0,
        timeout_seconds=timeout_seconds,
        cancel_requested=False,
        actor_id=str(actor_id) if actor_id is not None else None,
        evidence_file_id=str(evidence_file_id) if evidence_file_id is not None else None,
    )
    session.add(job)
    await session.flush()
    return job, True


async def get_job(
    session: AsyncSession, case_id: uuid.UUID, job_id: uuid.UUID
) -> AnalysisJob | None:
    """Case-scoped fetch (cross-case ids simply do not resolve)."""
    result = await session.execute(
        select(AnalysisJob).where(
            AnalysisJob.id == job_id,
            AnalysisJob.case_id == str(case_id),
        )
    )
    return result.scalar_one_or_none()


async def list_jobs(
    session: AsyncSession,
    case_id: uuid.UUID,
    *,
    feature: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[AnalysisJob], int]:
    """Case-scoped listing with filters (used by the Evidence Intelligence UI)."""
    query = select(AnalysisJob).where(AnalysisJob.case_id == str(case_id))
    if feature is not None:
        query = query.where(AnalysisJob.feature == feature)
    if status is not None:
        query = query.where(AnalysisJob.status == status)
    count_query = select(func.count()).select_from(query.subquery())
    total = int((await session.execute(count_query)).scalar_one())
    result = await session.execute(
        query.order_by(AnalysisJob.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars()), total


# -- case-level feature submission (phase-3 features) ---------------------------


class FeatureJobActive(ValueError):
    """A non-terminal job of this feature already runs for the case."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def _active_case_job(
    session: AsyncSession, case_id: uuid.UUID, feature: str
) -> AnalysisJob | None:
    result = await session.execute(
        select(AnalysisJob)
        .where(
            AnalysisJob.case_id == str(case_id),
            AnalysisJob.feature == feature,
            AnalysisJob.status.in_(("pending", "running")),
        )
        .order_by(AnalysisJob.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


def _clear_stale_case_job(job: AnalysisJob, *, timeout_seconds: int) -> bool:
    """Terminal-ize an orphaned pending/running job (restart, no queue).

    Same honest contract as the extraction/custody variants: a stale job is
    failed/canceled, never left alive and never able to report success.
    """
    try:
        if job.status == "running":
            if not is_timed_out(job):
                return False  # genuinely running (or never started): stay active
            job.error = f"superseded: exceeded {job.timeout_seconds}s timeout budget"
            transition(job, "failed")
        elif job.status == "pending":
            if (datetime.now(UTC) - job.created_at).total_seconds() <= 2 * max(
                1, job.timeout_seconds or timeout_seconds
            ):
                return False  # freshly queued, not stale
            transition(job, "canceled")
        else:
            return False
        return True
    except InvalidJobTransition:  # pragma: no cover - raced to terminal
        return False


async def submit_case_feature_job(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    feature: str,
    actor_id: uuid.UUID,
    timeout_seconds: int,
    active_code: str,
    scope_hash: str | None = None,
) -> tuple[AnalysisJob, bool]:
    """Idempotent case-level submission shared by the phase-3 features.

    One active job per (case, feature): a typed 409-style refusal
    (``active_code``) while one runs, honest clearing of stale jobs left by a
    restart, and attempt-numbered idempotency keys so a retry after
    failure/cancellation becomes attempt N+1 while a duplicate submission
    collapses onto the same job (``created=False``).

    ``scope_hash`` (cross-case runs) additionally distinguishes submissions by
    their authorized case scope: two different scopes on the same anchor case
    are different jobs, never a silent collapse onto a run over another scope.
    """
    from sqlalchemy.exc import IntegrityError

    active = await _active_case_job(session, case_id, feature)
    if active is not None and not _clear_stale_case_job(
        active, timeout_seconds=timeout_seconds
    ):
        raise FeatureJobActive(
            active_code, f"a {feature} job is already running for this case"
        )
    if active is not None:
        await session.flush()

    attempts = int(
        (
            await session.execute(
                select(func.count())
                .select_from(AnalysisJob)
                .where(
                    AnalysisJob.case_id == str(case_id),
                    AnalysisJob.feature == feature,
                )
            )
        ).scalar_one()
    )
    idempotency_key = (
        f"{feature}:{case_id}:h{scope_hash}:a{attempts + 1}"
        if scope_hash
        else f"{feature}:{case_id}:a{attempts + 1}"
    )
    try:
        return await create_job(
            session,
            case_id=case_id,
            feature=feature,
            idempotency_key=idempotency_key,
            actor_id=actor_id,
            timeout_seconds=timeout_seconds,
        )
    except IntegrityError:
        # Concurrent duplicate submission won the unique-key race.
        await session.rollback()
        existing = await session.execute(
            select(AnalysisJob).where(
                AnalysisJob.case_id == str(case_id),
                AnalysisJob.idempotency_key == idempotency_key,
            )
        )
        row = existing.scalar_one_or_none()
        if row is None:
            raise
        return row, False
