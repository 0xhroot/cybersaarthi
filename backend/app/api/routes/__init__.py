from app.api.dependencies import (
    get_analytics_data_repository,
    get_analytics_service,
    get_case_or_404,
    get_entity_query_service,
    get_entity_repository,
    get_evidence_repository,
    get_ingestion_service,
    get_relationship_repository,
)
from app.api.routes.analytics import router as analytics_router
from app.api.routes.audit import router as audit_router
from app.api.routes.auth import router as auth_router
from app.api.routes.cases import router as cases_router
from app.api.routes.entities import router as entities_router
from app.api.routes.evidence import router as evidence_router
from app.api.routes.findings import router as findings_router
from app.api.routes.graph import router as graph_router
from app.api.routes.health import router as health_router

__all__ = [
    "get_analytics_data_repository",
    "get_analytics_service",
    "get_case_or_404",
    "get_entity_query_service",
    "get_entity_repository",
    "get_evidence_repository",
    "get_ingestion_service",
    "get_relationship_repository",
    "analytics_router",
    "audit_router",
    "auth_router",
    "cases_router",
    "entities_router",
    "evidence_router",
    "findings_router",
    "graph_router",
    "health_router",
]
