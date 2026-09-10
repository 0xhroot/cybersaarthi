"""Aggregates all v1 API routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    analytics_router,
    audit_router,
    auth_router,
    cases_router,
    collections_router,
    devices_router,
    entities_router,
    evidence_router,
    findings_router,
    graph_router,
    health_router,
    hypotheses_router,
    import_packages_router,
    iot_router,
    reports_router,
    search_router,
    timeline_router,
    users_router,
    victims_router,
)

api_router = APIRouter()
api_router.include_router(health_router, prefix="/api/v1")

# Phase 4: authentication, case management and the audit trail.
api_router.include_router(auth_router, prefix="/api/v1")
api_router.include_router(cases_router, prefix="/api/v1")
api_router.include_router(audit_router, prefix="/api/v1")

# Phase 5: administrative user management (account lifecycle).
api_router.include_router(users_router, prefix="/api/v1")

# Phase 2: evidence ingestion, entities, resolution review and graph queries.
api_router.include_router(evidence_router, prefix="/api/v1")
api_router.include_router(entities_router, prefix="/api/v1")
api_router.include_router(graph_router, prefix="/api/v1")

# Phase 3: investigation intelligence (analytics + explainable findings).
api_router.include_router(analytics_router, prefix="/api/v1")
api_router.include_router(findings_router, prefix="/api/v1")

# Victim management.
api_router.include_router(victims_router, prefix="/api/v1")

# IoT device and telemetry management.
api_router.include_router(iot_router, prefix="/api/v1")

# Investigation platform: collections, devices, timeline, hypotheses, reports, search, import.
api_router.include_router(collections_router, prefix="/api/v1")
api_router.include_router(devices_router, prefix="/api/v1")
api_router.include_router(timeline_router, prefix="/api/v1")
api_router.include_router(hypotheses_router, prefix="/api/v1")
api_router.include_router(reports_router, prefix="/api/v1")
api_router.include_router(search_router, prefix="/api/v1")
api_router.include_router(import_packages_router, prefix="/api/v1")
