"""Aggregates all v1 API routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    analytics_router,
    entities_router,
    evidence_router,
    findings_router,
    graph_router,
    health_router,
)

api_router = APIRouter()
api_router.include_router(health_router, prefix="/api/v1")

# Phase 2: evidence ingestion, entities, resolution review and graph queries.
api_router.include_router(evidence_router, prefix="/api/v1")
api_router.include_router(entities_router, prefix="/api/v1")
api_router.include_router(graph_router, prefix="/api/v1")

# Phase 3: investigation intelligence (analytics + explainable findings).
api_router.include_router(analytics_router, prefix="/api/v1")
api_router.include_router(findings_router, prefix="/api/v1")
