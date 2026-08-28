from app.api.dependencies import (
    get_case_or_404,
    get_entity_query_service,
    get_entity_repository,
    get_evidence_repository,
    get_ingestion_service,
    get_relationship_repository,
)
from app.api.routes.entities import router as entities_router
from app.api.routes.evidence import router as evidence_router
from app.api.routes.graph import router as graph_router
from app.api.routes.health import router as health_router

__all__ = [
    "get_case_or_404",
    "get_entity_query_service",
    "get_entity_repository",
    "get_evidence_repository",
    "get_ingestion_service",
    "get_relationship_repository",
    "entities_router",
    "evidence_router",
    "graph_router",
    "health_router",
]
