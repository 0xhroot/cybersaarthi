"""Routes: hypotheses (case-scoped)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_case_or_404, require_permission
from app.core import rbac
from app.db.postgres import get_db_session
from app.models import Hypothesis, User
from app.services import audit as audit_svc
from app.services import hypotheses as hyp_svc
from app.services.timeline import record_event

router = APIRouter(prefix="/cases", tags=["hypotheses"])


class HypothesisCreateRequest(BaseModel):
    kind: str = "hypothesis"
    title: str
    statement: str
    confidence: float | None = None
    notes: str | None = None


class HypothesisUpdateStatusRequest(BaseModel):
    status: str


class HypothesisLinkEvidenceRequest(BaseModel):
    evidence_id: uuid.UUID
    support: bool = True


class HypothesisOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    kind: str
    status: str
    title: str
    statement: str
    confidence: float | None
    supporting_evidence: list[str] | None
    contradicting_evidence: list[str] | None
    related_entities: list[str] | None
    related_relationships: list[str] | None
    evidence_weight: int
    notes: str | None
    submitted_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class HypothesisListResponse(BaseModel):
    items: list[HypothesisOut]
    total: int
    limit: int
    offset: int


def _hypothesis_out(h: Hypothesis) -> HypothesisOut:
    return HypothesisOut(
        id=h.id,
        case_id=uuid.UUID(str(h.case_id)),
        kind=h.kind,
        status=h.status,
        title=h.title,
        statement=h.statement,
        confidence=h.confidence,
        supporting_evidence=h.supporting_evidence,
        contradicting_evidence=h.contradicting_evidence,
        related_entities=h.related_entities,
        related_relationships=h.related_relationships,
        evidence_weight=h.evidence_weight,
        notes=h.notes,
        submitted_by=uuid.UUID(str(h.submitted_by)) if h.submitted_by else None,
        created_at=h.created_at,
        updated_at=h.updated_at,
    )


@router.post(
    "/{case_id}/hypotheses",
    response_model=HypothesisOut,
    status_code=201,
)
async def create_hypothesis(
    case_id: uuid.UUID,
    body: HypothesisCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_FINDINGS_REVIEW)),
) -> HypothesisOut:
    from app.api.dependencies import assert_case_investigation_mutable

    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    h = await hyp_svc.create_hypothesis(
        session=session,
        case_id=case_id,
        kind=body.kind,
        title=body.title,
        statement=body.statement,
        confidence=body.confidence,
        notes=body.notes,
        submitted_by=user.id,
    )
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="hypothesis.created",
        resource_type="hypothesis",
        resource_id=h.id,
        case_id=case_id,
        metadata={"title": h.title, "kind": h.kind},
    )
    await record_event(
        session=session,
        case_id=case_id,
        occurred_at=h.created_at,
        kind="hypothesis_created",
        title=f"Hypothesis: {h.title}",
        actor_user_id=user.id,
    )
    await session.commit()
    return _hypothesis_out(h)


@router.get("/{case_id}/hypotheses", response_model=HypothesisListResponse)
async def list_hypotheses(
    case_id: uuid.UUID,
    request: Request,
    kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> HypothesisListResponse:
    await get_case_or_404(case_id, request, session)
    rows, total = await hyp_svc.list_hypotheses(
        session=session, case_id=case_id, kind=kind, status=status, limit=limit, offset=offset
    )
    return HypothesisListResponse(
        items=[_hypothesis_out(h) for h in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}/hypotheses/{hypothesis_id}", response_model=HypothesisOut)
async def get_hypothesis(
    case_id: uuid.UUID,
    hypothesis_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CASE_READ)),
) -> HypothesisOut:
    from fastapi import HTTPException

    await get_case_or_404(case_id, request, session)
    h = await hyp_svc.get_hypothesis(session, hypothesis_id)
    if h is None or str(h.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"hypothesis {hypothesis_id} not found")
    return _hypothesis_out(h)


@router.patch("/{case_id}/hypotheses/{hypothesis_id}/status", response_model=HypothesisOut)
async def transition_hypothesis_status(
    case_id: uuid.UUID,
    hypothesis_id: uuid.UUID,
    body: HypothesisUpdateStatusRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_FINDINGS_REVIEW)),
) -> HypothesisOut:
    from app.api.dependencies import assert_case_investigation_mutable

    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    h = await hyp_svc.get_hypothesis(session, hypothesis_id)
    if h is None or str(h.case_id) != str(case_id):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"hypothesis {hypothesis_id} not found")
    old_status = h.status
    h = await hyp_svc.transition_hypothesis_status(
        session=session, hypothesis=h, new_status=body.status
    )
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="hypothesis.status_changed",
        resource_type="hypothesis",
        resource_id=h.id,
        case_id=case_id,
        metadata={"old": old_status, "new": body.status},
    )
    await record_event(
        session=session,
        case_id=case_id,
        occurred_at=h.updated_at,
        kind="hypothesis_status_changed",
        title=f"Hypothesis '{h.title}' status: {old_status} -> {body.status}",
        actor_user_id=user.id,
    )
    await session.commit()
    return _hypothesis_out(h)


@router.post(
    "/{case_id}/hypotheses/{hypothesis_id}/evidence",
    response_model=HypothesisOut,
)
async def link_evidence(
    case_id: uuid.UUID,
    hypothesis_id: uuid.UUID,
    body: HypothesisLinkEvidenceRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_FINDINGS_REVIEW)),
) -> HypothesisOut:
    from app.api.dependencies import assert_case_investigation_mutable

    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    h = await hyp_svc.get_hypothesis(session, hypothesis_id)
    if h is None or str(h.case_id) != str(case_id):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"hypothesis {hypothesis_id} not found")

    from app.models import EvidenceFile

    evidence = await session.get(EvidenceFile, body.evidence_id)
    if evidence is None or str(evidence.case_id) != str(case_id) or evidence.is_deleted:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"evidence {body.evidence_id} not found")

    h = await hyp_svc.link_evidence_to_hypothesis(
        session=session, hypothesis=h, evidence_id=body.evidence_id, support=body.support
    )
    await session.commit()
    return _hypothesis_out(h)


@router.delete(
    "/{case_id}/hypotheses/{hypothesis_id}",
    status_code=204,
)
async def delete_hypothesis(
    case_id: uuid.UUID,
    hypothesis_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_FINDINGS_DISMISS)),
) -> None:
    from fastapi import HTTPException

    from app.api.dependencies import assert_case_investigation_mutable

    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    h = await hyp_svc.get_hypothesis(session, hypothesis_id)
    if h is None or str(h.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"hypothesis {hypothesis_id} not found")
    await hyp_svc.delete_hypothesis(session=session, hypothesis=h)
    await session.commit()
