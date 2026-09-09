"""Routes: entity and resolution queries."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_case_or_404, get_entity_query_service
from app.db.postgres import get_db_session
from app.models import Entity
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
from app.services.entity_service import EntityQueryService

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
