"""Shared fixtures for the API and integration test suites."""

from __future__ import annotations

import pytest
from app.core.config import Settings, get_settings
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.redis import Cache
from app.db.storage import Storage


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
async def database(settings: Settings) -> Database:
    client = Database(settings)
    yield client
    await client.close()


@pytest.fixture(scope="session")
async def graph_store(settings: Settings) -> GraphStore:
    client = GraphStore(settings)
    yield client
    await client.close()


@pytest.fixture(scope="session")
async def cache(settings: Settings) -> Cache:
    client = Cache(settings)
    yield client
    await client.close()


@pytest.fixture(scope="session")
async def storage(settings: Settings) -> Storage:
    client = Storage(settings)
    yield client
    client.close()
