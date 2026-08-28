"""API test fixtures.

The app's lifespan is not triggered when using ASGITransport, so the
infrastructure clients are wired onto ``app.state`` explicitly.
"""

from __future__ import annotations

import httpx
import pytest
from app.core.config import get_settings
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.redis import Cache
from app.db.storage import Storage
from app.main import app


@pytest.fixture
async def http_client():
    settings = get_settings()
    app.state.database = Database(settings)
    app.state.graph_store = GraphStore(settings)
    app.state.cache = Cache(settings)
    app.state.storage = Storage(settings)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
