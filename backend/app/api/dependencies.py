"""FastAPI dependencies that assemble Phase 2 repositories and services."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.findings import AnalyticsService
from app.core.config import get_settings
from app.db.postgres import get_db_session
from app.models import Case
from app.repositories.analytics_repository import AnalyticsDataRepository
from app.repositories.entity_repository import EntityRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.repositories.relationship_repository import RelationshipRepository
from app.services.entity_service import EntityQueryService
from app.services.graph_sync import GraphSyncService
from app.services.ingestion import IngestionService


async def get_case_or_404(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> Case:
    result = await session.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")
    return case


def _repositories(
    session: AsyncSession,
) -> tuple[EvidenceRepository, EntityRepository, RelationshipRepository]:
    return (
        EvidenceRepository(session),
        EntityRepository(session),
        RelationshipRepository(session),
    )


async def get_evidence_repository(
    session: AsyncSession = Depends(get_db_session),
) -> EvidenceRepository:
    return EvidenceRepository(session)


async def get_entity_repository(
    session: AsyncSession = Depends(get_db_session),
) -> EntityRepository:
    return EntityRepository(session)


async def get_relationship_repository(
    session: AsyncSession = Depends(get_db_session),
) -> RelationshipRepository:
    return RelationshipRepository(session)


async def get_ingestion_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> IngestionService:
    evidence_repo, entity_repo, relationship_repo = _repositories(session)
    settings = get_settings()
    return IngestionService(
        session=session,
        evidence_repository=evidence_repo,
        entity_repository=entity_repo,
        relationship_repository=relationship_repo,
        storage=request.app.state.storage,
        graph_sync=GraphSyncService(request.app.state.graph_store, settings),
        settings=settings,
    )


async def get_analytics_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsService:
    return AnalyticsService(
        data_repo=AnalyticsDataRepository(session),
        graph_store=request.app.state.graph_store,
        settings=get_settings(),
    )


async def get_analytics_data_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsDataRepository:
    return AnalyticsDataRepository(session)


async def get_entity_query_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> EntityQueryService:
    evidence_repo, entity_repo, relationship_repo = _repositories(session)
    return EntityQueryService(
        session=session,
        entity_repository=entity_repo,
        evidence_repository=evidence_repo,
        relationship_repository=relationship_repo,
    )
