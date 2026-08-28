"""Readiness aggregation: probes each infrastructure dependency."""

from __future__ import annotations

import logging

from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.redis import Cache
from app.db.storage import Storage
from app.schemas.health import ReadinessResponse, ServiceStates

logger = logging.getLogger(__name__)

HEALTHY = "ok"
UNHEALTHY = "unavailable"


class ReadinessService:
    def __init__(
        self,
        database: Database,
        graph_store: GraphStore,
        cache: Cache,
        storage: Storage,
    ) -> None:
        self._database = database
        self._graph_store = graph_store
        self._cache = cache
        self._storage = storage

    async def check(self) -> tuple[ReadinessResponse, bool]:
        probes = (
            ("postgres", self._database.ping),
            ("neo4j", self._graph_store.ping),
            ("redis", self._cache.ping),
            ("object_storage", self._storage.ping),
        )

        states: dict[str, str] = {}
        for name, probe in probes:
            try:
                await probe()
                states[name] = HEALTHY
            except Exception:
                logger.warning("readiness probe failed", extra={"service": name})
                states[name] = UNHEALTHY

        all_ready = all(state == HEALTHY for state in states.values())
        response = ReadinessResponse(
            status="ready" if all_ready else "not_ready",
            services=ServiceStates(**states),
        )
        return response, all_ready
