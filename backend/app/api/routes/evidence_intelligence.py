"""Routes: evidence intelligence foundation (case-scoped).

Shared read/review surface for all ten evidence-intelligence features: derived
artifacts (with provenance) and the analysis jobs that produced them. Feature
endpoints (extraction runs, contradiction scans, ...) live alongside this in
later phases and write through ``app.services.artifacts`` /
``app.services.analysis_jobs``; this router owns their listing, filters and the
human-review decision.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    assert_case_investigation_mutable,
    get_case_or_404,
    require_permission,
)
from app.api.errors import ApiHTTPException
from app.core import rbac
from app.core.codes import (
    CODE_AI_DISABLED,
    CODE_ARTIFACT_KIND_UNSUPPORTED,
    CODE_ARTIFACT_NOT_FOUND,
    CODE_ARTIFACT_NOT_REVIEWABLE,
    CODE_EVIDENCE_NOT_FOUND,
    CODE_EVIDENCE_UNAVAILABLE,
    CODE_EXTRACTION_ACTIVE,
    CODE_INVALID_FILTER,
    CODE_INVALID_PAYLOAD,
    CODE_JOB_NOT_FOUND,
    CODE_JOB_TERMINAL,
    CODE_UNSUPPORTED_FORMAT,
)
from app.core.config import Settings, get_settings
from app.db.postgres import get_db_session
from app.models import AnalysisJob, DerivedArtifact, User
from app.models.analysis_job import ANALYSIS_JOB_FEATURES, ANALYSIS_JOB_STATUSES
from app.models.derived_artifact import (
    DERIVED_ARTIFACT_KINDS,
    DERIVED_ARTIFACT_STATUSES,
    DERIVED_ARTIFACT_VALIDATION,
)
from app.schemas.evidence_integrity import JobSubmitResponse
from app.schemas.evidence_intelligence import (
    AnalysisJobOut,
    ArtifactListResponse,
    ArtifactReviewRequest,
    DerivedArtifactOut,
    ExtractionSubmitRequest,
    JobListResponse,
)
from app.services import analysis_jobs as jobs_svc
from app.services import artifacts as artifacts_svc
from app.services import audit as audit_svc
from app.services import evidence_extraction as extraction_svc

router = APIRouter(prefix="/cases", tags=["evidence-intelligence"])

# Typed HTTP mapping for extraction-submission rejections.
_REJECTION_HTTP: dict[str, int] = {
    CODE_EVIDENCE_NOT_FOUND: 404,
    CODE_EVIDENCE_UNAVAILABLE: 409,
    CODE_EXTRACTION_ACTIVE: 409,
    CODE_JOB_NOT_FOUND: 404,
    CODE_JOB_TERMINAL: 409,
    CODE_UNSUPPORTED_FORMAT: 422,
    CODE_INVALID_PAYLOAD: 422,
}


def _artifact_out(artifact: DerivedArtifact) -> DerivedArtifactOut:
    return DerivedArtifactOut(
        id=artifact.id,
        case_id=uuid.UUID(str(artifact.case_id)),
        kind=artifact.kind,
        origin=artifact.origin,
        status=artifact.status,
        validation_status=artifact.validation_status,
        evidence_file_id=(
            uuid.UUID(str(artifact.evidence_file_id)) if artifact.evidence_file_id else None
        ),
        source_record_id=(
            uuid.UUID(str(artifact.source_record_id)) if artifact.source_record_id else None
        ),
        source_locator=artifact.source_locator,
        payload=artifact.payload,
        content_hash=artifact.content_hash,
        parser_version=artifact.parser_version,
        prompt_version=artifact.prompt_version,
        model_profile=artifact.model_profile,
        analysis_job_id=(
            uuid.UUID(str(artifact.analysis_job_id)) if artifact.analysis_job_id else None
        ),
        validation_errors=artifact.validation_errors,
        review_note=artifact.review_note,
        reviewed_by=uuid.UUID(str(artifact.reviewed_by)) if artifact.reviewed_by else None,
        reviewed_at=artifact.reviewed_at,
        parent_artifact_id=(
            uuid.UUID(str(artifact.parent_artifact_id)) if artifact.parent_artifact_id else None
        ),
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


def _job_out(job: AnalysisJob) -> AnalysisJobOut:
    return AnalysisJobOut(
        id=job.id,
        case_id=uuid.UUID(str(job.case_id)),
        feature=job.feature,
        status=job.status,
        idempotency_key=job.idempotency_key,
        progress=job.progress,
        total_records=job.total_records,
        processed_records=job.processed_records,
        attempts=job.attempts,
        timeout_seconds=job.timeout_seconds,
        cancel_requested=job.cancel_requested,
        error=job.error,
        result_summary=job.result_summary,
        evidence_file_id=(
            uuid.UUID(str(job.evidence_file_id)) if job.evidence_file_id else None
        ),
        actor_id=uuid.UUID(str(job.actor_id)) if job.actor_id else None,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _assert_filter(name: str, value: str | None, allowed: tuple[str, ...]) -> None:
    if value is not None and value not in allowed:
        raise ApiHTTPException(422, CODE_INVALID_FILTER, f"unknown {name} {value!r}")


def _rejection(exc: extraction_svc.ExtractionRejected) -> ApiHTTPException:
    return ApiHTTPException(_REJECTION_HTTP.get(exc.code, 422), exc.code, str(exc))


# Audit-action prefix per cancellable feature (job feature -> audit vocabulary).
_CANCELABLE_FEATURES = ("ingestion", "custody")
_AUDIT_PREFIX = {"ingestion": "extraction", "custody": "custody"}


@router.post(
    "/{case_id}/evidence-intelligence/extract",
    response_model=JobSubmitResponse,
    status_code=202,
)
async def submit_evidence_extraction(
    case_id: uuid.UUID,
    body: ExtractionSubmitRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_INGESTION_RUN)),
) -> JobSubmitResponse:
    """Queue one bounded, page-aware extraction run for an evidence file.

    Idempotent: a second submission while a run is active is refused with a
    typed 409 (``EXTRACTION_ACTIVE``) instead of starting duplicate work, and
    attempt-numbered keys make retries after failure safe. The background task
    re-checks authorization, hash integrity and cancellation itself; this
    endpoint only validates, records and schedules (no unbounded work in the
    request handler).
    """
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    if not settings.AI_FEATURE_EXTRACTION:
        raise ApiHTTPException(403, CODE_AI_DISABLED, "AI extraction feature is disabled")
    try:
        job, created = await extraction_svc.submit_extraction(
            session,
            case_id=case_id,
            evidence_id=body.evidence_file_id,
            actor_id=user.id,
            settings=settings,
        )
    except extraction_svc.ExtractionRejected as exc:
        raise _rejection(exc) from exc
    if created:
        background_tasks.add_task(
            extraction_svc.run_extraction_job, request.app, uuid.UUID(str(job.id))
        )
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="extraction.submitted",
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"evidence_file_id": str(body.evidence_file_id), "duplicate": not created},
    )
    await session.commit()
    return JobSubmitResponse(job=_job_out(job), duplicate=not created)


@router.post(
    "/{case_id}/evidence-intelligence/jobs/{job_id}/cancel",
    response_model=AnalysisJobOut,
)
async def cancel_evidence_job(
    case_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_INGESTION_RUN)),
) -> AnalysisJobOut:
    """Request cooperative cancellation; a canceled job can never succeed.

    Covers every evidence-intelligence analysis feature (extraction runs and
    custody audits). Terminal jobs refuse with a typed 409 instead of
    pretending the flag changed anything.
    """
    await get_case_or_404(case_id, request, session)
    job = await jobs_svc.get_job(session, case_id, job_id)
    if job is None or job.feature not in _CANCELABLE_FEATURES:
        raise ApiHTTPException(404, CODE_JOB_NOT_FOUND, f"job {job_id} not found in this case")
    if jobs_svc.is_terminal(job.status):
        raise ApiHTTPException(409, CODE_JOB_TERMINAL, f"job is already {job.status}")
    jobs_svc.request_cancel(job)
    await session.flush()
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action=f"{_AUDIT_PREFIX.get(job.feature, job.feature)}.cancel_requested",
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"status": job.status},
    )
    await session.commit()
    return _job_out(job)


@router.get("/{case_id}/evidence-intelligence/artifacts", response_model=ArtifactListResponse)
async def list_evidence_artifacts(
    case_id: uuid.UUID,
    request: Request,
    kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
    validation_status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_EVIDENCE_READ)),
) -> ArtifactListResponse:
    """List derived artifacts (with provenance) for a case the caller can read."""
    _assert_filter("kind", kind, DERIVED_ARTIFACT_KINDS)
    _assert_filter("status", status, DERIVED_ARTIFACT_STATUSES)
    _assert_filter("validation_status", validation_status, DERIVED_ARTIFACT_VALIDATION)
    await get_case_or_404(case_id, request, session)
    rows, total = await artifacts_svc.list_artifacts(
        session,
        case_id,
        kind=kind,
        status=status,
        validation_status=validation_status,
        limit=limit,
        offset=offset,
    )
    return ArtifactListResponse(
        items=[_artifact_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}/evidence-intelligence/jobs", response_model=JobListResponse)
async def list_evidence_jobs(
    case_id: uuid.UUID,
    request: Request,
    feature: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> JobListResponse:
    """List analysis jobs (progress/lifecycle) for a case the caller can read."""
    _assert_filter("feature", feature, ANALYSIS_JOB_FEATURES)
    _assert_filter("status", status, ANALYSIS_JOB_STATUSES)
    await get_case_or_404(case_id, request, session)
    rows, total = await jobs_svc.list_jobs(
        session, case_id, feature=feature, status=status, limit=limit, offset=offset
    )
    return JobListResponse(
        items=[_job_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{case_id}/evidence-intelligence/artifacts/{artifact_id}/review",
    response_model=DerivedArtifactOut,
)
async def review_evidence_artifact(
    case_id: uuid.UUID,
    artifact_id: uuid.UUID,
    body: ArtifactReviewRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_FINDINGS_REVIEW)),
) -> DerivedArtifactOut:
    """Approve or reject one derived artifact (human review, audit-logged).

    Approving an extraction may carry edited fields (``payload``): edits are
    re-validated against the strict schema *and* the artifact's source record,
    then persisted as a new lineage-linked artifact while the original model
    output is marked ``superseded`` - review never rewrites recorded output.
    """
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    artifact = await artifacts_svc.get_artifact(session, case_id, artifact_id)
    if artifact is None:
        raise ApiHTTPException(404, CODE_ARTIFACT_NOT_FOUND, f"artifact {artifact_id} not found")

    target = artifact
    edit_meta: dict[str, Any] = {}
    if body.payload is not None:
        if artifact.status != "pending_review":
            raise ApiHTTPException(
                409,
                CODE_ARTIFACT_NOT_REVIEWABLE,
                f"artifact is {artifact.status}; only pending_review artifacts can be edited",
            )
        if artifact.kind != "extraction":
            raise ApiHTTPException(
                422,
                CODE_ARTIFACT_KIND_UNSUPPORTED,
                "payload edits apply only to extraction artifacts",
            )
        if body.decision != "approved":
            raise ApiHTTPException(
                422, CODE_INVALID_PAYLOAD, "an edited payload can only accompany approval"
            )
        fields = body.payload.get("fields")
        if not isinstance(fields, dict):
            raise ApiHTTPException(
                422, CODE_INVALID_PAYLOAD, "payload must contain a 'fields' object"
            )
        try:
            edited_fields = await extraction_svc.validate_artifact_edit(
                session, case_id=case_id, artifact=artifact, edited_fields=fields
            )
        except extraction_svc.ExtractionRejected as exc:
            raise _rejection(exc) from exc
        child, _ = await artifacts_svc.record_artifact(
            session,
            case_id=case_id,
            kind="extraction",
            origin=artifact.origin,
            payload={
                "fields": edited_fields,
                "record_no": (artifact.payload or {}).get("record_no"),
            },
            evidence_file_id=(
                uuid.UUID(str(artifact.evidence_file_id)) if artifact.evidence_file_id else None
            ),
            source_record_id=(
                uuid.UUID(str(artifact.source_record_id)) if artifact.source_record_id else None
            ),
            source_locator=artifact.source_locator,
            validation_status="valid",
            parser_version=artifact.parser_version,
            prompt_version=artifact.prompt_version,
            model_profile=artifact.model_profile,
            analysis_job_id=(
                uuid.UUID(str(artifact.analysis_job_id)) if artifact.analysis_job_id else None
            ),
            parent_artifact_id=artifact.id,
            created_by=user.id,
            status="pending_review",
        )
        edit_meta = {
            "edited": True,
            "original_artifact_id": str(artifact.id),
            "edited_artifact_id": str(child.id),
            "original_content_hash": artifact.content_hash,
            "edited_content_hash": child.content_hash,
        }
        if str(child.id) != str(artifact.id):
            # Immutable lineage: the model output stays byte-for-byte intact.
            artifact.status = "superseded"
            artifact.review_note = f"superseded by edited artifact {child.id}"
            await session.flush()
            target = child

    try:
        await artifacts_svc.review_artifact(
            session,
            artifact=target,
            decision=body.decision,
            reviewer_id=user.id,
            note=body.note,
        )
    except artifacts_svc.InvalidArtifactReview as exc:
        raise ApiHTTPException(409, CODE_ARTIFACT_NOT_REVIEWABLE, str(exc)) from exc
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action=f"derived_artifact.{body.decision}",
        resource_type="derived_artifact",
        resource_id=target.id,
        case_id=case_id,
        metadata={"kind": target.kind, "content_hash": target.content_hash, **edit_meta},
    )
    await session.commit()
    return _artifact_out(target)
