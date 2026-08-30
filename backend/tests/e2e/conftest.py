"""E2E fixtures: wire the infrastructure clients onto ``app.state``.

The ASGI transport does not run the app's lifespan, so the same explicit
wiring used by the API tests is applied here.
"""

from __future__ import annotations

import pytest
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.redis import Cache
from app.db.storage import Storage
from app.main import app


@pytest.fixture(scope="session", autouse=True)
async def _wire_app_state(
    database: Database,
    graph_store: GraphStore,
    cache: Cache,
    storage: Storage,
) -> None:
    app.state.database = database
    app.state.graph_store = graph_store
    app.state.cache = cache
    app.state.storage = storage
    yield
