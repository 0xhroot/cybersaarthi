"""Routes: integrity verification & chain-of-custody (feature 9, case-scoped).

Deterministic surface: verify recomputes sha256 over the original object
bytes; the custody audit runs the pure rule set as an ``AnalysisJob``; the
chronology endpoint returns recorded events exactly as stored. The only AI
endpoint here narrates an already-recorded finding - it cannot certify
custody, alter results or create history. Recorded custody events are
append-only: no route in this file edits or deletes them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import CUSTODY_EXPLAIN_PROMPT_VERSION
from app.ai.service import AIService
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
    CODE_CUSTODY_AUDIT_ACTIVE,
    CODE_CUSTODY_FIELD_REQUIRED,
    CODE_EVIDENCE_NOT_FOUND,
    CODE_EVIDENCE_UNAVAILABLE,
    CODE_INVALID_PAYLOAD,
    CODE_JOB_NOT_FOUND,
    CODE_JOB_TERMINAL,
)
from app.core.config import Settings, get_settings
from app.db.postgres import get_db_session
from app.models import AnalysisJob, DerivedArtifact, EvidenceCustodyEvent, EvidenceFile, User
from app.schemas.evidence_integrity import (
    CustodyAuditRequest,
    CustodyChronologyResponse,
    CustodyEventCreate,
    CustodyEventOut,
    ExplainResponse,
    IntegrityVerificationRequest,
    IntegrityVerificationResponse,
    JobSubmitResponse,
)
from app.schemas.evidence_intelligence import AnalysisJobOut, DerivedArtifactOut
from app.services import analysis_jobs as jobs_svc
from app.services import artifacts as artifacts_svc
from app.services import audit as audit_svc
from app.services import custody as custody_svc
from app.services.integrity import IntegrityRejected, verify_evidence_integrity

router = APIRouter(prefix="/cases", tags=["evidence-integrity"])

CUSTODY_FEATURE = "custody"

_REJECTION_HTTP: dict[str, int] = {
    CODE_EVIDENCE_NOT_FOUND: 404,
    CODE_EVIDENCE_UNAVAILABLE: 409,
    CODE_CUSTODY_AUDIT_ACTIVE: 409,
    CODE_CUSTODY_FIELD_REQUIRED: 422,
    CODE_JOB_NOT_FOUND: 404,
    CODE_JOB_TERMINAL: 409,
    CODE_INVALID_PAYLOAD: 422,
    CODE_ARTIFACT_NOT_FOUND: 404,
    CODE_ARTIFACT_KIND_UNSUPPORTED: 422,
}


def _rejection(code: str, message: str) -> ApiHTTPException:
    return ApiHTTPException(_REJECTION_HTTP.get(code, 422), code, message)


def _job_out(job: AnalysisJob) -> AnalysisJobOut:
    return AnalysisJobOut.model_validate(job, from_attributes=True)


def _event_out(event: EvidenceCustodyEvent) -> CustodyEventOut:
    return CustodyEventOut.model_validate(event, from_attributes=True)


def _artifact_out(artifact: DerivedArtifact) -> DerivedArtifactOut:
    return DerivedArtifactOut.model_validate(artifact, from_attributes=True)


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


# -- deterministic verification ------------------------------------------------


@router.post(
    "/{case_id}/evidence-integrity/verify",
    response_model=IntegrityVerificationResponse,
)
async def verify_evidence(
    case_id: uuid.UUID,
    body: IntegrityVerificationRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_INGESTION_RUN)),
) -> IntegrityVerificationResponse:
    """Recompute sha256 over the original bytes and report the exact outcome.

    ``match``/``mismatch`` and every inconclusive state (missing object bytes,
    missing recorded hash) are 200 responses with typed statuses - the
    endpoint never guesses and never modifies the evidence row or object.
    """
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    try:
        result = await verify_evidence_integrity(
            session,
            storage=request.app.state.storage,
            case_id=case_id,
            evidence_id=body.evidence_file_id,
            actor_id=user.id,
        )
    except IntegrityRejected as exc:
        raise _rejection(exc.code, str(exc)) from exc
    return IntegrityVerificationResponse(**result)


# -- custody audit (AnalysisJob) ------------------------------------------------


async def _active_custody_job(session: AsyncSession, case_id: uuid.UUID) -> AnalysisJob | None:
    result = await session.execute(
        select(AnalysisJob)
        .where(
            AnalysisJob.case_id == str(case_id),
            AnalysisJob.feature == CUSTODY_FEATURE,
            AnalysisJob.status.in_(("pending", "running")),
        )
        .order_by(AnalysisJob.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


def _clear_stale_custody_job(job: AnalysisJob, settings: Settings) -> bool:
    """Terminal-ize an orphaned pending/running job (restart, no queue)."""
    try:
        if job.status == "running":
            if not jobs_svc.is_timed_out(job):
                return False  # genuinely running (or never started): stay active
            job.error = f"superseded: exceeded {job.timeout_seconds}s timeout budget"
            jobs_svc.transition(job, "failed")
        elif job.status == "pending":
            if (datetime.now(UTC) - job.created_at).total_seconds() <= 2 * max(
                1, job.timeout_seconds or settings.CUSTODY_TIMEOUT_SECONDS
            ):
                return False  # freshly queued, not stale
            jobs_svc.transition(job, "canceled")
        else:
            return False
        return True
    except jobs_svc.InvalidJobTransition:  # pragma: no cover - raced to terminal
        return False


@router.post(
    "/{case_id}/evidence-integrity/custody-audit",
    response_model=JobSubmitResponse,
    status_code=202,
)
async def submit_custody_audit(
    case_id: uuid.UUID,
    body: CustodyAuditRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_INGESTION_RUN)),
) -> JobSubmitResponse:
    """Queue the deterministic custody rule set over one item or the whole case.

    One active audit per case (typed 409 while one runs; stale jobs left by a
    restart are cleared honestly - they can never report success). Findings
    land as reviewable ``custody_finding`` artifacts; identical facts dedupe
    onto the existing artifact instead of duplicating it.
    """
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)

    active = await _active_custody_job(session, case_id)
    if active is not None and not _clear_stale_custody_job(active, settings):
        raise ApiHTTPException(
            409, CODE_CUSTODY_AUDIT_ACTIVE, "a custody audit is already running for this case"
        )
    if active is not None:
        await session.flush()

    if body.evidence_file_id is not None:
        evidence = await _scoped_evidence(session, case_id, body.evidence_file_id)
        if evidence is None:
            raise _rejection(CODE_EVIDENCE_NOT_FOUND, "evidence not found in this case")
        if evidence.deleted_at is not None:
            raise _rejection(
                CODE_EVIDENCE_UNAVAILABLE, "evidence is deleted; restore it before auditing"
            )

    attempts = int(
        (
            await session.execute(
                select(func.count())
                .select_from(AnalysisJob)
                .where(
                    AnalysisJob.case_id == str(case_id),
                    AnalysisJob.feature == CUSTODY_FEATURE,
                )
            )
        ).scalar_one()
    )
    idempotency_key = f"custody:{case_id}:a{attempts + 1}"
    try:
        job, created = await jobs_svc.create_job(
            session,
            case_id=case_id,
            feature=CUSTODY_FEATURE,
            idempotency_key=idempotency_key,
            actor_id=user.id,
            evidence_file_id=body.evidence_file_id,
            timeout_seconds=settings.CUSTODY_TIMEOUT_SECONDS,
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
        job, created = row, False

    if created:
        background_tasks.add_task(
            custody_svc.run_custody_audit_job, request.app, uuid.UUID(str(job.id))
        )
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="custody.audit_submitted",
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=case_id,
        metadata={
            "evidence_file_id": str(body.evidence_file_id) if body.evidence_file_id else None,
            "duplicate": not created,
        },
    )
    await session.commit()
    return JobSubmitResponse(job=_job_out(job), duplicate=not created)


# -- chronology (recorded history, read-only) ----------------------------------


@router.get(
    "/{case_id}/evidence/{evidence_id}/custody",
    response_model=CustodyChronologyResponse,
)
async def get_custody_chronology(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_EVIDENCE_READ)),
) -> CustodyChronologyResponse:
    """Evidence summary + its custody events in occurred-at order.

    Read-only: deleted evidence reports ``deleted_at`` explicitly instead of
    disappearing or rendering as verified; no hash is computed on read (the
    frontend shows the latest recorded verification artifact for that).
    """
    await get_case_or_404(case_id, request, session)
    evidence = await _scoped_evidence(session, case_id, evidence_id)
    if evidence is None:
        raise _rejection(CODE_EVIDENCE_NOT_FOUND, "evidence not found in this case")
    rows = await session.execute(
        select(EvidenceCustodyEvent)
        .where(
            EvidenceCustodyEvent.evidence_file_id == str(evidence_id),
            EvidenceCustodyEvent.case_id == str(case_id),
        )
        .order_by(EvidenceCustodyEvent.occurred_at, EvidenceCustodyEvent.created_at)
    )
    events = [_event_out(row) for row in rows.scalars()]
    return CustodyChronologyResponse(
        evidence_id=evidence.id,
        original_filename=evidence.original_filename,
        sha256=evidence.sha256,
        algorithm="sha256",
        format=evidence.format,
        file_size=evidence.file_size,
        created_at=evidence.created_at,
        deleted_at=evidence.deleted_at,
        events=events,
        event_count=len(events),
    )


@router.post(
    "/{case_id}/evidence/{evidence_id}/custody-events",
    response_model=CustodyEventOut,
    status_code=status.HTTP_201_CREATED,
)
async def record_custody_event(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    body: CustodyEventCreate,
    request: Request,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_EVIDENCE_UPLOAD)),
) -> CustodyEventOut:
    """Append one custody event (authorized, policy-validated, audit-logged).

    Corrections are new events; this endpoint cannot rewrite history. Policy
    v1.0.0 party fields, timezone-aware ``occurred_at``, future-time and
    sha256 format are all checked deterministically with typed codes.
    """
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    try:
        event = await custody_svc.record_custody_event(
            session,
            case_id=case_id,
            evidence_id=evidence_id,
            actor_id=user.id,
            event_type=body.event_type,
            occurred_at=body.occurred_at,
            collector=body.collector,
            transferor=body.transferor,
            recipient=body.recipient,
            location=body.location,
            method=body.method,
            notes=body.notes,
            recorded_sha256=body.recorded_sha256,
            max_future_seconds=settings.CUSTODY_FUTURE_SKEW_SECONDS,
        )
    except custody_svc.CustodyRejected as exc:
        raise _rejection(exc.code, str(exc)) from exc
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="custody.event_recorded",
        resource_type="evidence_file",
        resource_id=str(evidence_id),
        case_id=case_id,
        metadata={"event_id": str(event.id), "event_type": event.event_type},
    )
    await session.commit()
    return _event_out(event)


# -- AI explanation of a recorded finding (facts-only) --------------------------


def _ai_service(request: Request) -> AIService:
    return request.app.state.ai_service


@router.post(
    "/{case_id}/evidence-intelligence/artifacts/{artifact_id}/explain",
    response_model=ExplainResponse,
)
async def explain_custody_finding(
    case_id: uuid.UUID,
    artifact_id: uuid.UUID,
    request: Request,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_EVIDENCE_READ)),
    ai: AIService = Depends(_ai_service),
) -> ExplainResponse:
    """Explain one recorded custody/integrity finding from its facts only.

    The deterministic rules already decided pass/fail; this endpoint records
    an AI narration as a separate ``recorded`` artifact (parent = finding).
    It refuses non-finding artifacts, forwards nothing but the finding payload
    to the model, and the prompt forbids inventing custody entries, certifying
    the chain or claiming any verification was performed by the model.
    """
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    if not settings.AI_FEATURE_INTEGRITY_EXPLAIN:
        raise ApiHTTPException(403, CODE_AI_DISABLED, "AI integrity explanations are disabled")
    artifact = await artifacts_svc.get_artifact(session, case_id, artifact_id)
    if artifact is None:
        raise _rejection(CODE_ARTIFACT_NOT_FOUND, f"artifact {artifact_id} not found")
    payload = artifact.payload or {}
    if artifact.kind != "custody_finding" or payload.get("type") != "custody_finding":
        raise _rejection(
            CODE_ARTIFACT_KIND_UNSUPPORTED,
            "explanations apply only to recorded custody/integrity findings",
        )

    rule = str(payload.get("rule") or "")
    facts = {
        "rule": rule,
        "severity": payload.get("severity"),
        "observed": payload.get("observed"),
        "missing": payload.get("missing"),
        "message": payload.get("message"),
        "event_ids": payload.get("event_ids"),
        "rule_set_version": payload.get("rule_set_version"),
        "policy_version": payload.get("policy_version"),
        "evidence_id": payload.get("evidence_id"),
    }
    text = await ai.explain_integrity_finding(finding=facts)

    explanation, _ = await artifacts_svc.record_artifact(
        session,
        case_id=case_id,
        kind="custody_finding",
        origin="llm",
        payload={
            "type": "ai_explanation",
            "text": text,
            "for_artifact_id": str(artifact.id),
            "rule": rule,
        },
        evidence_file_id=(
            uuid.UUID(str(artifact.evidence_file_id)) if artifact.evidence_file_id else None
        ),
        # Explanations are unverified AI interpretation: amber by design, never
        # a fabricated green "validated" badge, and never queued for approval.
        validation_status="flagged",
        validation_errors=[
            {
                "field": "explanation",
                "code": "ai_unverified",
                "message": (
                    "AI interpretation of recorded facts; deterministic rules and "
                    "human review decide outcomes"
                ),
            }
        ],
        prompt_version=CUSTODY_EXPLAIN_PROMPT_VERSION,
        model_profile="explain",
        parent_artifact_id=artifact.id,
        created_by=user.id,
        status="recorded",
    )
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="custody.explanation_generated",
        resource_type="derived_artifact",
        resource_id=str(explanation.id),
        case_id=case_id,
        metadata={"for_artifact_id": str(artifact.id), "rule": rule},
    )
    await session.commit()
    return ExplainResponse(
        explanation_artifact=_artifact_out(explanation), text=text, rule=rule
    )
