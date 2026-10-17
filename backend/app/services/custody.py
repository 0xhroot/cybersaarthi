"""Chain-of-custody audit (feature 9): pure rule engine + job runner.

The rules are pure functions over a snapshot of REAL data (evidence row,
custody events, append-only audit entries, recomputed object hash) - they
decide pass/fail deterministically and never call the LLM. The AI layer only
explains recorded findings afterwards and cannot change any outcome here.

Policy semantics (policy v1.0.0, mirrored from
``app.models.evidence_custody_event``):

- ``collected`` requires ``collector``; ``transferred`` requires
  ``transferor`` AND ``recipient``; ``received`` requires ``recipient``;
  every other event type has no mandatory party fields - their absence is
  NOT a finding.
- ``received`` acknowledges a hand-off in this deployment; initial
  acquisition is documented as ``collected``. Chronology checks follow from
  that documented choice, nothing more.
- Missing information (bytes, hashes, acknowledgements, party details) is a
  documentation finding, never proof of tampering; only a recomputed-hash
  discrepancy yields the ``critical`` hash rules.

Rule set v1.0.0 (every payload carries both versions):

- ``custody.hash_mismatch`` (critical) - stored bytes hash ≠ recorded sha256.
- ``custody.recorded_hash_mismatch`` (critical) - an event's recorded hash ≠
  current object bytes.
- ``custody.source_missing`` (warning) - original object bytes unavailable.
- ``custody.hash_missing`` (info) - evidence row has no recorded sha256.
- ``custody.missing_required_field`` (warning) - policy party fields absent.
- ``custody.unacknowledged_transfer`` (warning) - transfer with no receipt at
  or after it (coarse check: any receipt counts; no per-transfer linkage
  exists in the schema yet - documented limitation).
- ``custody.duplicate_event`` (warning) - same type + same occurred_at twice
  on one evidence item.
- ``custody.chronology_future`` (warning) - occurred beyond clock-skew budget.
- ``custody.chronology_recorded_before_occurred`` (warning) - documented
  before it happened (beyond skew).
- ``custody.chronology_received_before_transfer`` (warning) - receipt earlier
  than every transfer.
- ``custody.orphaned_event`` (warning) - custody event whose evidence
  reference was lost (SET NULL after a hard delete).
- ``custody.no_documented_custody`` (info) - no custody event and no audit
  entry references this evidence.

Finding payloads are deliberately free of wall-clock values so identical
facts dedupe to one artifact (content-addressed); the evaluation time lives
in the artifact's ``created_at`` and in the run's audit entry. Re-running
after a fact changes (hashes, new events) produces a new finding while the
old one stays reviewable - history is never rewritten.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.codes import (
    CODE_CASE_ACCESS_DENIED,
    CODE_CUSTODY_FIELD_REQUIRED,
    CODE_EVIDENCE_NOT_FOUND,
    CODE_EVIDENCE_UNAVAILABLE,
    CODE_INVALID_PAYLOAD,
)
from app.core.config import Settings
from app.models import (
    AnalysisJob,
    AuditLog,
    EvidenceCustodyEvent,
    EvidenceFile,
)
from app.models.evidence_custody_event import CUSTODY_EVENT_TYPES, CUSTODY_REQUIRED_FIELDS
from app.services import analysis_jobs as jobs_svc
from app.services import artifacts as artifacts_svc
from app.services import audit as audit_svc
from app.services.authorization import still_authorized_for_case
from app.services.integrity import compare_hashes

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.storage import Storage

logger = logging.getLogger(__name__)

CUSTODY_FEATURE = "custody"
CUSTODY_RULE_SET_VERSION = "1.0.0"
CUSTODY_POLICY_VERSION = "1.0.0"

RULE_SEVERITY: dict[str, str] = {
    "custody.hash_mismatch": "critical",
    "custody.recorded_hash_mismatch": "critical",
    "custody.source_missing": "warning",
    "custody.hash_missing": "info",
    "custody.missing_required_field": "warning",
    "custody.unacknowledged_transfer": "warning",
    "custody.duplicate_event": "warning",
    "custody.chronology_future": "warning",
    "custody.chronology_recorded_before_occurred": "warning",
    "custody.chronology_received_before_transfer": "warning",
    "custody.orphaned_event": "warning",
    "custody.no_documented_custody": "info",
}


class CustodyRejected(ValueError):
    """Custody recording refused; ``code`` is the typed API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# -- snapshot types (what the pure rules see) --------------------------------


@dataclass(frozen=True, slots=True)
class CustodyEventFacts:
    """Row-level facts for one custody event (no ORM objects in pure rules)."""

    id: str
    event_type: str
    occurred_at: datetime
    recorded_at: datetime
    collector: str | None
    transferor: str | None
    recipient: str | None
    evidence_file_id: str | None
    recorded_sha256: str | None


@dataclass(frozen=True, slots=True)
class CustodySnapshot:
    """Everything one evidence item's custody audit evaluates over."""

    case_id: str
    evidence_id: str
    evidence_sha256: str | None
    evidence_created_at: datetime
    audit_entry_count: int
    events: tuple[CustodyEventFacts, ...]
    object_present: bool
    object_hash: str | None
    checked_at: datetime
    future_skew_seconds: int
    rule_set_version: str = CUSTODY_RULE_SET_VERSION
    policy_version: str = CUSTODY_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class CustodyIssue:
    """One candidate finding: rule, subjects, observed facts, missing data."""

    rule: str
    severity: str
    evidence_id: str | None
    event_ids: tuple[str, ...]
    observed: dict[str, object]
    missing: tuple[str, ...]
    message: str
    rule_set_version: str
    policy_version: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "type": "custody_finding",
            "rule": self.rule,
            "severity": self.severity,
            "evidence_id": self.evidence_id,
            "event_ids": list(self.event_ids),
            "observed": dict(self.observed),
            "missing": list(self.missing),
            "message": self.message,
            "rule_set_version": self.rule_set_version,
            "policy_version": self.policy_version,
        }


def _iso(value: datetime) -> str:
    return value.isoformat()


def _issue(
    snapshot: CustodySnapshot,
    rule: str,
    *,
    event_ids: tuple[str, ...] = (),
    observed: dict[str, object] | None = None,
    missing: tuple[str, ...] = (),
    message: str = "",
) -> CustodyIssue:
    return CustodyIssue(
        rule=rule,
        severity=RULE_SEVERITY[rule],
        evidence_id=snapshot.evidence_id,
        event_ids=event_ids,
        observed=dict(observed or {}),
        missing=missing,
        message=message,
        rule_set_version=snapshot.rule_set_version,
        policy_version=snapshot.policy_version,
    )


def build_event_facts(event: EvidenceCustodyEvent) -> CustodyEventFacts:
    """ORM row -> immutable rule input (occurred/recorded both timezone-aware)."""
    return CustodyEventFacts(
        id=str(event.id),
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        recorded_at=event.created_at,
        collector=event.collector,
        transferor=event.transferor,
        recipient=event.recipient,
        evidence_file_id=str(event.evidence_file_id) if event.evidence_file_id else None,
        recorded_sha256=event.recorded_sha256,
    )


# -- pure rule engine ---------------------------------------------------------


def evaluate_custody(snapshot: CustodySnapshot) -> tuple[CustodyIssue, ...]:
    """Run every custody rule against one evidence item's snapshot.

    Pure: same snapshot in -> same issues out. Absence of information
    produces documentation findings (info/warning), never a tampering claim;
    ``critical`` requires an actually recomputed hash discrepancy.
    """
    issues: list[CustodyIssue] = []
    events = snapshot.events
    transfers = tuple(e for e in events if e.event_type == "transferred")
    receipts = tuple(e for e in events if e.event_type == "received")

    # -- hash integrity ----------------------------------------------------
    recorded = (snapshot.evidence_sha256 or "").strip().lower()
    if not recorded:
        issues.append(
            _issue(
                snapshot,
                "custody.hash_missing",
                observed={"sha256_recorded": False, "object_present": snapshot.object_present},
                missing=("evidence.sha256",),
                message="evidence has no recorded content hash to verify against",
            )
        )
    if snapshot.object_present:
        if snapshot.object_hash and recorded and snapshot.object_hash != recorded:
            issues.append(
                _issue(
                    snapshot,
                    "custody.hash_mismatch",
                    observed={
                        "algorithm": "sha256",
                        "expected_sha256": recorded,
                        "calculated_sha256": snapshot.object_hash,
                    },
                    message="stored object bytes do not hash to the recorded sha256",
                )
            )
        for event in events:
            claimed = (event.recorded_sha256 or "").strip().lower()
            if claimed and snapshot.object_hash and claimed != snapshot.object_hash:
                issues.append(
                    _issue(
                        snapshot,
                        "custody.recorded_hash_mismatch",
                        event_ids=(event.id,),
                        observed={
                            "event_type": event.event_type,
                            "occurred_at": _iso(event.occurred_at),
                            "event_recorded_sha256": claimed,
                            "calculated_sha256": snapshot.object_hash,
                        },
                        message=(
                            "hash recorded on this custody event does not match "
                            "the current object bytes"
                        ),
                    )
                )
    else:
        issues.append(
            _issue(
                snapshot,
                "custody.source_missing",
                observed={
                    "object_present": False,
                    "sha256_recorded": bool(recorded),
                },
                missing=("original object bytes",),
                message=(
                    "original stored object is unavailable; integrity cannot be "
                    "verified (this is a documentation gap, not proof of tampering)"
                ),
            )
        )

    # -- documentation presence ---------------------------------------------
    if not events and snapshot.audit_entry_count == 0:
        issues.append(
            _issue(
                snapshot,
                "custody.no_documented_custody",
                observed={"custody_events": 0, "audit_entries": 0},
                missing=("custody event or audit entry",),
                message="no custody event and no audit entry references this evidence",
            )
        )

    # -- policy party fields ---------------------------------------------------
    for event in events:
        required = CUSTODY_REQUIRED_FIELDS.get(event.event_type, ())
        absent = tuple(
            name
            for name in required
            if not str(getattr(event, name) or "").strip()
        )
        if absent:
            issues.append(
                _issue(
                    snapshot,
                    "custody.missing_required_field",
                    event_ids=(event.id,),
                    observed={
                        "event_type": event.event_type,
                        "occurred_at": _iso(event.occurred_at),
                    },
                    missing=absent,
                    message=(
                        f"{event.event_type!r} event is missing required field(s): "
                        + ", ".join(absent)
                    ),
                )
            )

    # -- duplicates ------------------------------------------------------------
    groups: dict[tuple[str, str], list[str]] = {}
    for event in events:
        groups.setdefault((event.event_type, _iso(event.occurred_at)), []).append(event.id)
    for (event_type, occurred), ids in sorted(groups.items()):
        if len(ids) > 1:
            issues.append(
                _issue(
                    snapshot,
                    "custody.duplicate_event",
                    event_ids=tuple(sorted(ids)),
                    observed={
                        "event_type": event_type,
                        "occurred_at": occurred,
                        "count": len(ids),
                    },
                    message="multiple custody events of one type share the same occurred_at",
                )
            )

    # -- chronology -------------------------------------------------------------
    skew = timedelta(seconds=snapshot.future_skew_seconds)
    for event in events:
        if event.occurred_at > snapshot.checked_at + skew:
            issues.append(
                _issue(
                    snapshot,
                    "custody.chronology_future",
                    event_ids=(event.id,),
                    observed={
                        "event_type": event.event_type,
                        "occurred_at": _iso(event.occurred_at),
                        "tolerance_seconds": snapshot.future_skew_seconds,
                    },
                    message="event claims to have occurred in the future",
                )
            )
        if event.recorded_at + skew < event.occurred_at:
            issues.append(
                _issue(
                    snapshot,
                    "custody.chronology_recorded_before_occurred",
                    event_ids=(event.id,),
                    observed={
                        "event_type": event.event_type,
                        "occurred_at": _iso(event.occurred_at),
                        "recorded_at": _iso(event.recorded_at),
                    },
                    message="event was documented before the time it claims to have occurred",
                )
            )
    if transfers and receipts:
        earliest_transfer = min(t.occurred_at for t in transfers)
        for receipt in receipts:
            if receipt.occurred_at < earliest_transfer:
                issues.append(
                    _issue(
                        snapshot,
                        "custody.chronology_received_before_transfer",
                        event_ids=(receipt.id,),
                        observed={
                            "received_at": _iso(receipt.occurred_at),
                            "earliest_transfer_at": _iso(earliest_transfer),
                        },
                        message="receipt predates every transfer of this evidence",
                    )
                )

    # -- unacknowledged hand-offs ------------------------------------------------
    for transfer in transfers:
        acknowledged = any(r.occurred_at >= transfer.occurred_at for r in receipts)
        if not acknowledged:
            latest = max((r.occurred_at for r in receipts), default=None)
            issues.append(
                _issue(
                    snapshot,
                    "custody.unacknowledged_transfer",
                    event_ids=(transfer.id,),
                    observed={
                        "transferred_at": _iso(transfer.occurred_at),
                        "latest_received_at": _iso(latest) if latest else None,
                    },
                    missing=("receipt (received event at or after the transfer)",),
                    message="transfer has no receipt acknowledging it",
                )
            )
    return tuple(issues)


def evaluate_orphaned_events(
    events: tuple[CustodyEventFacts, ...],
    *,
    case_id: str,
    rule_set_version: str = CUSTODY_RULE_SET_VERSION,
    policy_version: str = CUSTODY_POLICY_VERSION,
) -> tuple[CustodyIssue, ...]:
    """Broken evidence references, evaluated case-wide (evidence_file_id NULL).

    Orphan findings carry ``evidence_id=None`` by construction - they describe
    the absence of a reference, never a specific evidence item.
    """
    orphans = tuple(e for e in events if e.evidence_file_id is None)
    if not orphans:
        return ()
    _ = case_id  # snapshot-free evaluation: there is no evidence to anchor to
    return (
        CustodyIssue(
            rule="custody.orphaned_event",
            severity=RULE_SEVERITY["custody.orphaned_event"],
            evidence_id=None,
            event_ids=tuple(sorted(e.id for e in orphans)),
            observed={
                "orphaned_count": len(orphans),
                "event_types": sorted({e.event_type for e in orphans}),
            },
            missing=("evidence reference",),
            message="custody events no longer reference any evidence file",
            rule_set_version=rule_set_version,
            policy_version=policy_version,
        ),
    )


# -- custody event recording (append-only, going forward) ----------------------


async def record_custody_event(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    actor_id: uuid.UUID,
    event_type: str,
    occurred_at: datetime,
    collector: str | None = None,
    transferor: str | None = None,
    recipient: str | None = None,
    location: str | None = None,
    method: str | None = None,
    notes: str | None = None,
    recorded_sha256: str | None = None,
    max_future_seconds: int,
) -> EvidenceCustodyEvent:
    """Validate and append one custody event (never edits existing rows).

    Deterministic refusals: unknown type, missing policy party fields,
    timezone-less or implausibly future ``occurred_at``, malformed sha256.
    """
    evidence = await _scoped_evidence(session, case_id, evidence_id)
    if evidence is None:
        raise CustodyRejected(CODE_EVIDENCE_NOT_FOUND, "evidence not found in this case")
    if evidence.deleted_at is not None:
        raise CustodyRejected(
            CODE_EVIDENCE_UNAVAILABLE,
            "evidence is deleted; restore it before recording custody events",
        )
    if event_type not in CUSTODY_EVENT_TYPES:
        raise CustodyRejected(CODE_INVALID_PAYLOAD, f"unknown custody event type {event_type!r}")
    if occurred_at.tzinfo is None:
        raise CustodyRejected(
            CODE_INVALID_PAYLOAD, "occurred_at must include an explicit time zone"
        )
    now = datetime.now(UTC)
    if occurred_at > now + timedelta(seconds=max_future_seconds):
        raise CustodyRejected(
            CODE_INVALID_PAYLOAD,
            f"occurred_at is more than {max_future_seconds}s in the future",
        )
    parties = {"collector": collector, "transferor": transferor, "recipient": recipient}
    missing = [
        name
        for name in CUSTODY_REQUIRED_FIELDS.get(event_type, ())
        if not str(parties.get(name) or "").strip()
    ]
    if missing:
        raise CustodyRejected(
            CODE_CUSTODY_FIELD_REQUIRED,
            f"{event_type!r} custody event requires: " + ", ".join(missing),
        )
    if recorded_sha256 is not None:
        digest = recorded_sha256.strip().lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise CustodyRejected(
                CODE_INVALID_PAYLOAD, "recorded_sha256 must be a 64-character hex sha256"
            )
        recorded_sha256 = digest

    event = EvidenceCustodyEvent(
        case_id=str(case_id),
        evidence_file_id=str(evidence_id),
        event_type=event_type,
        occurred_at=occurred_at.astimezone(UTC),
        actor_user_id=str(actor_id),
        collector=collector,
        transferor=transferor,
        recipient=recipient,
        location=location,
        method=method,
        notes=notes,
        recorded_sha256=recorded_sha256,
    )
    session.add(event)
    await session.flush()
    return event


async def _scoped_evidence(
    session: AsyncSession, case_id: uuid.UUID, evidence_id: uuid.UUID
) -> EvidenceFile | None:
    result = await session.execute(
        select(EvidenceFile).where(
            EvidenceFile.id == str(evidence_id),
            EvidenceFile.case_id == str(case_id),
        )
    )
    return result.scalar_one_or_none()


# -- audit job runner ----------------------------------------------------------


async def _list_evidence(
    session: AsyncSession, case_id: uuid.UUID, evidence_id: uuid.UUID | None, settings: Settings
) -> tuple[list[EvidenceFile], bool]:
    """Evidence under audit: one item, or the case (bounded, undeleted)."""
    if evidence_id is not None:
        evidence = await _scoped_evidence(session, case_id, evidence_id)
        if evidence is None or evidence.deleted_at is not None:
            return [], False
        return [evidence], False
    cap = settings.CUSTODY_AUDIT_MAX_EVIDENCE
    result = await session.execute(
        select(EvidenceFile)
        .where(EvidenceFile.case_id == str(case_id), EvidenceFile.deleted_at.is_(None))
        .order_by(EvidenceFile.created_at, EvidenceFile.id)
        .limit(cap + 1)
    )
    rows = list(result.scalars())
    return rows[:cap], len(rows) > cap


async def _hash_object(storage: Storage, key: str) -> str | None:
    """Current sha256 of stored bytes, or None when they are unavailable."""
    from app.services.validation import fingerprint

    try:
        exists = await asyncio.to_thread(storage.exists, key)
        if not exists:
            return None
        raw = await asyncio.to_thread(storage.download, key)
        return fingerprint(raw)
    except Exception:  # storage outage must degrade to "unverifiable", not crash
        logger.warning("custody audit could not read object bytes")
        return None


async def execute_custody_audit(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    settings: Settings,
    storage: Storage,
) -> None:
    """Run one pending custody-audit job to a terminal state.

    Findings are never a job failure: ``succeeded`` reports how many issues
    were detected. Only authorization loss, missing evidence or unexpected
    crashes fail the job - always with a typed code.
    """
    job = await session.get(AnalysisJob, job_id)
    if job is None or job.status != "pending":
        return
    case_id = uuid.UUID(str(job.case_id))
    evidence_id = uuid.UUID(str(job.evidence_file_id)) if job.evidence_file_id else None
    actor_id = uuid.UUID(str(job.actor_id)) if job.actor_id else None

    if actor_id is None:
        await _fail_job(
            session, job, code="CUSTODY_AUDIT_FAILED", error="job has no actor reference"
        )
        return
    if not await still_authorized_for_case(
        session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_EVIDENCE_READ
    ):
        await _fail_job(
            session,
            job,
            code=CODE_CASE_ACCESS_DENIED,
            error="access to this case was revoked before the custody audit ran",
            denial=True,
        )
        return
    if job.cancel_requested:
        await _stop_job(session, job, stop="cancel", summary={}, case_id=case_id, actor_id=actor_id)
        return

    targets, bounded = await _list_evidence(session, case_id, evidence_id, settings)
    if evidence_id is not None and not targets:
        await _fail_job(
            session,
            job,
            code=CODE_EVIDENCE_UNAVAILABLE,
            error="evidence is no longer available for custody audit",
        )
        return

    jobs_svc.transition(job, "running")
    await session.commit()

    summary: dict[str, Any] = {
        "evidence_total": len(targets),
        "evidence_checked": 0,
        "evidence_bounded": bounded,
        "findings_new": 0,
        "findings_existing": 0,
        "custody_events": 0,
        "hash_match": 0,
        "hash_mismatch": 0,
        "hash_unavailable": 0,
        "orphaned_events": 0,
    }
    stage = "authorize"
    try:
        # Case-wide orphaned references (events whose evidence was hard-deleted).
        stage = "orphans"
        orphan_rows = await session.execute(
            select(EvidenceCustodyEvent).where(
                EvidenceCustodyEvent.case_id == str(case_id),
                EvidenceCustodyEvent.evidence_file_id.is_(None),
            )
        )
        orphan_facts = tuple(build_event_facts(row) for row in orphan_rows.scalars())
        for issue in evaluate_orphaned_events(
            orphan_facts, case_id=str(case_id), rule_set_version=CUSTODY_RULE_SET_VERSION
        ):
            created = await _record_finding(session, issue=issue, job=job, actor_id=actor_id)
            summary["findings_new" if created else "findings_existing"] += 1
            summary["orphaned_events"] = len(issue.event_ids)
        await session.commit()

        stage = "audit"
        for index, evidence in enumerate(targets, start=1):
            await session.refresh(job)
            stop = jobs_svc.should_stop(job)
            if stop is not None:
                await _stop_job(
                    session, job, stop=stop, summary=summary, case_id=case_id, actor_id=actor_id
                )
                return
            if not await still_authorized_for_case(
                session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_EVIDENCE_READ
            ):
                await _fail_job(
                    session,
                    job,
                    code=CODE_CASE_ACCESS_DENIED,
                    error="access to this case was revoked mid-audit; stopped",
                    denial=True,
                    summary=summary,
                )
                return

            event_rows = await session.execute(
                select(EvidenceCustodyEvent)
                .where(
                    EvidenceCustodyEvent.evidence_file_id == str(evidence.id),
                    EvidenceCustodyEvent.case_id == str(case_id),
                )
                .order_by(EvidenceCustodyEvent.occurred_at, EvidenceCustodyEvent.created_at)
            )
            events = tuple(build_event_facts(row) for row in event_rows.scalars())
            audit_count = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(AuditLog)
                        .where(
                            AuditLog.resource_type == "evidence_file",
                            AuditLog.resource_id == str(evidence.id),
                        )
                    )
                ).scalar_one()
            )
            object_hash = await _hash_object(storage, evidence.stored_key)
            snapshot = CustodySnapshot(
                case_id=str(case_id),
                evidence_id=str(evidence.id),
                evidence_sha256=evidence.sha256,
                evidence_created_at=evidence.created_at,
                audit_entry_count=audit_count,
                events=events,
                object_present=object_hash is not None,
                object_hash=object_hash,
                checked_at=datetime.now(UTC),
                future_skew_seconds=settings.CUSTODY_FUTURE_SKEW_SECONDS,
            )
            # Hash verification counters (facts, separate from rule findings).
            comparison = compare_hashes("sha256", evidence.sha256, object_hash)
            if comparison.status == "match":
                summary["hash_match"] += 1
            elif comparison.status == "mismatch":
                summary["hash_mismatch"] += 1
            else:
                summary["hash_unavailable"] += 1
            summary["custody_events"] += len(events)

            for issue in evaluate_custody(snapshot):
                created = await _record_finding(
                    session, issue=issue, job=job, actor_id=actor_id, evidence_file_id=evidence.id
                )
                summary["findings_new" if created else "findings_existing"] += 1

            summary["evidence_checked"] += 1
            jobs_svc.advance(job, processed=index, total=len(targets))
            await session.commit()

        job.result_summary = summary
        jobs_svc.transition(job, "succeeded")
        await session.flush()
        await audit_svc.record_audit(
            session,
            actor_id=actor_id,
            action="custody.audit_completed",
            resource_type="analysis_job",
            resource_id=job.id,
            case_id=case_id,
            metadata={
                "evidence_checked": summary["evidence_checked"],
                "findings_new": summary["findings_new"],
                "findings_existing": summary["findings_existing"],
            },
        )
        await session.commit()
    except Exception:
        logger.exception("custody audit crashed", extra={"job_id": str(job.id)})
        await session.rollback()
        # Rollback expires loaded instances; re-read before terminal writes.
        await session.refresh(job)
        await _fail_job(
            session,
            job,
            code="CUSTODY_AUDIT_FAILED",
            error=f"unexpected error during stage {stage}",
            summary=summary,
        )


async def _record_finding(
    session: AsyncSession,
    *,
    issue: CustodyIssue,
    job: AnalysisJob,
    actor_id: uuid.UUID,
    evidence_file_id: uuid.UUID | None = None,
) -> bool:
    """Persist one rule finding (content-addressed: identical facts = no dup)."""
    artifact, created = await artifacts_svc.record_artifact(
        session,
        case_id=uuid.UUID(str(job.case_id)),
        kind="custody_finding",
        origin="deterministic",
        payload=issue.as_payload(),
        evidence_file_id=evidence_file_id,
        validation_status="valid",
        parser_version=f"rules:{issue.rule_set_version}",
        analysis_job_id=job.id,
        created_by=actor_id,
        status="pending_review",
    )
    _ = artifact
    return created


async def _stop_job(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    stop: str,
    summary: dict[str, Any],
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    """Cooperative stop: cancel wins over timeout; never reports success."""
    if summary:
        job.result_summary = summary
    if stop == "cancel":
        jobs_svc.transition(job, "canceled")
        action = "custody.canceled"
    else:
        job.error = f"custody audit timed out after {job.timeout_seconds}s"
        jobs_svc.transition(job, "failed")
        action = "custody.timed_out"
    await session.flush()
    await audit_svc.record_audit(
        session,
        actor_id=actor_id,
        action=action,
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"evidence_checked": summary.get("evidence_checked", 0)} if summary else {},
    )
    await session.commit()


async def _fail_job(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    code: str,
    error: str,
    summary: dict[str, Any] | None = None,
    denial: bool = False,
    stage: str = "authorize",
) -> None:
    """Terminal failure with typed code + audit; safe from pending or running."""
    if jobs_svc.is_terminal(job.status):
        return
    payload: dict[str, Any] = dict(summary) if summary else {}
    payload["error_code"] = code
    job.result_summary = payload
    job.error = error[:500]
    jobs_svc.transition(job, "failed")
    await session.flush()
    case_id = uuid.UUID(str(job.case_id))
    actor_id = uuid.UUID(str(job.actor_id)) if job.actor_id else None
    await audit_svc.record_audit(
        session,
        actor_id=actor_id,
        action="custody.denied" if denial else "custody.failed",
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"code": code, "stage": stage},
    )
    await session.commit()


# -- background entry (mirrors the async-ingest pattern) -----------------------


async def run_custody_audit_job(app: FastAPI, job_id: uuid.UUID) -> None:
    """Background worker: own DB session, own scope, never raises."""
    from app.core.config import get_settings
    from app.db.postgres import Database

    settings: Settings = get_settings()
    database: Database = app.state.database
    factory: async_sessionmaker[AsyncSession] = database.session_factory()
    try:
        async with factory() as session:
            await execute_custody_audit(
                session, job_id=job_id, settings=settings, storage=app.state.storage
            )
    except Exception:  # session-level crash: fail the job best-effort
        logger.exception("background custody audit failed", extra={"job_id": str(job_id)})
        async with factory() as session:
            job = await session.get(AnalysisJob, job_id)
            if job is not None and not jobs_svc.is_terminal(job.status):
                await _fail_job(
                    session,
                    job,
                    code="CUSTODY_AUDIT_FAILED",
                    error="background custody audit task crashed",
                )
