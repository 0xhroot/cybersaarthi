"""API contract tests: case lifecycle and ownership semantics.

Cases belong to their creator. A stranger is authenticated but not the owner,
so they get 403 (the IDOR guard); a missing case gets 404 and an anonymous
caller gets 401.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from app.db.postgres import Database
from app.main import app
from app.models import Case
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from tests.api.conftest import ApiUser


def _client(token: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )


@pytest.fixture
async def _scratch_case(database: Database, api_user: ApiUser) -> uuid.UUID:
    case = Case(
        id=uuid.uuid4(),
        case_number=f"CSE-{uuid.uuid4().hex[:8]}",
        title="cases api test case",
        description="created directly for the case tests",
        status="open",
        owner_id=api_user.id,
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.commit()
        case_id = case.id
    yield case_id
    async with factory() as session:
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()


async def test_create_then_list_then_get(http_client, database: Database) -> None:
    prefix = get_settings().API_V1_PREFIX
    created = await http_client.post(
        f"{prefix}/cases", json={"title": "new case", "description": "d"}
    )
    assert created.status_code == 201, created.text
    case = created.json()
    assert case["case_number"].startswith("CS-")
    assert case["status"] == "open"

    listed = await http_client.get(f"{prefix}/cases")
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] >= 1
    assert any(item["id"] == case["id"] for item in listed.json()["items"])

    fetched = await http_client.get(f"{prefix}/cases/{case['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == case["id"]

    # The case is owned by the ephemeral api_user; remove it before teardown
    # deletes the user.
    factory = database.session_factory()
    async with factory() as session:
        await session.execute(delete(Case).where(Case.id == case["id"]))
        await session.commit()


async def test_update_and_archive(http_client, _scratch_case) -> None:
    case_id = _scratch_case
    prefix = get_settings().API_V1_PREFIX

    updated = await http_client.patch(
        f"{prefix}/cases/{case_id}", json={"title": "renamed", "status": "in_progress"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "renamed"
    assert updated.json()["status"] == "in_progress"

    archived = await http_client.post(f"{prefix}/cases/{case_id}/archive")
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"

    # PATCHing status to the reserved value is blocked with a clear 422.
    blocked = await http_client.patch(f"{prefix}/cases/{case_id}", json={"status": "archived"})
    assert blocked.status_code == 422, blocked.text


async def test_owner_access_but_stranger_403_and_missing_404(
    http_client, _scratch_case, user_factory
) -> None:
    case_id = _scratch_case
    prefix = get_settings().API_V1_PREFIX

    assert (await http_client.get(f"{prefix}/cases/{case_id}")).status_code == 200

    stranger = await user_factory(role="INVESTIGATOR")
    async with _client(stranger.token) as client:
        assert (await client.get(f"{prefix}/cases/{case_id}")).status_code == 403
        assert (
            await client.patch(f"{prefix}/cases/{case_id}", json={"title": "steal"})
        ).status_code == 403
        assert (await client.post(f"{prefix}/cases/{case_id}/archive")).status_code == 403
        assert (await client.get(f"{prefix}/cases/{case_id}/evidence")).status_code == 403

    missing = uuid.uuid4()
    assert (await http_client.get(f"{prefix}/cases/{missing}")).status_code == 404
    assert (
        await http_client.patch(f"{prefix}/cases/{missing}", json={"title": "x"})
    ).status_code == 404


async def test_anonymous_callers_are_rejected(http_client) -> None:
    prefix = get_settings().API_V1_PREFIX
    anon = _client("")
    async with anon:
        assert (await anon.get(f"{prefix}/cases")).status_code == 401
        response = await anon.post(f"{prefix}/cases", json={"title": "no"})
        assert response.status_code == 401
        # Anonymous on a missing case is resolved 404 before auth (by design).
        assert (
            await anon.get(f"{prefix}/cases/00000000-0000-0000-0000-000000000000")
        ).status_code == 404
