"""Session-level guard for integration tests.

If the Compose infrastructure is not reachable the whole integration suite is
skipped with an actionable message instead of failing on a developer's host.
"""

from __future__ import annotations

import asyncio

import pytest
from app.core.config import get_settings
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.redis import Cache
from app.db.storage import Storage


@pytest.fixture(scope="session", autouse=True)
def require_infrastructure() -> None:
    settings = get_settings()
    database = Database(settings)
    graph_store = GraphStore(settings)
    cache = Cache(settings)
    storage = Storage(settings)

    unreachable: list[str] = []
    for name, client in (
        ("postgres", database),
        ("neo4j", graph_store),
        ("redis", cache),
        ("object_storage", storage),
    ):
        try:
            asyncio.run(client.ping())
        except Exception:
            unreachable.append(name)

    if unreachable:
        pytest.skip(
            "infrastructure unreachable "
            f"({', '.join(unreachable)}) - run `make up` before integration tests"
        )
