"""API test fixtures.

The app's lifespan is not triggered when using ASGITransport, so the
infrastructure clients are wired onto ``app.state`` explicitly.

Phase 4: every request runs through authentication and case-scoped access
control, so the base client carries a valid bearer token for a dedicated
INVESTIGATOR account and case fixtures assign that account as owner.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import httpx
import pytest
from app.core.auth import create_access_token
from app.core.config import Settings, get_settings
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.redis import Cache
from app.db.storage import Storage
from app.main import app
from app.models import User
from app.repositories.user_repository import UserRepository
from app.services.users import UserService
from sqlalchemy import delete

TEST_USER_PASSWORD = "phase4-test-password!"


@dataclass(frozen=True)
class ApiUser:
    id: uuid.UUID
    username: str
    password: str
    token: str


@pytest.fixture
async def api_user(database: Database, settings: Settings) -> ApiUser:
    user = await _create_user(database, settings, "INVESTIGATOR")
    yield user
    await _delete_user(database, user.id)


@pytest.fixture
async def user_factory(database: Database, settings: Settings):
    """Create ephemeral users with any role; all are cleaned up on teardown."""
    created: list[uuid.UUID] = []

    async def _make(role: str = "INVESTIGATOR") -> ApiUser:
        user = await _create_user(database, settings, role)
        created.append(user.id)
        return user

    yield _make
    for user_id in created:
        await _delete_user(database, user_id)


async def _create_user(database: Database, settings: Settings, role: str) -> ApiUser:
    username = f"{role.lower()[:4]}-{uuid.uuid4().hex[:10]}"
    factory = database.session_factory()
    async with factory() as session:
        service = UserService(UserRepository(session))
        user = await service.create_user_with_role(
            username=username,
            email=f"{username}@cybersaarthi.test",
            password=TEST_USER_PASSWORD,
            role=role,
        )
        await session.commit()
        user_id = user.id
    token = create_access_token(
        user_id, secret=settings.SECRET_KEY, expires_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return ApiUser(id=user_id, username=username, password=TEST_USER_PASSWORD, token=token)


async def _delete_user(database: Database, user_id: uuid.UUID) -> None:
    factory = database.session_factory()
    async with factory() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


@pytest.fixture(scope="session", autouse=True)
async def _graph_store_hygiene(graph_store: GraphStore, database: Database):
    """Keep the live Neo4j store aligned with PostgreSQL after the API suite.

    API tests sync one case after another into the shared store and delete the
    PostgreSQL case rows on teardown, which would otherwise leave ghost
    projections behind (A02). After the suite, any projection whose case id no
    longer exists in PostgreSQL is purged.
    """
    yield
    from app.services.graph_sync import GraphSyncService
    from sqlalchemy import text

    service = GraphSyncService(graph_store, get_settings())
    case_ids: list[str] = []
    async with graph_store.driver().session() as session:
        result = await session.run("MATCH (n:Entity) RETURN DISTINCT n.case_id AS cid")
        case_ids = [record["cid"] async for record in result]
    if not case_ids:
        return
    factory = database.session_factory()
    async with factory() as session:
        existing = (
            (
                await session.execute(
                    text("SELECT id FROM cases WHERE id::text = ANY(:ids)"),
                    {"ids": case_ids},
                )
            )
            .scalars()
            .all()
        )
    live = {str(row) for row in existing}
    for case_id in case_ids:
        if case_id not in live:
            await service.delete_case(case_id)


@pytest.fixture(scope="session", autouse=True)
async def _object_store_hygiene(storage: Storage, database: Database):
    """Keep the live MinIO bucket aligned with PostgreSQL after the API suite.

    The suite uploads objects for cases whose PostgreSQL rows are deleted at
    teardown (evidence cascades away with the case), leaving orphan objects
    behind (A03). After the suite, every object not stored under a live case
    prefix is purged.
    """
    yield
    from sqlalchemy import text

    keys = await asyncio.to_thread(storage.list_keys, "cases/")
    if not keys:
        return
    factory = database.session_factory()
    async with factory() as session:
        case_rows = (await session.execute(text("SELECT id FROM cases"))).scalars().all()
    live_prefixes = [f"cases/{str(case_id)}/" for case_id in case_rows]
    doomed = [key for key in keys if not any(key.startswith(p) for p in live_prefixes)]
    await asyncio.to_thread(storage.delete_objects, doomed)


@pytest.fixture
async def http_client(api_user: ApiUser):
    settings = get_settings()
    app.state.database = Database(settings)
    app.state.graph_store = GraphStore(settings)
    app.state.cache = Cache(settings)
    app.state.storage = Storage(settings)

    headers = {"Authorization": f"Bearer {api_user.token}"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", headers=headers
    ) as async_client:
        yield async_client
