"""Routes: entity and resolution queries + review actions + merge."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_case_or_404, get_entity_query_service, require_permission
from app.core import rbac
from app.db.postgres import get_db_session
from app.models import Entity, User
from app.schemas.entity import (
    EntityAliasOut,
    EntityDetailOut,
    EntityListResponse,
    EntityOut,
    RelationshipListResponse,
    RelationshipOut,
    ReviewCandidateOut,
    ReviewListResponse,
)
from app.services import audit as audit_svc
from app.services import resolve_review as rr_svc
from app.services.entity_service import EntityQueryService
from app.services.timeline import record_event

router = APIRouter(prefix="/cases", tags=["entities"])


def _to_entity_out(entity: Entity) -> EntityOut:
    return EntityOut(
        id=entity.id,
        case_id=uuid.UUID(str(entity.case_id)),
        entity_type=entity.entity_type,
        canonical_value=entity.canonical_value,
        display_value=entity.display_value,
        confidence=entity.confidence,
        status=entity.status,
        created_at=entity.created_at,
    )


@router.get("/{case_id}/entities", response_model=EntityListResponse)
async def list_entities(
    case_id: uuid.UUID,
    request: Request,
    entity_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    service: EntityQueryService = Depends(get_entity_query_service),
) -> EntityListResponse:
    await get_case_or_404(case_id, request, session)
    entities, total = await service.list_entities(
        case_id=case_id,
        entity_type=entity_type,
        status=status,
        query=query,
        limit=limit,
        offset=offset,
    )
    return EntityListResponse(
        items=[_to_entity_out(entity) for entity in entities],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}/entities/{entity_id}", response_model=EntityDetailOut)
async def get_entity_detail(
    case_id: uuid.UUID,
    request: Request,
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    service: EntityQueryService = Depends(get_entity_query_service),
) -> EntityDetailOut:
    await get_case_or_404(case_id, request, session)
    entity, aliases = await service.get_entity_detail(entity_id)
    if entity is None or str(entity.case_id) != str(case_id):
        raise HTTPException(status_code=404, detail=f"entity {entity_id} not found")
    detail = EntityDetailOut(
        **_to_entity_out(entity).model_dump(), aliases=[], context=entity.context
    )
    detail.aliases = [
        EntityAliasOut(id=alias.id, alias_value=alias.alias_value, alias_type=alias.alias_type)
        for alias in aliases
    ]
    return detail


@router.get("/{case_id}/relationships", response_model=RelationshipListResponse)
async def list_relationships(
    case_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=500, ge=1, le=2000),
    session: AsyncSession = Depends(get_db_session),
    service: EntityQueryService = Depends(get_entity_query_service),
) -> RelationshipListResponse:
    await get_case_or_404(case_id, request, session)
    relationships = await service.list_relationships(case_id, limit=limit)
    return RelationshipListResponse(
        items=[
            RelationshipOut(
                id=rel.id,
                source_entity_id=uuid.UUID(str(rel.source_entity_id)),
                target_entity_id=uuid.UUID(str(rel.target_entity_id)),
                relationship_type=rel.relationship_type,
                confidence=rel.confidence,
                explanation=rel.explanation,
                created_at=rel.created_at,
            )
            for rel in relationships
        ],
        total=len(relationships),
    )


@router.get("/{case_id}/resolution/review", response_model=ReviewListResponse)
async def list_review_matches(
    case_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    service: EntityQueryService = Depends(get_entity_query_service),
) -> ReviewListResponse:
    await get_case_or_404(case_id, request, session)
    rows = await service.review_matches_detailed(case_id)
    items = [ReviewCandidateOut(**row) for row in rows]
    return ReviewListResponse(items=items, total=len(items))


class ReviewDecisionResponse(BaseModel):
    match_id: str
    status: str


@router.post(
    "/{case_id}/resolution/matches/{match_id}/accept",
    response_model=ReviewDecisionResponse,
)
async def accept_match(
    case_id: uuid.UUID,
    match_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_FINDINGS_REVIEW)),
) -> ReviewDecisionResponse:
    from datetime import UTC, datetime

    from app.api.dependencies import assert_case_investigation_mutable

    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    match = await rr_svc.accept_match(session=session, case_id=case_id, match_id=match_id)
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="match.accepted",
        resource_type="entity_match",
        resource_id=match.id,
        case_id=case_id,
        metadata={"score": match.score},
    )
    await record_event(
        session=session,
        case_id=case_id,
        occurred_at=datetime.now(UTC),
        kind="match_accepted",
        title=f"Resolution accepted: {match.decision} (score {match.score})",
        description=f"Match decision '{match.decision}' accepted at score {match.score}",
        actor_user_id=user.id,
        payload={"score": match.score},
    )
    await session.commit()
    return ReviewDecisionResponse(match_id=str(match.id), status=match.status)


@router.post(
    "/{case_id}/resolution/matches/{match_id}/reject",
    response_model=ReviewDecisionResponse,
)
async def reject_match(
    case_id: uuid.UUID,
    match_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_FINDINGS_REVIEW)),
) -> ReviewDecisionResponse:
    from datetime import UTC, datetime

    from app.api.dependencies import assert_case_investigation_mutable

    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    match = await rr_svc.reject_match(session=session, case_id=case_id, match_id=match_id)
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="match.rejected",
        resource_type="entity_match",
        resource_id=match.id,
        case_id=case_id,
        metadata={"score": match.score},
    )
    await record_event(
        session=session,
        case_id=case_id,
        occurred_at=datetime.now(UTC),
        kind="match_rejected",
        title=f"Resolution rejected: {match.decision} (score {match.score})",
        description=f"Match decision '{match.decision}' rejected at score {match.score}",
        actor_user_id=user.id,
        payload={"score": match.score},
    )
    await session.commit()
    return ReviewDecisionResponse(match_id=str(match.id), status=match.status)


class EntityMergeRequest(BaseModel):
    primary_entity_id: uuid.UUID
    merge_entity_id: uuid.UUID


@router.post(
    "/{case_id}/entities/merge",
    response_model=EntityOut,
)
async def merge_entities(
    case_id: uuid.UUID,
    body: EntityMergeRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission(rbac.PERM_ENTITY_MERGE)),
) -> EntityOut:
    from datetime import UTC, datetime

    from app.api.dependencies import assert_case_investigation_mutable

    case = await get_case_or_404(case_id, request, session)
    assert_case_investigation_mutable(case)
    merged_into = await rr_svc.merge_entities(
        session=session,
        case_id=case_id,
        primary_entity_id=body.primary_entity_id,
        merge_entity_id=body.merge_entity_id,
    )
    await audit_svc.record_audit(
        session,
        actor_id=user.id,
        action="entity.merged",
        resource_type="entity",
        resource_id=merged_into.id,
        case_id=case_id,
        metadata={
            "primary_id": str(body.primary_entity_id),
            "merge_id": str(body.merge_entity_id),
        },
    )
    await record_event(
        session=session,
        case_id=case_id,
        occurred_at=datetime.now(UTC),
        kind="entity_merged",
        title=f"Entities merged into '{merged_into.display_value}'",
        description=f"Kept {body.primary_entity_id} · absorbed {body.merge_entity_id}",
        entity_id=merged_into.id,
        actor_user_id=user.id,
        payload={
            "primary_id": str(body.primary_entity_id),
            "merge_id": str(body.merge_entity_id),
        },
    )
    await session.commit()
    return _to_entity_out(merged_into)
