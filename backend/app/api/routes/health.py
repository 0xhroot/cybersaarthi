"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.core.config import get_settings
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.readiness import ReadinessService

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.APP_NAME, version=__version__)


@router.get("/ready", response_model=ReadinessResponse)
async def ready(request: Request) -> JSONResponse | ReadinessResponse:
    service = ReadinessService(
        database=request.app.state.database,
        graph_store=request.app.state.graph_store,
        cache=request.app.state.cache,
        storage=request.app.state.storage,
    )
    response, all_ready = await service.check()
    status_code = 200 if all_ready else 503
    return JSONResponse(status_code=status_code, content=response.model_dump())
