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

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    assert_case_investigation_mutable,
    get_case_or_404,
    require_permission,
)
from app.api.errors import ApiHTTPException
from app.core import rbac
from app.core.codes import (
    CODE_ARTIFACT_NOT_FOUND,
    CODE_ARTIFACT_NOT_REVIEWABLE,
    CODE_INVALID_FILTER,
)
from app.db.postgres import get_db_session
from app.models import AnalysisJob, DerivedArtifact, User
from app.models.analysis_job import ANALYSIS_JOB_FEATURES, ANALYSIS_JOB_STATUSES
from app.models.derived_artifact import (
    DERIVED_ARTIFACT_KINDS,
    DERIVED_ARTIFACT_STATUSES,
    DERIVED_ARTIFACT_VALIDATION,
)
from app.schemas.evidence_intelligence import (
    AnalysisJobOut,
    ArtifactListResponse,
    ArtifactReviewRequest,
    DerivedArtifactOut,
    JobListResponse,
)
from app.services import analysis_jobs as jobs_svc
from app.services import artifacts as artifacts_svc
from app.services import audit as audit_svc

router = APIRouter(prefix="/cases", tags=["evidence-intelligence"])


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
    """Approve or reject one derived artifact (human review, audit-logged)."""
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    artifact = await artifacts_svc.get_artifact(session, case_id, artifact_id)
    if artifact is None:
        raise ApiHTTPException(404, CODE_ARTIFACT_NOT_FOUND, f"artifact {artifact_id} not found")
    try:
        await artifacts_svc.review_artifact(
            session,
            artifact=artifact,
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
        resource_id=artifact.id,
        case_id=case_id,
        metadata={"kind": artifact.kind, "content_hash": artifact.content_hash},
    )
    await session.commit()
    return _artifact_out(artifact)
