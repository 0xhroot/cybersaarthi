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
from app.api.routes.collections import router as collections_router
from app.api.routes.devices import router as devices_router
from app.api.routes.entities import router as entities_router
from app.api.routes.evidence import router as evidence_router
from app.api.routes.findings import router as findings_router
from app.api.routes.graph import router as graph_router
from app.api.routes.health import router as health_router
from app.api.routes.hypotheses import router as hypotheses_router
from app.api.routes.import_packages import router as import_packages_router
from app.api.routes.iot import router as iot_router
from app.api.routes.reports import router as reports_router
from app.api.routes.search import router as search_router
from app.api.routes.timeline import router as timeline_router
from app.api.routes.users import router as users_router
from app.api.routes.victims import router as victims_router

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
    "collections_router",
    "devices_router",
    "entities_router",
    "evidence_router",
    "findings_router",
    "graph_router",
    "health_router",
    "hypotheses_router",
    "import_packages_router",
    "iot_router",
    "reports_router",
    "search_router",
    "timeline_router",
    "users_router",
    "victims_router",
]
