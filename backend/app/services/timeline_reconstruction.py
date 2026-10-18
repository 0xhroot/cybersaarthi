"""Phase 3 feature B: automatic timeline reconstruction proposals.

Deterministic extraction of proposed timeline events from data the platform
already holds: structured source records (date-like fields) and phase-2
extraction artifacts (``transaction_dates``, dated ``events`` statements).
LLM extraction from free text is deliberately deferred (documented
limitation): the data model supports deterministic timestamp extraction, and
ungrounded model dates would be worse than none.

Design contract (``docs/ai/PHASE_3_DESIGN.md`` section 4):

- Original timestamp strings and source time-zone information are preserved
  verbatim (``original_timestamp``, ``tz``); normalization to a UTC
  ``occurred_at`` for comparison never overwrites them. Date-only values are
  midnight UTC (documented ``time_granularity: "date"``); naive local
  datetimes are flagged ``ambiguous_timezone`` (an explicit assumption, never
  silent); unparseable or absent values produce a flagged
  ``missing_timestamp`` proposal with the original value - a datetime is
  never invented, and commit refuses such proposals.
- ``time_semantics`` distinguishes when the time refers to: the recorded
  event (``record_occurs_on``), a statement about an event
  (``statement_refers_to_event``), document creation, upload or extraction.
- Every proposal cites real source ids and locators, is stored through the
  phase-1 job/artifact pipeline, and duplicates/conflicts against other
  proposals and the authoritative timeline are flagged - existing timeline
  events are never replaced or rewritten. Committing a reviewed proposal
  goes through the existing authorized timeline service and is idempotent.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.codes import (
    CODE_ARTIFACT_KIND_UNSUPPORTED,
    CODE_ARTIFACT_NOT_FOUND,
    CODE_CASE_ACCESS_DENIED,
    CODE_PROPOSAL_NOT_APPROVED,
    CODE_TIMELINE_TIMESTAMP_MISSING,
)
from app.core.config import Settings
from app.models import AnalysisJob, DerivedArtifact, EvidenceFile, SourceRecord, TimelineEvent
from app.models.timeline_event import TIMELINE_EVENT_KINDS
from app.services import analysis_jobs as jobs_svc
from app.services import artifacts as artifacts_svc
from app.services import audit as audit_svc
from app.services import timeline as timeline_svc
from app.services.authorization import still_authorized_for_case
from app.services.structured_extraction import as_date, canonical_hash, normalize_text

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)

TIMELINE_FEATURE = "timeline"
TIMELINE_RECON_VERSION = "timeline_recon:1.0.0"
COMMIT_KIND = "case_event"  # the only kind reconstruction may create

# Field-name hints: which record fields plausibly hold a timestamp. "strong"
# fields become missing-timestamp proposals when unparseable; "weak" fields are
# simply skipped when their value cannot be parsed.
_TIME_HINTS = (
    "date",
    "time",
    "timestamp",
    "_at",
    "day",
    "when",
    "period",
    "occurred",
    "incident",
    "posted",
    "logged",
    "recorded",
    "submitted",
    "issued",
    "closed",
    "opened",
    "stamp",
)
_STRONG_TIME_HINTS = ("date", "time", "timestamp", "occurred", "incident", "stamp", "_at")

# time_semantics, by field-name hints (first match wins).
_SEMANTIC_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("extracted", "parsed", "analysed", "analyzed"), "extraction"),
    (("uploaded", "imported", "ingested"), "uploaded"),
    (
        ("created", "issued", "generated", "printed", "signed", "updated", "modified"),
        "document_created",
    ),
    (
        ("occurred", "incident", "txn", "transaction", "paid", "debited", "credited"),
        "record_occurs_on",
    ),
)

_OFFSET_TZ_RE = re.compile(
    r"^(?P<body>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)"
    r"\s*(?P<tz>Z|[+-]\d{2}:?\d{2})$"
)
_NAIVE_ISO_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})[T ](?P<time>\d{2}:\d{2}(?::\d{2})?)$")
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_WITH_TIME_RE = re.compile(
    r"^(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{4})[ T,]+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)$"
)
_EMBEDDED_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4}")

TITLE_MAX = 200
DESCRIPTION_MAX = 500


def looks_like_time_field(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _TIME_HINTS)


def is_strong_time_field(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _STRONG_TIME_HINTS)


def classify_time_semantics(field_name: str) -> str:
    lowered = field_name.lower()
    for hints, semantics in _SEMANTIC_HINTS:
        if any(hint in lowered for hint in hints):
            return semantics
    return "record_occurs_on"


# -- deterministic timestamp parsing (originals preserved) ----------------------


@dataclass(frozen=True, slots=True)
class ParsedTimestamp:
    """One parsed timestamp: UTC instant plus everything the source said."""

    occurred_at: datetime | None  # aware UTC, or None when only a date is known
    original: str
    tz: str | None
    granularity: str | None  # "datetime" | "date"
    tz_assumed: bool


def _tz_label(value: datetime) -> str | None:
    offset = value.utcoffset()
    if offset is None:
        return None
    if offset == timedelta(0):
        return "UTC"
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def _from_datetime_value(value: datetime, original: str) -> ParsedTimestamp:
    if value.tzinfo is None:
        # Naive local time: the zone is unknown. Assume UTC for comparison but
        # flag it - the investigator sees the original string and the flag.
        return ParsedTimestamp(
            occurred_at=value.replace(tzinfo=UTC),
            original=original,
            tz=None,
            granularity="datetime",
            tz_assumed=True,
        )
    aware = value.astimezone(UTC)
    return ParsedTimestamp(
        occurred_at=aware,
        original=original,
        tz=_tz_label(value),
        granularity="datetime",
        tz_assumed=False,
    )


def parse_timestamp(value: Any) -> ParsedTimestamp | None:
    """Parse *value* into a UTC instant, or None when it cannot be established.

    Never guesses a missing zone beyond the one documented assumption (naive
    datetime -> UTC, flagged) and never invents a date.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return _from_datetime_value(value, value.isoformat())
    if isinstance(value, date):
        return ParsedTimestamp(
            occurred_at=datetime.combine(value, time.min, tzinfo=UTC),
            original=value.isoformat(),
            tz=None,
            granularity="date",
            tz_assumed=False,
        )
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None

    # Date-only strings: Python's fromisoformat accepts "2026-03-15" as a
    # midnight datetime, but a bare date carries no time or zone - it stays a
    # date-granularity value (not an assumed-local midnight).
    if _DATE_ONLY_RE.fullmatch(text) is not None:
        parsed_date = as_date(text)
        if parsed_date is not None:
            return ParsedTimestamp(
                occurred_at=datetime.combine(parsed_date, time.min, tzinfo=UTC),
                original=text,
                tz=None,
                granularity="date",
                tz_assumed=False,
            )

    offset_match = _OFFSET_TZ_RE.match(text)
    if offset_match is not None:
        tz = offset_match.group("tz")
        body = offset_match.group("body")
        normalized_tz = (
            "+00:00" if tz in ("Z", "z") else (f"{tz[:3]}:{tz[3:]}" if len(tz) == 5 else tz)
        )
        try:
            parsed = datetime.fromisoformat(f"{body}{normalized_tz}")
        except ValueError:
            parsed = None
        if parsed is not None:
            return _from_datetime_value(parsed, text)

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        return _from_datetime_value(parsed, text)

    naive_match = _NAIVE_ISO_RE.match(text)
    dmy_match = _DMY_WITH_TIME_RE.match(text)
    if naive_match is not None:
        date_part, time_part = naive_match.group("date"), naive_match.group("time")
        parsed_date = as_date(date_part)
    elif dmy_match is not None:
        date_part, time_part = dmy_match.group("date"), dmy_match.group("time")
        parsed_date = as_date(date_part)
    else:
        parsed_date = None
    if parsed_date is not None:
        try:
            parsed_time = time.fromisoformat(time_part)
        except ValueError:
            return None
        naive = datetime.combine(parsed_date, parsed_time)
        return _from_datetime_value(naive, text)

    parsed_date = as_date(text)
    if parsed_date is not None:
        return ParsedTimestamp(
            occurred_at=datetime.combine(parsed_date, time.min, tzinfo=UTC),
            original=text,
            tz=None,
            granularity="date",
            tz_assumed=False,
        )
    return None


# -- event drafts (pure generation input/output) --------------------------------


@dataclass(slots=True)
class EventDraft:
    """One proposed timeline event, before it becomes an artifact."""

    title: str
    description: str | None
    occurred_at: datetime | None
    original: str
    tz: str | None
    tz_assumed: bool
    granularity: str | None
    semantics: str
    origin: str  # "record" | "artifact"
    evidence_file_id: str | None
    source_record_id: str | None
    record_no: int | None
    locator_field: str
    locator_index: int | None
    missing_timestamp: bool
    flags: list[str] = dataclass_field(default_factory=list)
    conflicts: list[dict[str, object]] = dataclass_field(default_factory=list)
    existing_event_id: str | None = None

    def locator(self) -> dict[str, object]:
        locator: dict[str, object] = {"record_no": self.record_no, "field": self.locator_field}
        if self.locator_index is not None:
            locator["index"] = self.locator_index
        return locator

    def sort_key(self) -> tuple[str, int, str, int, str]:
        return (
            self.evidence_file_id or "",
            self.record_no or 0,
            self.locator_field,
            self.locator_index or 0,
            self.title,
        )

    def proposal_key(self) -> str:
        """Stable identity of this proposal across retries and re-runs."""
        return canonical_hash(
            {
                "source_record_id": self.source_record_id,
                "field": self.locator_field,
                "index": self.locator_index,
                "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
                "original": self.original,
            }
        )

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "timeline_proposal",
            "kind": COMMIT_KIND,
            "title": self.title,
            "description": self.description,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "original_timestamp": self.original,
            "tz": self.tz,
            "tz_assumed": self.tz_assumed,
            "time_granularity": self.granularity,
            "time_semantics": self.semantics,
            "missing_timestamp": self.missing_timestamp,
            "proposal_key": self.proposal_key(),
            "evidence_file_id": self.evidence_file_id,
            "source_record_id": self.source_record_id,
            "source_locator": self.locator(),
            "flags": sorted(set(self.flags)),
        }
        if self.conflicts:
            payload["conflicts"] = list(self.conflicts)
        if self.existing_event_id is not None:
            payload["existing_event_id"] = self.existing_event_id
        return payload


def _title_for(field_name: str, original: str, *, prefix: str = "") -> str:
    text = f"{prefix}{field_name}: {original}" if prefix else f"{field_name}: {original}"
    return text[:TITLE_MAX]


def _description_for(record_no: int | None, field_name: str, filename: str | None) -> str:
    where = f"record {record_no}" if record_no is not None else "an extraction artifact"
    source = f" of {filename}" if filename else ""
    return f"Derived from {where}{source}, field {field_name!r}"[:DESCRIPTION_MAX]


def drafts_from_record(
    *,
    record_id: str,
    evidence_file_id: str,
    record_no: int,
    raw_data: Mapping[str, Any],
    filename: str | None,
) -> tuple[list[EventDraft], int]:
    """Proposals from one structured record's date-like fields.

    Returns (drafts, skipped_non_scalar). Unparseable values in strongly
    date-like fields become flagged ``missing_timestamp`` proposals; weak
    fields are skipped without a proposal (their name was only a hint).
    """
    drafts: list[EventDraft] = []
    skipped = 0
    for field_name, value in raw_data.items():
        if not looks_like_time_field(field_name):
            continue
        if isinstance(value, (list, tuple, dict)) or value is None:
            skipped += 1
            continue
        if isinstance(value, str) and not value.strip():
            skipped += 1
            continue
        original = str(value).strip()[:200]
        parsed = parse_timestamp(value)
        if parsed is None:
            if is_strong_time_field(field_name):
                drafts.append(
                    EventDraft(
                        title=_title_for(field_name, original),
                        description=_description_for(record_no, field_name, filename),
                        occurred_at=None,
                        original=original,
                        tz=None,
                        tz_assumed=False,
                        granularity=None,
                        semantics=classify_time_semantics(field_name),
                        origin="record",
                        evidence_file_id=evidence_file_id,
                        source_record_id=record_id,
                        record_no=record_no,
                        locator_field=field_name,
                        locator_index=None,
                        missing_timestamp=True,
                    )
                )
            else:
                skipped += 1
            continue
        drafts.append(
            EventDraft(
                title=_title_for(field_name, parsed.original),
                description=_description_for(record_no, field_name, filename),
                occurred_at=parsed.occurred_at,
                original=parsed.original,
                tz=parsed.tz,
                tz_assumed=parsed.tz_assumed,
                granularity=parsed.granularity,
                semantics=classify_time_semantics(field_name),
                origin="record",
                evidence_file_id=evidence_file_id,
                source_record_id=record_id,
                record_no=record_no,
                locator_field=field_name,
                locator_index=None,
                missing_timestamp=parsed.occurred_at is None,
            )
        )
    return drafts, skipped


def drafts_from_artifact(
    *,
    artifact_id: str,
    payload: Mapping[str, Any],
    record_no: int | None,
    evidence_file_id: str | None,
    source_record_id: str | None,
    filename: str | None,
    max_events: int = 10,
) -> list[EventDraft]:
    """Proposals from a phase-2 extraction artifact's validated fields.

    ``transaction_dates`` are used verbatim (they were source-validated at
    extraction time); ``events`` statements yield a proposal only when the
    statement itself establishes a date - the time of a statement's event is
    otherwise unknown and stays missing, never guessed.
    """
    fields = payload.get("fields")
    if not isinstance(fields, Mapping):
        return []
    drafts: list[EventDraft] = []

    dates = fields.get("transaction_dates")
    if isinstance(dates, list):
        for index, value in enumerate(dates):
            if not isinstance(value, str) or not value.strip():
                continue
            parsed = parse_timestamp(value)
            original = value.strip()[:200]
            drafts.append(
                EventDraft(
                    title=_title_for("transaction_dates", original, prefix=""),
                    description=_description_for(record_no, "transaction_dates", filename),
                    occurred_at=parsed.occurred_at if parsed else None,
                    original=original,
                    tz=parsed.tz if parsed else None,
                    tz_assumed=parsed.tz_assumed if parsed else False,
                    granularity=parsed.granularity if parsed else None,
                    semantics="record_occurs_on",
                    origin="artifact",
                    evidence_file_id=evidence_file_id,
                    source_record_id=source_record_id,
                    record_no=record_no,
                    locator_field="transaction_dates",
                    locator_index=index,
                    missing_timestamp=parsed is None,
                )
            )

    events = fields.get("events")
    if isinstance(events, list):
        counted = 0
        for index, value in enumerate(events):
            if counted >= max_events:
                break
            if not isinstance(value, str) or not value.strip():
                continue
            counted += 1
            text = value.strip()
            match = _EMBEDDED_DATE_RE.search(text)
            parsed = parse_timestamp(match.group(0)) if match else None
            if parsed is None:
                # Statement with no established time: keep it visible as a
                # missing-timestamp proposal, never invent a date.
                drafts.append(
                    EventDraft(
                        title=text[:TITLE_MAX],
                        description=_description_for(record_no, "events", filename),
                        occurred_at=None,
                        original=text[:200],
                        tz=None,
                        tz_assumed=False,
                        granularity=None,
                        semantics="statement_refers_to_event",
                        origin="artifact",
                        evidence_file_id=evidence_file_id,
                        source_record_id=source_record_id,
                        record_no=record_no,
                        locator_field="events",
                        locator_index=index,
                        missing_timestamp=True,
                    )
                )
                continue
            drafts.append(
                EventDraft(
                    title=text[:TITLE_MAX],
                    description=_description_for(record_no, "events", filename),
                    occurred_at=parsed.occurred_at,
                    original=parsed.original,
                    tz=parsed.tz,
                    tz_assumed=parsed.tz_assumed,
                    granularity=parsed.granularity,
                    semantics="statement_refers_to_event",
                    origin="artifact",
                    evidence_file_id=evidence_file_id,
                    source_record_id=source_record_id,
                    record_no=record_no,
                    locator_field="events",
                    locator_index=index,
                    missing_timestamp=False,
                )
            )
    _ = artifact_id  # artifact identity lives in the recorded artifact row
    return drafts


@dataclass(frozen=True, slots=True)
class ExistingEventFacts:
    """Row-level facts for one authoritative timeline event."""

    id: str
    evidence_file_id: str | None
    occurred_at: datetime
    title: str
    proposal_key: str | None


def annotate_drafts(
    drafts: Sequence[EventDraft], existing: Sequence[ExistingEventFacts]
) -> dict[str, int]:
    """Flag duplicates, cross-source conflicts and overlaps with the timeline.

    Deterministic and ordering-stable (drafts are annotated in sort order, so
    the first occurrence keeps the clean payload and later ones reference it).
    """
    counts = {"duplicates": 0, "conflicts": 0, "overlaps": 0}
    ordered = sorted(drafts, key=lambda draft: draft.sort_key())

    # Duplicate proposals: same evidence, same instant, same title.
    seen: dict[tuple[str, str, str], EventDraft] = {}
    for draft in ordered:
        if draft.occurred_at is None or draft.missing_timestamp:
            continue
        key = (
            draft.evidence_file_id or "",
            draft.occurred_at.isoformat(),
            normalize_text(draft.title),
        )
        first = seen.get(key)
        if first is not None:
            draft.flags.append("duplicate_proposal")
            draft.conflicts.append(
                {"with": first.locator(), "reason": "same time and title as another proposal"}
            )
            counts["duplicates"] += 1
        else:
            seen[key] = draft

    # Cross-source conflicts: raw record and extraction artifact disagree on
    # the time of the same source record.
    by_record: dict[str, list[EventDraft]] = {}
    for draft in ordered:
        if draft.source_record_id and draft.occurred_at is not None and not draft.missing_timestamp:
            by_record.setdefault(draft.source_record_id, []).append(draft)
    for record_drafts in by_record.values():
        record_side = [d for d in record_drafts if d.origin == "record"]
        artifact_side = [d for d in record_drafts if d.origin == "artifact"]
        if not record_side or not artifact_side:
            continue
        record_dates = {d.occurred_at.date() for d in record_side if d.occurred_at}
        artifact_dates = {d.occurred_at.date() for d in artifact_side if d.occurred_at}
        if not (record_dates & artifact_dates):
            for draft in record_side:
                draft.flags.append("conflicting_timestamp")
                for other in artifact_side:
                    draft.conflicts.append(
                        {
                            "with": other.locator(),
                            "value": other.occurred_at.isoformat() if other.occurred_at else None,
                            "reason": "extraction artifact reports a different time",
                        }
                    )
            for draft in artifact_side:
                draft.flags.append("conflicting_timestamp")
                for other in record_side:
                    draft.conflicts.append(
                        {
                            "with": other.locator(),
                            "value": other.occurred_at.isoformat() if other.occurred_at else None,
                            "reason": "source record reports a different time",
                        }
                    )
            counts["conflicts"] += len(record_side) + len(artifact_side)

    # Overlaps with the authoritative timeline (same evidence, same day).
    existing_by_evidence: dict[str, list[ExistingEventFacts]] = {}
    for event in existing:
        if event.evidence_file_id:
            existing_by_evidence.setdefault(event.evidence_file_id, []).append(event)
    for draft in ordered:
        if draft.occurred_at is None or draft.missing_timestamp or not draft.evidence_file_id:
            continue
        day = draft.occurred_at.date()
        for event in existing_by_evidence.get(draft.evidence_file_id, ()):
            if event.occurred_at.astimezone(UTC).date() == day:
                draft.flags.append("overlaps_existing_timeline")
                draft.existing_event_id = event.id
                counts["overlaps"] += 1
                break
    return counts


# -- execution (bounded job runner) ----------------------------------------------


@dataclass(frozen=True, slots=True)
class RecordFacts:
    id: str
    evidence_file_id: str
    record_no: int
    raw_data: Mapping[str, Any]
    filename: str | None


async def _load_records(
    session: AsyncSession, case_id: uuid.UUID, cap: int
) -> tuple[list[RecordFacts], bool]:
    result = await session.execute(
        select(SourceRecord, EvidenceFile.original_filename)
        .join(EvidenceFile, SourceRecord.evidence_file_id == EvidenceFile.id)
        .where(
            EvidenceFile.case_id == str(case_id),
            EvidenceFile.deleted_at.is_(None),
        )
        .order_by(EvidenceFile.created_at, EvidenceFile.id, SourceRecord.record_no)
        .limit(cap + 1)
    )
    rows = result.all()
    bounded = len(rows) > cap
    facts = [
        RecordFacts(
            id=str(record.id),
            evidence_file_id=str(record.evidence_file_id),
            record_no=record.record_no,
            raw_data=dict(record.raw_data),
            filename=filename,
        )
        for record, filename in rows[:cap]
    ]
    return facts, bounded


async def _load_extraction_artifacts(
    session: AsyncSession, case_id: uuid.UUID, cap: int
) -> tuple[list[DerivedArtifact], bool]:
    result = await session.execute(
        select(DerivedArtifact)
        .where(
            DerivedArtifact.case_id == str(case_id),
            DerivedArtifact.kind == "extraction",
            DerivedArtifact.status.in_(("pending_review", "approved")),
        )
        .order_by(DerivedArtifact.created_at, DerivedArtifact.id)
        .limit(cap + 1)
    )
    rows = list(result.scalars())
    return rows[:cap], len(rows) > cap


async def _load_existing_events(
    session: AsyncSession, case_id: uuid.UUID
) -> list[ExistingEventFacts]:
    result = await session.execute(
        select(TimelineEvent).where(TimelineEvent.case_id == str(case_id))
    )
    facts: list[ExistingEventFacts] = []
    for event in result.scalars():
        payload = event.payload or {}
        key = payload.get("proposal_key")
        facts.append(
            ExistingEventFacts(
                id=str(event.id),
                evidence_file_id=str(event.evidence_file_id) if event.evidence_file_id else None,
                occurred_at=event.occurred_at,
                title=event.title,
                proposal_key=str(key) if key else None,
            )
        )
    return facts


async def execute_timeline_reconstruction(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    settings: Settings,
) -> None:
    """Run one pending reconstruction job to a terminal state.

    Proposals are never a job failure. Only authorization loss or unexpected
    crashes fail the job - always with a typed code. Cancellation and timeout
    are cooperative between the bounded stages.
    """
    job = await session.get(AnalysisJob, job_id)
    if job is None or job.status != "pending":
        return
    case_id = uuid.UUID(str(job.case_id))
    actor_id = uuid.UUID(str(job.actor_id)) if job.actor_id else None

    if actor_id is None:
        await _fail_job(
            session, job, code="RECONSTRUCTION_FAILED", error="job has no actor reference"
        )
        return
    if not await still_authorized_for_case(
        session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_EVIDENCE_READ
    ):
        await _fail_job(
            session,
            job,
            code=CODE_CASE_ACCESS_DENIED,
            error="access to this case was revoked before reconstruction ran",
            denial=True,
        )
        return
    if job.cancel_requested:
        await _stop_job(session, job, stop="cancel", summary={}, case_id=case_id, actor_id=actor_id)
        return

    jobs_svc.transition(job, "running")
    await session.commit()

    summary: dict[str, Any] = {
        "records_scanned": 0,
        "records_bounded": False,
        "artifacts_scanned": 0,
        "artifacts_bounded": False,
        "drafts_generated": 0,
        "proposals_recorded": 0,
        "proposals_reused": 0,
        "proposals_committed_skipped": 0,
        "duplicates": 0,
        "conflicts": 0,
        "overlaps": 0,
        "missing_timestamps": 0,
        "ambiguous_timezones": 0,
    }
    stage = "load-records"
    try:
        records, records_bounded = await _load_records(
            session, case_id, settings.TIMELINE_MAX_RECORDS
        )
        summary["records_scanned"] = len(records)
        summary["records_bounded"] = records_bounded

        stage = "load-artifacts"
        artifacts, artifacts_bounded = await _load_extraction_artifacts(
            session, case_id, settings.TIMELINE_MAX_ARTIFACTS
        )
        summary["artifacts_scanned"] = len(artifacts)
        summary["artifacts_bounded"] = artifacts_bounded

        stage = "load-existing"
        existing = await _load_existing_events(session, case_id)
        committed_keys = {
            event.proposal_key for event in existing if event.proposal_key is not None
        }

        await session.refresh(job)
        stop = jobs_svc.should_stop(job)
        if stop is not None:
            await _stop_job(
                session, job, stop=stop, summary=summary, case_id=case_id, actor_id=actor_id
            )
            return

        stage = "draft"
        drafts: list[EventDraft] = []
        for record in records:
            record_drafts, _ = drafts_from_record(
                record_id=record.id,
                evidence_file_id=record.evidence_file_id,
                record_no=record.record_no,
                raw_data=record.raw_data,
                filename=record.filename,
            )
            drafts.extend(record_drafts)
        for artifact in artifacts:
            payload = artifact.payload or {}
            record_no = payload.get("record_no")
            evidence_file_id = str(artifact.evidence_file_id) if artifact.evidence_file_id else None
            source_record_id = str(artifact.source_record_id) if artifact.source_record_id else None
            drafts.extend(
                drafts_from_artifact(
                    artifact_id=str(artifact.id),
                    payload=payload,
                    record_no=record_no if isinstance(record_no, int) else None,
                    evidence_file_id=evidence_file_id,
                    source_record_id=source_record_id,
                    filename=None,
                )
            )

        fresh = [draft for draft in drafts if draft.proposal_key() not in committed_keys]
        summary["proposals_committed_skipped"] = len(drafts) - len(fresh)
        counts = annotate_drafts(fresh, existing)
        summary.update(counts)
        summary["drafts_generated"] = len(fresh)
        summary["missing_timestamps"] = sum(1 for d in fresh if d.missing_timestamp)
        summary["ambiguous_timezones"] = sum(1 for d in fresh if d.tz_assumed)

        stage = "record"
        jobs_svc.advance(job, processed=0, total=len(fresh))
        await session.commit()
        for index, draft in enumerate(sorted(fresh, key=lambda d: d.sort_key()), start=1):
            await session.refresh(job)
            stop = jobs_svc.should_stop(job)
            if stop is not None:
                await _stop_job(
                    session,
                    job,
                    stop=stop,
                    summary=summary,
                    case_id=case_id,
                    actor_id=actor_id,
                )
                return
            if not await still_authorized_for_case(
                session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_EVIDENCE_READ
            ):
                await _fail_job(
                    session,
                    job,
                    code=CODE_CASE_ACCESS_DENIED,
                    error="access to this case was revoked mid-run; reconstruction stopped",
                    denial=True,
                    summary=summary,
                )
                return

            validation_errors: list[dict[str, object]] = []
            if draft.missing_timestamp:
                validation_errors.append(
                    {
                        "field": "timestamp",
                        "code": "missing_timestamp",
                        "message": (
                            "no timestamp could be established from the source; "
                            "this proposal cannot be committed until a reviewer "
                            "supplies the time elsewhere"
                        ),
                    }
                )
            if draft.tz_assumed:
                validation_errors.append(
                    {
                        "field": "timestamp",
                        "code": "ambiguous_timezone",
                        "message": (
                            "the source timestamp has no time zone; it was "
                            "interpreted as UTC for ordering and flagged"
                        ),
                    }
                )
            _, created = await artifacts_svc.record_artifact(
                session,
                case_id=case_id,
                kind="timeline_proposal",
                origin="deterministic",
                payload=draft.as_payload(),
                evidence_file_id=(
                    uuid.UUID(draft.evidence_file_id) if draft.evidence_file_id else None
                ),
                source_record_id=(
                    uuid.UUID(draft.source_record_id) if draft.source_record_id else None
                ),
                source_locator=draft.locator(),
                validation_status="flagged" if validation_errors else "valid",
                validation_errors=validation_errors or None,
                parser_version=TIMELINE_RECON_VERSION,
                analysis_job_id=job.id,
                created_by=actor_id,
                status="pending_review",
            )
            summary["proposals_recorded" if created else "proposals_reused"] += 1
            jobs_svc.advance(job, processed=index, total=len(fresh))
            await session.commit()

        job.result_summary = summary
        jobs_svc.transition(job, "succeeded")
        await session.flush()
        await audit_svc.record_audit(
            session,
            actor_id=actor_id,
            action="reconstruction.completed",
            resource_type="analysis_job",
            resource_id=job.id,
            case_id=case_id,
            metadata={
                "drafts_generated": summary["drafts_generated"],
                "proposals_recorded": summary["proposals_recorded"],
                "missing_timestamps": summary["missing_timestamps"],
            },
        )
        await session.commit()
    except Exception:
        logger.exception("timeline reconstruction crashed", extra={"job_id": str(job.id)})
        await session.rollback()
        await session.refresh(job)
        await _fail_job(
            session,
            job,
            code="RECONSTRUCTION_FAILED",
            error=f"unexpected error during stage {stage}",
            summary=summary,
        )


# -- commit (through the existing authorized timeline service) --------------------


class TimelineRejected(ValueError):
    """Commit refused; ``code`` carries the typed API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def commit_timeline_proposal(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    artifact_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> tuple[TimelineEvent, bool]:
    """Commit one reviewer-approved proposal via ``timeline.record_event``.

    Authorization is re-checked immediately before the write. Commit is
    idempotent: an event already carrying this proposal's key is returned
    instead of a second row. Existing events are never modified.
    """
    artifact = await artifacts_svc.get_artifact(session, case_id, artifact_id)
    if artifact is None:
        raise TimelineRejected(CODE_ARTIFACT_NOT_FOUND, f"artifact {artifact_id} not found")
    if artifact.kind != "timeline_proposal":
        raise TimelineRejected(
            CODE_ARTIFACT_KIND_UNSUPPORTED, "artifact is not a timeline proposal"
        )
    if artifact.status != "approved":
        raise TimelineRejected(
            CODE_PROPOSAL_NOT_APPROVED,
            "proposal must be approved by a reviewer before it can be committed",
        )
    payload = artifact.payload or {}
    occurred_raw = payload.get("occurred_at")
    if payload.get("missing_timestamp") or not isinstance(occurred_raw, str):
        raise TimelineRejected(
            CODE_TIMELINE_TIMESTAMP_MISSING,
            "proposal has no established timestamp; it cannot be committed",
        )
    try:
        occurred_at = datetime.fromisoformat(occurred_raw)
    except ValueError as exc:
        raise TimelineRejected(
            CODE_TIMELINE_TIMESTAMP_MISSING, "proposal timestamp is not parseable"
        ) from exc
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)

    if not await still_authorized_for_case(
        session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_CASE_UPDATE
    ):
        raise TimelineRejected(
            CODE_CASE_ACCESS_DENIED,
            "access to this case was revoked before the proposal could be committed",
        )

    key = payload.get("proposal_key")
    if isinstance(key, str) and key:
        existing = await session.execute(
            select(TimelineEvent)
            .where(
                TimelineEvent.case_id == str(case_id),
                TimelineEvent.payload["proposal_key"].astext == key,
            )
            .limit(1)
        )
        row = existing.scalars().first()
        if row is not None:
            return row, False

    kind = str(payload.get("kind") or COMMIT_KIND)
    if kind not in TIMELINE_EVENT_KINDS:
        kind = COMMIT_KIND
    description = payload.get("description")
    event = await timeline_svc.record_event(
        session=session,
        case_id=case_id,
        occurred_at=occurred_at,
        kind=kind,
        title=str(payload.get("title") or "Reconstructed event")[:255],
        description=str(description)[:1000] if description else None,
        evidence_file_id=(
            uuid.UUID(str(payload["evidence_file_id"])) if payload.get("evidence_file_id") else None
        ),
        actor_user_id=actor_id,
        payload={
            "origin": "timeline_reconstruction",
            "proposal_artifact_id": str(artifact.id),
            "proposal_key": key,
            "source_record_id": payload.get("source_record_id"),
            "source_locator": payload.get("source_locator"),
            "time_semantics": payload.get("time_semantics"),
            "original_timestamp": payload.get("original_timestamp"),
            "tz": payload.get("tz"),
            "tz_assumed": bool(payload.get("tz_assumed")),
        },
    )
    await session.flush()
    return event, True


# -- cooperative stop / failure (shared shape with the other runners) -------------


async def _stop_job(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    stop: str,
    summary: dict[str, Any],
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    if summary:
        job.result_summary = summary
    if stop == "cancel":
        jobs_svc.transition(job, "canceled")
        action = "reconstruction.canceled"
    else:
        job.error = f"timeline reconstruction timed out after {job.timeout_seconds}s"
        jobs_svc.transition(job, "failed")
        action = "reconstruction.timed_out"
    await session.flush()
    await audit_svc.record_audit(
        session,
        actor_id=actor_id,
        action=action,
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"drafts_generated": summary.get("drafts_generated", 0)} if summary else {},
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
        action="reconstruction.denied" if denial else "reconstruction.failed",
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"code": code, "stage": stage},
    )
    await session.commit()


async def run_timeline_reconstruction_job(app: FastAPI, job_id: uuid.UUID) -> None:
    """Background worker: own DB session, own scope, never raises."""
    from app.core.config import get_settings
    from app.db.postgres import Database

    settings: Settings = get_settings()
    database: Database = app.state.database
    factory: async_sessionmaker[AsyncSession] = database.session_factory()
    try:
        async with factory() as session:
            await execute_timeline_reconstruction(session, job_id=job_id, settings=settings)
    except Exception:  # session-level crash: fail the job best-effort
        logger.exception("background reconstruction failed", extra={"job_id": str(job_id)})
        async with factory() as session:
            job = await session.get(AnalysisJob, job_id)
            if job is not None and not jobs_svc.is_terminal(job.status):
                await _fail_job(
                    session,
                    job,
                    code="RECONSTRUCTION_FAILED",
                    error="background reconstruction task crashed",
                )
