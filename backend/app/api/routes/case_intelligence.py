"""Routes: phase-3 case intelligence (features A, B, C - case-scoped).

Submission surface for the three case-level analysis jobs (entity-pair
resolution, timeline reconstruction, contradiction detection) plus their two
review-driven write paths:

- committing a reviewer-approved timeline proposal through the existing
  authorized timeline service (idempotent; existing events never replaced);
- recording reviewer resolution states on contradiction candidates as
  appended child artifacts (never rewriting the candidate or the evidence).

Listing, filters, cancellation and the approve/reject review decision stay on
the shared evidence-intelligence router; artifacts are always written through
``app.services.artifacts`` and jobs through ``app.services.analysis_jobs``.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    assert_case_investigation_mutable,
    get_case_or_404,
    require_permission,
)
from app.api.errors import ApiHTTPException
from app.api.routes.evidence_intelligence import _artifact_out, _job_out
from app.api.routes.timeline import TimelineEventOut, _event_out
from app.core import rbac
from app.core.codes import (
    CODE_ARTIFACT_KIND_UNSUPPORTED,
    CODE_ARTIFACT_NOT_FOUND,
    CODE_ARTIFACT_NOT_REVIEWABLE,
    CODE_CASE_ACCESS_DENIED,
    CODE_CONTRADICTION_ACTIVE,
    CODE_CONTRADICTION_STATE_INVALID,
    CODE_FLOW_ACTIVE,
    CODE_PROPOSAL_NOT_APPROVED,
    CODE_RECONSTRUCTION_ACTIVE,
    CODE_RESOLUTION_ACTIVE,
    CODE_REVIEW_NOTE_REQUIRED,
    CODE_TIMELINE_TIMESTAMP_MISSING,
)
from app.core.config import Settings, get_settings
from app.db.postgres import get_db_session
from app.models import User
from app.schemas.evidence_integrity import JobSubmitResponse
from app.schemas.evidence_intelligence import (
    CaseAnalysisSubmitRequest,
    ContradictionResolveRequest,
    DerivedArtifactOut,
)
from app.services import analysis_jobs as jobs_svc
from app.services import audit as audit_svc
from app.services import contradiction_detection as contradiction_svc
from app.services import entity_matching as resolution_svc
from app.services import financial_flow as flow_svc
from app.services import timeline_reconstruction as reconstruction_svc

router = APIRouter(prefix="/cases", tags=["case-intelligence"])

# Typed HTTP mapping for feature-specific rejections.
_SUBMIT_HTTP: dict[str, int] = {
    CODE_CONTRADICTION_ACTIVE: 409,
    CODE_FLOW_ACTIVE: 409,
    CODE_RECONSTRUCTION_ACTIVE: 409,
    CODE_RESOLUTION_ACTIVE: 409,
}
_COMMIT_HTTP: dict[str, int] = {
    CODE_ARTIFACT_KIND_UNSUPPORTED: 422,
    CODE_ARTIFACT_NOT_FOUND: 404,
    CODE_CASE_ACCESS_DENIED: 403,
    CODE_PROPOSAL_NOT_APPROVED: 409,
    CODE_TIMELINE_TIMESTAMP_MISSING: 422,
}
_RESOLVE_HTTP: dict[str, int] = {
    CODE_ARTIFACT_KIND_UNSUPPORTED: 422,
    CODE_ARTIFACT_NOT_FOUND: 404,
    CODE_ARTIFACT_NOT_REVIEWABLE: 409,
    CODE_CASE_ACCESS_DENIED: 403,
    CODE_CONTRADICTION_STATE_INVALID: 422,
    CODE_REVIEW_NOTE_REQUIRED: 422,
}

# feature -> (active-job refusal code, audit action, timeout, background runner).
SubmitRunner = Callable[[Any, uuid.UUID], Awaitable[None]]
_FEATURES: dict[str, tuple[str, str, SubmitRunner]] = {
    "entity_resolution": (
        CODE_RESOLUTION_ACTIVE,
        "resolution.submitted",
        resolution_svc.run_entity_resolution_job,
    ),
    "timeline": (
        CODE_RECONSTRUCTION_ACTIVE,
        "reconstruction.submitted",
        reconstruction_svc.run_timeline_reconstruction_job,
    ),
    "contradiction": (
        CODE_CONTRADICTION_ACTIVE,
        "contradiction.submitted",
        contradiction_svc.run_contradiction_job,
    ),
    "financial_flow": (
        CODE_FLOW_ACTIVE,
        "flow.submitted",
        flow_svc.run_financial_flow_job,
    ),
}
_TIMEOUT_ATTR = {
    "entity_resolution": "RESOLUTION_TIMEOUT_SECONDS",
    "timeline": "TIMELINE_TIMEOUT_SECONDS",
    "contradiction": "CONTRADICTION_TIMEOUT_SECONDS",
    "financial_flow": "FLOW_TIMEOUT_SECONDS",
}


async def _submit_case_job(
    *,
    case_id: uuid.UUID,
    user: User,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings,
    session: AsyncSession,
    feature: str,
) -> JobSubmitResponse:
    """Shared idempotent submission for the case-level features.

    One active job per feature (typed 409 while one runs), honest clearing of
    stale jobs left by a restart, and attempt-numbered keys so retries after
    failure become new attempts while duplicate submissions collapse onto the
    same job. The background runner re-checks authorization itself.
    """
    active_code, audit_action, runner = _FEATURES[feature]
    timeout = int(getattr(settings, _TIMEOUT_ATTR[feature]))
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    try:
        job, created = await jobs_svc.submit_case_feature_job(
            session,
            case_id=case_id,
            feature=feature,
            actor_id=user.id,
            timeout_seconds=timeout,
            active_code=active_code,
        )
    except jobs_svc.FeatureJobActive as exc:
        raise ApiHTTPException(_SUBMIT_HTTP.get(exc.code, 409), exc.code, str(exc)) from exc
    if created:
        background_tasks.add_task(runner, request.app, uuid.UUID(str(job.id)))
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action=audit_action,
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={"feature": feature, "duplicate": not created},
    )
    await session.commit()
    return JobSubmitResponse(job=_job_out(job), duplicate=not created)


@router.post(
    "/{case_id}/evidence-intelligence/entity-resolution",
    response_model=JobSubmitResponse,
    status_code=202,
)
async def submit_entity_resolution(
    case_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    body: CaseAnalysisSubmitRequest | None = None,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_INGESTION_RUN)),
) -> JobSubmitResponse:
    """Queue one bounded entity-pair resolution run for the whole case.

    Compares the case's resolved entities (indexed probes only, never an
    all-pairs scan) and stores reviewable ``entity_resolution`` candidates.
    The local LLM is consulted only for ambiguous pairs when enabled; with AI
    disabled the run is deterministic-only. Approval of a candidate records a
    reviewed relationship (additive aliases) - it never merges entities.
    """
    _ = body
    return await _submit_case_job(
        case_id=case_id,
        user=user,
        request=request,
        background_tasks=background_tasks,
        settings=settings,
        session=session,
        feature="entity_resolution",
    )


@router.post(
    "/{case_id}/evidence-intelligence/timeline-reconstruction",
    response_model=JobSubmitResponse,
    status_code=202,
)
async def submit_timeline_reconstruction(
    case_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    body: CaseAnalysisSubmitRequest | None = None,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_INGESTION_RUN)),
) -> JobSubmitResponse:
    """Queue one deterministic timeline-reconstruction run for the whole case.

    Extracts proposed events from structured records and extraction artifacts
    (originals and time zones preserved, nothing invented), flags duplicates,
    conflicts and overlaps against the authoritative timeline, and stores the
    proposals as reviewable ``timeline_proposal`` artifacts. No LLM is used.
    """
    _ = body
    return await _submit_case_job(
        case_id=case_id,
        user=user,
        request=request,
        background_tasks=background_tasks,
        settings=settings,
        session=session,
        feature="timeline",
    )


@router.post(
    "/{case_id}/evidence-intelligence/contradiction-detection",
    response_model=JobSubmitResponse,
    status_code=202,
)
async def submit_contradiction_detection(
    case_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    body: CaseAnalysisSubmitRequest | None = None,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_INGESTION_RUN)),
) -> JobSubmitResponse:
    """Queue one anchored contradiction-detection run for the whole case.

    Compares structured claims only between records that share an exact
    identifier anchor (never unrelated claims), with transparent rules and
    rule-generated alternative explanations. The local LLM may only compare
    two anchored statements and only ever yields a flagged, reviewable
    candidate - never a confirmation. Disabled AI -> deterministic-only run.
    """
    _ = body
    return await _submit_case_job(
        case_id=case_id,
        user=user,
        request=request,
        background_tasks=background_tasks,
        settings=settings,
        session=session,
        feature="contradiction",
    )


@router.post(
    "/{case_id}/evidence-intelligence/financial-flow",
    response_model=JobSubmitResponse,
    status_code=202,
)
async def submit_financial_flow(
    case_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    body: CaseAnalysisSubmitRequest | None = None,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_INGESTION_RUN)),
) -> JobSubmitResponse:
    """Queue one bounded, deterministic financial-fact analysis for the case.

    The run extracts exact-``Decimal`` amounts and account context from the
    case's source records, computes aggregates, builds a bounded
    association structure network and evaluates the declared pattern rules.
    It uses no LLM: direction-dependent metrics are reported
    ``not_computable_no_direction`` and rules whose input the ingest does not
    carry are returned ``not_evaluable`` with the missing input — nothing is
    invented to fill a gap.
    """
    _ = body
    return await _submit_case_job(
        case_id=case_id,
        user=user,
        request=request,
        background_tasks=background_tasks,
        settings=settings,
        session=session,
        feature="financial_flow",
    )


class TimelineCommitResponse(BaseModel):
    """One committed (or already-committed) reconstructed timeline event."""

    event: TimelineEventOut
    duplicate: bool


@router.post(
    "/{case_id}/evidence-intelligence/timeline-proposals/{artifact_id}/commit",
    response_model=TimelineCommitResponse,
)
async def commit_timeline_proposal(
    case_id: uuid.UUID,
    artifact_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
) -> TimelineCommitResponse:
    """Commit one reviewer-approved proposal via the authorized timeline service.

    Authorization is re-checked immediately before the write. Idempotent: a
    retry returns the already-committed event (``duplicate=true``) instead of
    a second row. Proposals without an established timestamp are refused with
    a typed 422, and existing timeline events are never modified.
    """
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    try:
        event, created = await reconstruction_svc.commit_timeline_proposal(
            session, case_id=case_id, artifact_id=artifact_id, actor_id=user.id
        )
    except reconstruction_svc.TimelineRejected as exc:
        raise ApiHTTPException(_COMMIT_HTTP.get(exc.code, 422), exc.code, str(exc)) from exc
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="reconstruction.proposal_committed",
        resource_type="timeline_event",
        resource_id=event.id,
        case_id=case_id,
        metadata={
            "proposal_artifact_id": str(artifact_id),
            "duplicate": not created,
            "occurred_at": event.occurred_at.isoformat(),
        },
    )
    await session.commit()
    return TimelineCommitResponse(event=_event_out(event), duplicate=not created)


@router.post(
    "/{case_id}/evidence-intelligence/contradictions/{artifact_id}/resolve",
    response_model=DerivedArtifactOut,
)
async def resolve_contradiction_candidate(
    case_id: uuid.UUID,
    artifact_id: uuid.UUID,
    body: ContradictionResolveRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_FINDINGS_REVIEW)),
) -> DerivedArtifactOut:
    """Record a reviewer resolution state on one contradiction candidate.

    ``explained`` / ``requires_evidence`` / ``deferred`` are appended as new
    auditable child artifacts (lineage-linked, immutable); ``confirmed`` and
    ``false_positive`` remain the one-shot approve/reject review on the shared
    router. The candidate payload and the original evidence stay untouched.
    """
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    try:
        child = await contradiction_svc.resolve_contradiction(
            session,
            case_id=case_id,
            artifact_id=artifact_id,
            actor_id=user.id,
            state=body.state,
            note=body.note,
        )
    except contradiction_svc.ContradictionRejected as exc:
        raise ApiHTTPException(_RESOLVE_HTTP.get(exc.code, 422), exc.code, str(exc)) from exc
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action=f"contradiction.{body.state}",
        resource_type="derived_artifact",
        resource_id=artifact_id,
        case_id=case_id,
        metadata={
            "state": body.state,
            "child_artifact_id": str(child.id),
            "child_content_hash": child.content_hash,
        },
    )
    await session.commit()
    return _artifact_out(child)
