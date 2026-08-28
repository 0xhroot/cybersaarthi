"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.errors import error_response
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.redis import Cache
from app.db.storage import Storage
from app.middleware import SecurityHeadersMiddleware

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    database = Database(settings)
    graph_store = GraphStore(settings)
    cache = Cache(settings)
    storage = Storage(settings)

    app.state.database = database
    app.state.graph_store = graph_store
    app.state.cache = cache
    app.state.storage = storage

    # Probe dependencies at startup. Failures are logged, not fatal: the
    # readiness endpoint reflects the real state of each service.
    probes = (
        ("postgres", database.ping),
        ("neo4j", graph_store.ping),
        ("redis", cache.ping),
        ("object_storage", storage.ping),
    )
    for name, probe in probes:
        try:
            await probe()
            logger.info("dependency ready at startup", extra={"service": name})
        except Exception:
            logger.warning("dependency unavailable at startup", extra={"service": name})

    yield

    await database.close()
    await graph_store.close()
    await cache.close()
    storage.close()
    logger.info("all infrastructure clients closed")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="CyberSaarthi API",
        description="AI-powered criminal network analysis - Phase 1 foundation.",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    return app


app = create_app()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning(
        "request validation failed", extra={"path": request.url.path, "errors": exc.errors()}
    )
    return error_response(422, "VALIDATION_ERROR", "Request validation failed")


_STATUS_CODE_NAMES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    503: "SERVICE_UNAVAILABLE",
}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    code = _STATUS_CODE_NAMES.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, code, detail)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error", extra={"path": request.url.path})
    return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred")
