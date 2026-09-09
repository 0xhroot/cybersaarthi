"""Routes: victim management for cyber fraud cases."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    assert_case_investigation_mutable,
    get_case_or_404,
    require_permission,
)
from app.core import rbac
from app.db.postgres import get_db_session
from app.models import User
from app.models.victim import Victim
from app.repositories.victim_repository import VictimRepository
from app.schemas.victim import (
    VictimCreateRequest,
    VictimListResponse,
    VictimOut,
    VictimUpdateRequest,
)
from app.services.audit import record_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases", tags=["victims"])


def _to_victim_out(victim: Victim) -> VictimOut:
    return VictimOut(
        id=victim.id,
        case_id=uuid.UUID(str(victim.case_id)),
        name=victim.name,
        age=victim.age,
        date_of_birth=victim.date_of_birth,
        gender=victim.gender,
        classification=victim.classification,
        phone=victim.phone,
        email=victim.email,
        address=victim.address,
        incident_date=victim.incident_date,
        incident_type=victim.incident_type,
        fraud_category=victim.fraud_category,
        description=victim.description,
        reported_amount=victim.reported_amount,
        currency=victim.currency,
        amount_lost=victim.amount_lost,
        recovery_amount=victim.recovery_amount,
        digital_accounts=victim.digital_accounts,
        devices=victim.devices,
        wallet_addresses=victim.wallet_addresses,
        status=victim.status,
        statement=victim.statement,
        investigator_notes=victim.investigator_notes,
        recovery_status=victim.recovery_status,
        created_by=victim.created_by,
        created_at=victim.created_at,
        updated_at=victim.updated_at,
    )


@router.get("/{case_id}/victims", response_model=VictimListResponse)
async def list_victims(
    case_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, max_length=32),
    search: str | None = Query(None, max_length=200),
    session: AsyncSession = Depends(get_db_session),
) -> VictimListResponse:
    """List victims associated with a case."""
    await get_case_or_404(case_id, request, session)
    repo = VictimRepository(session)
    items, total = await repo.list_by_case(
        case_id, status=status, query=search, limit=limit, offset=offset
    )
    return VictimListResponse(
        items=[_to_victim_out(v) for v in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{case_id}/victims", response_model=VictimOut, status_code=201)
async def create_victim(
    case_id: uuid.UUID,
    payload: VictimCreateRequest,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> VictimOut:
    """Add a victim to an investigation case."""
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    repo = VictimRepository(session)
    victim = await repo.create(
        case_id=case_id,
        created_by=user.id,
        **payload.model_dump(exclude_unset=True),
    )
    await record_audit(
        session,
        actor_id=user.id,
        action="victim.created",
        resource_type="victim",
        resource_id=victim.id,
        case_id=case_id,
        metadata={"name": victim.name, "status": victim.status},
    )
    await session.commit()
    return _to_victim_out(victim)


@router.get("/{case_id}/victims/{victim_id}", response_model=VictimOut)
async def get_victim(
    case_id: uuid.UUID,
    victim_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> VictimOut:
    """Get a single victim by ID within a case."""
    await get_case_or_404(case_id, request, session)
    repo = VictimRepository(session)
    victim = await repo.get(victim_id)
    if victim is None or str(victim.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"victim {victim_id} not found")
    return _to_victim_out(victim)


@router.patch("/{case_id}/victims/{victim_id}", response_model=VictimOut)
async def update_victim(
    case_id: uuid.UUID,
    victim_id: uuid.UUID,
    payload: VictimUpdateRequest,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> VictimOut:
    """Update victim information."""
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    repo = VictimRepository(session)
    victim = await repo.get(victim_id)
    if victim is None or str(victim.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"victim {victim_id} not found")
    updates = payload.model_dump(exclude_unset=True)
    victim = await repo.update(victim, **updates)
    await record_audit(
        session,
        actor_id=user.id,
        action="victim.updated",
        resource_type="victim",
        resource_id=victim.id,
        case_id=case_id,
        metadata={"fields": list(updates.keys())},
    )
    await session.commit()
    return _to_victim_out(victim)


@router.delete("/{case_id}/victims/{victim_id}", status_code=204)
async def delete_victim(
    case_id: uuid.UUID,
    victim_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission(rbac.PERM_CASE_UPDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Remove a victim from a case."""
    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    repo = VictimRepository(session)
    victim = await repo.get(victim_id)
    if victim is None or str(victim.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"victim {victim_id} not found")
    await record_audit(
        session,
        actor_id=user.id,
        action="victim.deleted",
        resource_type="victim",
        resource_id=victim.id,
        case_id=case_id,
        metadata={"name": victim.name},
    )
    await repo.delete(victim)
    await session.commit()
