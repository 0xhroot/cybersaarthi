"""Smart evidence ingestion copilot (feature 1): bounded extraction jobs.

Submission is idempotent (one active job per evidence file, attempt-numbered
idempotency keys); execution re-checks the submitter's authorization before
any evidence byte or model context is touched, verifies the stored sha256
against the original object before parsing, and records one derived artifact
per processed record through the Phase 1 artifact/job services.

The original evidence file is read-only here: this module never writes to
object storage, never rewrites recorded hashes, and never mutates custody
history. Model output is untrusted until it survives ``parse_structured`` +
``check_fields_against_source``; field-level problems are shown to reviewers,
never silently dropped. Cancellation and timeout are cooperative
(``should_stop`` between records) and a canceled job can never succeed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import CompletionResult
from app.ai.prompts import EXTRACTION_PROMPT_VERSION
from app.core import rbac
from app.core.codes import (
    CODE_CASE_ACCESS_DENIED,
    CODE_EMPTY_EVIDENCE,
    CODE_EVIDENCE_NOT_FOUND,
    CODE_EVIDENCE_UNAVAILABLE,
    CODE_EXTRACTION_ACTIVE,
    CODE_EXTRACTION_FAILED,
    CODE_EXTRACTION_PARSE_FAILED,
    CODE_INTEGRITY_MISMATCH,
    CODE_INTEGRITY_SOURCE_MISSING,
    CODE_INVALID_PAYLOAD,
    CODE_OCR_REQUIRED,
    CODE_UNSUPPORTED_FORMAT,
)
from app.core.config import Settings
from app.core.enums import EvidenceFormat
from app.models import (
    AnalysisJob,
    DerivedArtifact,
    EvidenceFile,
    SourceRecord,
)
from app.repositories.evidence_repository import EvidenceRepository
from app.schemas.evidence_extraction import EvidenceExtractionSchema
from app.services import analysis_jobs as jobs_svc
from app.services import artifacts as artifacts_svc
from app.services import audit as audit_svc
from app.services.authorization import still_authorized_for_case
from app.services.parsing import OCRRequiredError, ParseError, parse
from app.services.structured_extraction import (
    FieldIssue,
    check_fields_against_source,
    parse_structured,
)
from app.services.validation import (
    UploadValidationError,
    detect_encoding,
    detect_format,
    fingerprint,
)

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.storage import Storage

logger = logging.getLogger(__name__)

EXTRACTION_FEATURE = "ingestion"
RAW_EXCERPT_CHARS = 2000
SUPPORTED_FORMAT_VALUES = frozenset(fmt.value for fmt in EvidenceFormat)


class ExtractionRejected(ValueError):
    """Submission refused; ``code`` carries the typed API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ExtractionRunError(ValueError):
    """Deterministic job-abort during execution; ``code`` is machine-readable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PageExtractor(Protocol):
    """The bounded model-call surface the runner needs (AIService implements it)."""

    async def extract_page(self, *, label: str, text: str) -> CompletionResult: ...


# -- submission ------------------------------------------------------------


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


async def _active_extraction_job(
    session: AsyncSession, case_id: uuid.UUID, evidence_id: uuid.UUID
) -> AnalysisJob | None:
    """A non-terminal extraction job for this evidence, newest first."""
    result = await session.execute(
        select(AnalysisJob)
        .where(
            AnalysisJob.case_id == str(case_id),
            AnalysisJob.evidence_file_id == str(evidence_id),
            AnalysisJob.feature == EXTRACTION_FEATURE,
            AnalysisJob.status.in_(("pending", "running")),
        )
        .order_by(AnalysisJob.created_at.desc())
    )
    return result.scalars().first()


async def _attempt_count(session: AsyncSession, case_id: uuid.UUID, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(AnalysisJob)
        .where(
            AnalysisJob.case_id == str(case_id),
            AnalysisJob.evidence_file_id == str(evidence_id),
            AnalysisJob.feature == EXTRACTION_FEATURE,
        )
    )
    return int(result.scalar_one())


def _clear_stale(job: AnalysisJob, settings: Settings) -> bool:
    """Terminal-ize a stale job left behind by a restart. Returns False when
    the transition no longer applies (it reached a terminal state meanwhile).

    No durable queue exists in this deployment, so an orphaned pending/running
    job would otherwise lock its evidence forever; clearing it is honest - the
    job never reports success.
    """
    try:
        if job.status == "running":
            if not jobs_svc.is_timed_out(job):
                return False  # genuinely running (or never started): stay active
            job.error = f"superseded: exceeded {job.timeout_seconds}s timeout budget"
            jobs_svc.transition(job, "failed")
        elif job.status == "pending":
            if (datetime.now(UTC) - job.created_at).total_seconds() <= 2 * max(
                1, job.timeout_seconds or settings.EXTRACTION_TIMEOUT_SECONDS
            ):
                return False  # freshly queued, not stale
            jobs_svc.transition(job, "canceled")
        else:
            return False
        return True
    except jobs_svc.InvalidJobTransition:  # pragma: no cover - raced to terminal
        return False


async def submit_extraction(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    actor_id: uuid.UUID,
    settings: Settings,
) -> tuple[AnalysisJob, bool]:
    """Validate and (idempotently) enqueue one extraction run.

    Raises :class:`ExtractionRejected` with a typed code for unavailable,
    unsupported or already-running targets. Attempt-numbered idempotency keys
    make duplicate submissions collapse onto one job (``created=False``) while
    a genuine retry after failure/cancellation becomes attempt N+1.
    """
    evidence = await _scoped_evidence(session, case_id, evidence_id)
    if evidence is None:
        raise ExtractionRejected(CODE_EVIDENCE_NOT_FOUND, "evidence not found in this case")
    if evidence.deleted_at is not None:
        raise ExtractionRejected(
            CODE_EVIDENCE_UNAVAILABLE,
            "evidence is deleted; restore it before extraction",
        )

    active = await _active_extraction_job(session, case_id, evidence_id)
    if active is not None and not _clear_stale(active, settings):
        raise ExtractionRejected(
            CODE_EXTRACTION_ACTIVE,
            "an extraction job is already running for this evidence",
        )
    if active is not None:
        await session.flush()

    if evidence.format is None:
        try:
            detect_format(evidence.original_filename, b"")
        except UploadValidationError as exc:
            raise ExtractionRejected(
                CODE_UNSUPPORTED_FORMAT,
                "evidence format is not supported for extraction (supported: csv, json, txt, pdf)",
            ) from exc
    elif evidence.format not in SUPPORTED_FORMAT_VALUES:
        raise ExtractionRejected(
            CODE_UNSUPPORTED_FORMAT,
            f"evidence format {evidence.format!r} is not supported for extraction",
        )

    attempt = await _attempt_count(session, case_id, evidence_id) + 1
    idempotency_key = f"extraction:{evidence_id}:a{attempt}"
    try:
        return await jobs_svc.create_job(
            session,
            case_id=case_id,
            feature=EXTRACTION_FEATURE,
            idempotency_key=idempotency_key,
            actor_id=actor_id,
            evidence_file_id=evidence_id,
            timeout_seconds=settings.EXTRACTION_TIMEOUT_SECONDS,
        )
    except IntegrityError:
        # Concurrent duplicate submission won the unique-key race: return the
        # row the winner created instead of starting a second run.
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


# -- authorization recheck: see app.services.authorization (shared) -----------


# -- records ---------------------------------------------------------------


async def _load_or_create_records(
    session: AsyncSession,
    *,
    evidence: EvidenceFile,
    raw: bytes,
) -> list[SourceRecord]:
    """Existing source records, or parse + create them idempotently.

    Uses the shared ``(evidence_file_id, record_no)`` uniqueness so a retried
    run converges on the same records instead of duplicating them. Metadata
    completed here (format/encoding/record_count) is filled only when absent -
    evidence status is preserved exactly.
    """
    repo = EvidenceRepository(session)
    existing = await repo.get_source_records(evidence.id)
    if existing:
        return existing

    if evidence.format:
        fmt = EvidenceFormat(evidence.format)
    else:
        try:
            fmt = detect_format(evidence.original_filename, raw)
        except UploadValidationError as exc:
            raise ExtractionRunError(
                CODE_UNSUPPORTED_FORMAT,
                "evidence format could not be determined for extraction",
            ) from exc
    encoding = evidence.encoding or detect_encoding(raw)
    try:
        parsed = parse(raw, fmt, encoding)
    except OCRRequiredError as exc:
        raise ExtractionRunError(CODE_OCR_REQUIRED, str(exc)) from exc
    except ParseError as exc:
        raise ExtractionRunError(
            CODE_EXTRACTION_PARSE_FAILED, f"evidence could not be parsed: {exc}"
        ) from exc

    created: list[SourceRecord] = []
    for record_no, raw_data in enumerate(parsed, start=1):
        row = await repo.create_source_record(
            evidence_file_id=evidence.id,
            record_no=record_no,
            raw_data=raw_data,
        )
        if row is None:
            row = await repo.get_source_record(evidence.id, record_no)
        if row is not None:
            created.append(row)

    updates: dict[str, Any] = {}
    if not evidence.record_count:
        updates["record_count"] = len(parsed)
    if not evidence.format:
        updates["format"] = fmt.value
    if not evidence.encoding:
        updates["encoding"] = encoding
    if updates:
        await repo.update_evidence(
            evidence.id,
            status=evidence.status,
            status_detail=evidence.status_detail,
            **updates,
        )
    return created


def _unit_content(record: SourceRecord, fmt: EvidenceFormat | None) -> tuple[str, str]:
    """(model input, human label) for one record; '' content means skip."""
    raw = dict(record.raw_data)
    page = raw.get("page")
    if isinstance(page, int) and isinstance(raw.get("text"), str):
        return str(raw["text"]), f"page {page}"
    if fmt == EvidenceFormat.TXT and isinstance(raw.get("text"), str):
        return str(raw["text"]), f"record {record.record_no}"
    content = json.dumps(raw, ensure_ascii=False, default=str)
    return content, f"record {record.record_no}"


def _locator_and_source(
    record: SourceRecord,
) -> tuple[dict[str, object], dict[str, object]]:
    """Deterministic citation locator + the source mapping fields validate against.

    Page-style records cite ``field="text"`` (the page number is carried by
    ``record_no`` and deliberately excluded from matchable values, so a page
    number can never "back" a claimed value). Row records cite their first
    field and validate against the whole row.
    """
    raw = dict(record.raw_data)
    if isinstance(raw.get("page"), int) and "text" in raw:
        return {"record_no": record.record_no, "field": "text"}, {"text": raw["text"]}
    field_name = "text" if "text" in raw else next(iter(raw), "")
    return {"record_no": record.record_no, "field": field_name}, raw


def _field_stats(data: dict[str, Any], issues: tuple[FieldIssue, ...]) -> tuple[int, int]:
    """(fields proposed, fields source-verified) - the field validation metric."""
    issued = {issue.field for issue in issues}
    verified = sum(1 for name in data if name not in issued)
    return len(data), verified


async def validate_artifact_edit(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    artifact: DerivedArtifact,
    edited_fields: dict[str, Any],
) -> dict[str, Any]:
    """Load the artifact's own source record (case-scoped) and re-check edits.

    Editing is only possible while the source record still exists and still
    belongs to this case; otherwise the edit is refused with ``INVALID_PAYLOAD``
    instead of approving fields nothing can verify anymore.
    """
    if artifact.source_record_id is None:
        raise ExtractionRejected(
            CODE_INVALID_PAYLOAD,
            "artifact has no source record to re-validate the edit against",
        )
    record = await session.get(SourceRecord, uuid.UUID(str(artifact.source_record_id)))
    if record is None:
        raise ExtractionRejected(
            CODE_INVALID_PAYLOAD,
            "source record is no longer available; the edit cannot be verified",
        )
    evidence = await session.get(EvidenceFile, uuid.UUID(str(record.evidence_file_id)))
    if evidence is None or str(evidence.case_id) != str(case_id):
        raise ExtractionRejected(
            CODE_INVALID_PAYLOAD,
            "source record is not available in this case",
        )
    _, source = _locator_and_source(record)
    return validate_edited_fields(edited_fields, source)


async def _reviewable_artifact_for(
    session: AsyncSession, case_id: uuid.UUID, source_record_id: uuid.UUID
) -> DerivedArtifact | None:
    """A pending/approved extraction for this record (retry idempotency)."""
    result = await session.execute(
        select(DerivedArtifact)
        .where(
            DerivedArtifact.case_id == str(case_id),
            DerivedArtifact.kind == "extraction",
            DerivedArtifact.source_record_id == str(source_record_id),
            DerivedArtifact.status.in_(("pending_review", "approved")),
        )
        .limit(1)
    )
    return result.scalars().first()


# -- execution -------------------------------------------------------------


async def execute_extraction(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    settings: Settings,
    storage: Storage,
    extractor: PageExtractor,
) -> None:
    """Run one pending extraction job to a terminal state.

    Domain failures become explicit job states (never silent); unexpected
    errors propagate so the background wrapper can fail the job best-effort.
    """
    job = await session.get(AnalysisJob, job_id)
    if job is None or job.status != "pending":
        return
    case_id = uuid.UUID(str(job.case_id))
    evidence_id = uuid.UUID(str(job.evidence_file_id)) if job.evidence_file_id else None
    actor_id = uuid.UUID(str(job.actor_id)) if job.actor_id else None

    # Stage 1: authorization BEFORE any evidence bytes or model context.
    if actor_id is None or evidence_id is None:
        await _fail_job(
            session,
            job,
            code=CODE_EXTRACTION_FAILED,
            error="job is missing its evidence or actor reference",
        )
        return
    if not await still_authorized_for_case(
        session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_EVIDENCE_READ
    ):
        await _fail_job(
            session,
            job,
            code=CODE_CASE_ACCESS_DENIED,
            error="access to this case was revoked before extraction ran",
            denial=True,
        )
        return
    if job.cancel_requested:
        await _stop_job(session, job, stop="cancel", summary={}, case_id=case_id, actor_id=actor_id)
        return

    # Stage 2: load evidence (deleted between submit and run -> explicit fail).
    evidence = await _scoped_evidence(session, case_id, evidence_id)
    if evidence is None or evidence.deleted_at is not None:
        await _fail_job(
            session,
            job,
            code=CODE_EVIDENCE_UNAVAILABLE,
            error="evidence is no longer available for extraction",
        )
        return

    jobs_svc.transition(job, "running")
    await session.commit()

    summary: dict[str, Any] = {
        "artifacts_created": 0,
        "artifacts_flagged": 0,
        "artifacts_invalid": 0,
        "artifacts_reused": 0,
        "fields_total": 0,
        "fields_verified": 0,
        "units_total": 0,
        "units_skipped_empty": 0,
        "units_failed": 0,
    }
    stage = "fetch"
    try:
        # Stage 3: original bytes, hash-verified before anything parses them.
        if not await asyncio.to_thread(storage.exists, evidence.stored_key):
            raise ExtractionRunError(
                CODE_INTEGRITY_SOURCE_MISSING,
                "original stored object is unavailable; extraction aborted "
                "(no content is inferred without the source bytes)",
            )
        raw = await asyncio.to_thread(storage.download, evidence.stored_key)
        if fingerprint(raw) != evidence.sha256:
            raise ExtractionRunError(
                CODE_INTEGRITY_MISMATCH,
                "stored bytes do not match the recorded sha256; extraction "
                "aborted pending integrity verification",
            )

        # Stage 4: bounded, page-aware source records.
        stage = "parse"
        records = await _load_or_create_records(session, evidence=evidence, raw=raw)
        fmt = EvidenceFormat(evidence.format) if evidence.format else None
        summary["records_total"] = len(records)
        summary["records_bounded"] = len(records) > settings.EXTRACTION_MAX_PAGES
        units: list[tuple[SourceRecord, str, str]] = []
        for record in records[: settings.EXTRACTION_MAX_PAGES]:
            content, label = _unit_content(record, fmt)
            if not content.strip():
                summary["units_skipped_empty"] += 1
                continue
            units.append((record, content, label))
        summary["units_total"] = len(units)
        jobs_svc.advance(job, processed=0, total=len(units))
        await session.flush()
        await session.commit()

        if not units:
            raise ExtractionRunError(
                CODE_OCR_REQUIRED if fmt == EvidenceFormat.PDF else CODE_EMPTY_EVIDENCE,
                "PDF has no extractable text layer; OCR is required but "
                "unavailable in this deployment"
                if fmt == EvidenceFormat.PDF
                else "no extractable content in this evidence",
            )

        # Stage 5: per-record extract -> validate -> record, with cooperative
        # cancel/timeout and a fresh authorization recheck every iteration.
        stage = "extract"
        reviewable = 0
        run_error: str | None = None
        for index, (record, content, label) in enumerate(units, start=1):
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
                    error="access to this case was revoked mid-run; extraction stopped",
                    denial=True,
                    summary=summary,
                )
                return

            if await _reviewable_artifact_for(session, case_id, record.id) is not None:
                # Retry idempotency: this record already has output awaiting
                # review (or approved) - no second model call, no duplicates.
                summary["artifacts_reused"] += 1
                reviewable += 1
            else:
                try:
                    completion = await extractor.extract_page(
                        label=f"{label} of {evidence.original_filename}", text=content
                    )
                except Exception as exc:  # AI-layer failure -> honest partial/failed
                    summary["units_failed"] += 1
                    run_error = str(exc)[:300]
                    break
                status = await _record_extraction(
                    session,
                    job=job,
                    record=record,
                    content=content,
                    completion=completion,
                    case_id=case_id,
                    actor_id=actor_id,
                    summary=summary,
                )
                if status == "pending_review":
                    reviewable += 1

            jobs_svc.advance(job, processed=index, total=len(units))
            await session.commit()

        # Stage 6: honest terminal state from the counts.
        invalid = int(summary["artifacts_invalid"])
        if run_error is not None and reviewable == 0:
            await _fail_job(
                session,
                job,
                code=CODE_EXTRACTION_FAILED,
                error=run_error,
                summary=summary,
            )
            return
        if run_error is not None:
            summary["model_error"] = run_error
        job.result_summary = summary
        if invalid == 0 and run_error is None:
            jobs_svc.transition(job, "succeeded")
        elif reviewable > 0:
            if run_error is not None:
                job.error = run_error
            jobs_svc.transition(job, "partial")
        else:
            job.error = "every model response failed validation; no fields extracted"
            jobs_svc.transition(job, "failed")
        await session.flush()
        await audit_svc.record_audit(
            session,
            actor_id=actor_id,
            action="extraction.completed",
            resource_type="analysis_job",
            resource_id=job.id,
            case_id=case_id,
            metadata={"status": job.status, **_counts(summary)},
        )
        await session.commit()
    except ExtractionRunError as exc:
        await session.rollback()
        # Rollback expires loaded instances; re-read the job before terminal
        # writes (attribute access on the expired proxy would lazy-load IO in
        # a sync context and raise MissingGreenlet).
        await session.refresh(job)
        await _fail_job(session, job, code=exc.code, error=str(exc), summary=summary, stage=stage)
    except Exception:
        logger.exception("extraction job crashed", extra={"job_id": str(job.id)})
        await session.rollback()
        await session.refresh(job)
        await _fail_job(
            session,
            job,
            code=CODE_EXTRACTION_FAILED,
            error=f"unexpected error during stage {stage}",
            summary=summary,
            stage=stage,
        )


async def _record_extraction(
    session: AsyncSession,
    *,
    job: AnalysisJob,
    record: SourceRecord,
    content: str,
    completion: CompletionResult,
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
    summary: dict[str, Any],
) -> str:
    """Validate one model response and persist it as a derived artifact.

    Returns the artifact status (``pending_review`` or ``failed``).
    Outcomes: ``valid``/``flagged`` -> pending human review; ``invalid``
    -> failed state with a truncated raw excerpt kept for diagnostics and
    never presented as extracted content. Content-addressed recording makes
    an identical re-derivation a no-op (``artifacts_created`` unchanged).
    """
    locator, source = _locator_and_source(record)
    result = parse_structured(completion.text, EvidenceExtractionSchema)
    validation_status = result.status
    if result.data is not None:
        issues = check_fields_against_source(result.data, source)
        total, verified = _field_stats(result.data, issues)
        summary["fields_total"] += total
        summary["fields_verified"] += verified
        # ``record_no`` is part of the payload on purpose: content-addressed
        # recording must stay unique per source record, so two pages with
        # identical extracted fields remain two citable artifacts.
        payload: dict[str, Any] = {"fields": dict(result.data), "record_no": record.record_no}
        status = "pending_review"
        if issues:
            summary["artifacts_flagged"] += 1
        validation_errors: list[dict[str, object]] | None = (
            [issue.as_dict() for issue in issues] if issues else None
        )
    else:
        payload = {
            "extraction_failed": True,
            "record_no": record.record_no,
            "raw_response": completion.text[:RAW_EXCERPT_CHARS],
            "schema_issues": [issue.as_dict() for issue in result.issues],
        }
        status = "failed"
        summary["artifacts_invalid"] += 1
        validation_errors = [issue.as_dict() for issue in result.issues]

    _, created = await artifacts_svc.record_artifact(
        session,
        case_id=case_id,
        kind="extraction",
        origin="llm",
        payload=payload,
        evidence_file_id=uuid.UUID(str(record.evidence_file_id)),
        source_record_id=record.id,
        source_locator=locator,
        validation_status=validation_status,
        validation_errors=validation_errors,
        prompt_version=EXTRACTION_PROMPT_VERSION,
        model_profile="extraction",
        analysis_job_id=job.id,
        created_by=actor_id,
        status=status,
    )
    if created:
        summary["artifacts_created"] += 1
    return status


def _counts(summary: dict[str, Any]) -> dict[str, object]:
    """Audit-safe metadata: counts only, never extracted content."""
    return {
        key: summary[key]
        for key in (
            "units_total",
            "artifacts_created",
            "artifacts_flagged",
            "artifacts_invalid",
            "artifacts_reused",
        )
        if key in summary
    }


async def _stop_job(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    stop: str,
    summary: dict[str, Any],
    case_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    """Apply a cooperative stop: cancel wins over timeout, never 'succeeded'."""
    if summary:
        job.result_summary = summary
    if stop == "cancel":
        jobs_svc.transition(job, "canceled")
        action = "extraction.canceled"
    else:
        job.error = f"extraction timed out after {job.timeout_seconds}s"
        jobs_svc.transition(job, "failed")
        action = "extraction.timed_out"
    await session.flush()
    await audit_svc.record_audit(
        session,
        actor_id=actor_id,
        action=action,
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata=_counts(summary),
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
        action="extraction.denied" if denial else "extraction.failed",
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"code": code, "stage": stage},
    )
    await session.commit()


# -- background entry (mirrors the async-ingest pattern) --------------------


async def run_extraction_job(app: FastAPI, job_id: uuid.UUID) -> None:
    """Background worker: own DB session, own scope, never raises."""
    from app.core.config import get_settings
    from app.db.postgres import Database

    settings: Settings = get_settings()
    database: Database = app.state.database
    factory: async_sessionmaker[AsyncSession] = database.session_factory()
    try:
        async with factory() as session:
            await execute_extraction(
                session,
                job_id=job_id,
                settings=settings,
                storage=app.state.storage,
                extractor=app.state.ai_service,
            )
    except Exception:  # session-level crash: fail the job best-effort
        logger.exception("background extraction failed", extra={"job_id": str(job_id)})
        async with factory() as session:
            job = await session.get(AnalysisJob, job_id)
            if job is not None and not jobs_svc.is_terminal(job.status):
                await _fail_job(
                    session,
                    job,
                    code=CODE_EXTRACTION_FAILED,
                    error="background extraction task crashed",
                )


# -- review-time payload edits (approve-with-edit path) ---------------------


def validate_edited_fields(
    edited_fields: dict[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    """Re-validate an investigator's edited ``payload.fields`` against schema + source.

    Editing can change which values are kept, never which values exist: the
    edited fields must still satisfy the strict extraction schema and every
    value must still be present in the artifact's own source mapping (the
    record the original extraction was checked against). Raises
    :class:`ExtractionRejected` with ``INVALID_PAYLOAD`` otherwise.
    """
    result = parse_structured(json.dumps(edited_fields), EvidenceExtractionSchema)
    if result.data is None:
        raise ExtractionRejected(
            CODE_INVALID_PAYLOAD,
            "edited payload does not match the extraction schema: "
            + "; ".join(issue.code for issue in result.issues[:5]),
        )
    issues = check_fields_against_source(result.data, source)
    if issues:
        raise ExtractionRejected(
            CODE_INVALID_PAYLOAD,
            "edited values are not present in the source record: "
            + "; ".join(f"{issue.field}: {issue.code}" for issue in issues[:5]),
        )
    return result.data
