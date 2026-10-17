"""Routes: cross-case pattern discovery (phase 4, feature B).

Two surfaces, both authorization-first:

- ``POST /cross-case/discover`` queues one bounded discovery run over an
  explicit scope. Every case in the scope must be readable *now* or the whole
  request is refused with a 404 that never reveals which id failed (so scope
  probing cannot test case existence). The runner re-derives the same scope
  from fresh rows before touching evidence and fails the job closed
  (``CROSS_CASE_SCOPE_REVOKED``) if any access was revoked mid-run.
- ``GET /cross-case/candidates`` lists an anchor case's candidates, re-fetching
  per-case visibility on every response and omitting (never redacting) any
  candidate that touches a case the caller may not read.

Candidates are ``cross_case_link`` artifacts; they are never returned by the
generic artifact listing, so this scope-checked endpoint is the only read path.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    assert_case_investigation_mutable,
    get_case_or_404,
    require_permission,
)
from app.api.errors import ApiHTTPException
from app.api.routes.evidence_intelligence import _artifact_out, _job_out
from app.core import rbac
from app.core.codes import (
    CODE_CROSS_CASE_ACTIVE,
    CODE_CROSS_CASE_SCOPE_DENIED,
    CODE_INVALID_PAYLOAD,
)
from app.core.config import Settings, get_settings
from app.db.postgres import get_db_session
from app.models import User
from app.schemas.cross_case import CrossCaseCandidateListResponse, CrossCaseDiscoverRequest
from app.schemas.evidence_integrity import JobSubmitResponse
from app.services import analysis_jobs as jobs_svc
from app.services import audit as audit_svc
from app.services import cross_case as cross_case_svc

router = APIRouter(prefix="/cross-case", tags=["cross-case"])

_SUBMIT_HTTP: dict[str, int] = {
    CODE_CROSS_CASE_ACTIVE: 409,
}


def _scope_denied() -> ApiHTTPException:
    """A 404 that confirms nothing: neither which id failed nor whether it
    exists. Uniform for missing, foreign-tenant and merely-unreadable cases."""
    return ApiHTTPException(
        404,
        CODE_CROSS_CASE_SCOPE_DENIED,
        "one or more cases in the requested scope are not accessible to this account",
    )


@router.post("/discover", response_model=JobSubmitResponse, status_code=202)
async def discover_cross_case(
    body: CrossCaseDiscoverRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CROSSCASE_READ)),
) -> JobSubmitResponse:
    """Queue one bounded cross-case discovery run (202 accepted).

    Requires the ``crosscase.read`` capability *and* read access to every case
    in ``case_ids``. The scope is explicit and bounded (never "every case I can
    see"); a scope containing an inaccessible case is refused with a no-leak
    404. Submission is idempotent per (anchor, scope): a duplicate collapses
    onto the existing job, a different scope is a different job, and one active
    job per anchor+feature is enforced with a typed 409.
    """
    ids = sorted({str(value) for value in body.case_ids})
    if len(ids) > settings.CROSSCASE_MAX_CASES:
        raise ApiHTTPException(
            422,
            CODE_INVALID_PAYLOAD,
            f"scope exceeds the {settings.CROSSCASE_MAX_CASES}-case bound",
        )
    anchor = str(body.anchor_case_id)
    if anchor not in ids:
        raise ApiHTTPException(
            422,
            CODE_INVALID_PAYLOAD,
            "anchor_case_id must be one of the cases in case_ids",
        )

    # Fresh, whole-scope visibility check (no-leak 404 on any failure).
    try:
        verified_ids, scope_hash = await cross_case_svc.verify_scope(
            session, user=user, case_ids=ids
        )
    except cross_case_svc.CrossCaseScopeDenied as exc:
        raise _scope_denied() from exc

    # Anchor must be a mutable investigation the caller can already read (the
    # scope check above already proved anchor visibility).
    anchor_case = await get_case_or_404(body.anchor_case_id, request, session)
    assert_case_investigation_mutable(anchor_case)

    try:
        job, created = await cross_case_svc.submit_cross_case_job(
            session,
            anchor_case_id=body.anchor_case_id,
            case_ids=verified_ids,
            actor_id=user.id,
            timeout_seconds=settings.CROSSCASE_TIMEOUT_SECONDS,
        )
    except jobs_svc.FeatureJobActive as exc:
        raise ApiHTTPException(_SUBMIT_HTTP.get(exc.code, 409), exc.code, str(exc)) from exc

    if created:
        background_tasks.add_task(
            cross_case_svc.run_cross_case_job,
            request.app,
            uuid.UUID(str(job.id)),
        )
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="cross_case.search_submitted",
        resource_type="analysis_job",
        resource_id=job.id,
        case_id=body.anchor_case_id,
        metadata={
            "anchor_case_id": str(body.anchor_case_id),
            "case_ids": verified_ids,
            "scope_count": len(verified_ids),
            "scope_hash": scope_hash,
            "duplicate": not created,
        },
    )
    await session.commit()
    return JobSubmitResponse(job=_job_out(job), duplicate=not created)


@router.get("/candidates", response_model=CrossCaseCandidateListResponse)
async def list_cross_case_candidates(
    anchor_case_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_CROSSCASE_READ)),
) -> CrossCaseCandidateListResponse:
    """Authorized cross-case candidates for one anchor case (B7 recheck).

    Per-case visibility is re-derived from fresh rows on this call (never from
    submission-time or cached state). A candidate is returned only when the
    caller may read *every* side right now; candidates touching an inaccessible
    case are dropped whole, so the response can never leak a foreign case's
    identifiers, ids, names or counts.
    """
    await get_case_or_404(anchor_case_id, request, session)
    rows, total = await cross_case_svc.visible_candidates(
        session,
        user=user,
        anchor_case_id=anchor_case_id,
        limit=limit,
        offset=offset,
    )
    return CrossCaseCandidateListResponse(
        items=[_artifact_out(row) for row in rows],
        total=total,
        anchor_case_id=anchor_case_id,
        crosscase_rules_version=cross_case_svc.CROSSCASE_RULES_VERSION,
        graph_freshness_note=cross_case_svc.GRAPH_FRESHNESS_NOTE,
    )
