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


async def test_list_search_status_and_pagination_totals(
    http_client, database: Database, api_user: ApiUser
) -> None:
    """Regression for A17/F01: list filters and totals are computed in SQL.

    Search narrows on title/case number, status filters the lifecycle state,
    and ``total`` reflects the *filtered* universe even when a page boundary
    cuts the result short.
    """
    prefix = get_settings().API_V1_PREFIX
    marker = uuid.uuid4().hex[:8]
    created_ids: list[str] = []
    factory = database.session_factory()
    try:
        for i, status in enumerate(["open", "open", "in_progress"]):
            response = await http_client.post(
                f"{prefix}/cases",
                json={
                    "title": f"search-probe-{marker}-{i}",
                    "description": "regression list filters",
                    "status": status,
                },
            )
            assert response.status_code == 201, response.text
            created_ids.append(response.json()["id"])

        # "archived" is reachable only through the archive endpoint (the create
        # contract reserves it), so seed an archived case directly.
        archived_case = Case(
            id=uuid.uuid4(),
            case_number=f"CSE-{uuid.uuid4().hex[:8]}",
            title=f"search-probe-{marker}-3",
            status="archived",
            owner_id=api_user.id,
        )
        async with factory() as session:
            session.add(archived_case)
            await session.commit()
        created_ids.append(str(archived_case.id))

        # Search by title substring: only the matching page set is returned,
        # and total matches the substring, not the page.
        all_matches = await http_client.get(f"{prefix}/cases?search={marker}")
        assert all_matches.status_code == 200, all_matches.text
        payload = all_matches.json()
        assert payload["total"] == 4
        assert len(payload["items"]) == 4
        assert all(f"search-probe-{marker}" in item["title"] for item in payload["items"])

        # Search also matches the case number reference.
        probe = all_matches.json()["items"][0]
        by_number = await http_client.get(f"{prefix}/cases?search={probe['case_number'][:6]}")
        assert by_number.status_code == 200, by_number.text
        assert any(item["id"] == probe["id"] for item in by_number.json()["items"])

        # A query that matches nothing is an empty page, not an error.
        empty = await http_client.get(f"{prefix}/cases?search={marker}-nope")
        assert empty.status_code == 200, empty.text
        assert empty.json()["total"] == 0
        assert empty.json()["items"] == []

        # Status filter narrows to a single lifecycle state.
        open_only = await http_client.get(f"{prefix}/cases?search={marker}&status=open")
        assert open_only.status_code == 200, open_only.text
        assert open_only.json()["total"] == 2
        assert all(item["status"] == "open" for item in open_only.json()["items"])

        # Inserted statuses survive round trips, including archived.
        archived = await http_client.get(f"{prefix}/cases?search={marker}&status=archived")
        assert archived.status_code == 200, archived.text
        assert archived.json()["total"] == 1
        assert archived.json()["items"][0]["status"] == "archived"

        # Pagination: total is the filtered total even when the page is small.
        small_page = await http_client.get(f"{prefix}/cases?search={marker}&limit=1")
        assert small_page.status_code == 200, small_page.text
        assert small_page.json()["total"] == 4
        assert len(small_page.json()["items"]) == 1

        # Offsets walk the same filtered universe.
        page_two = await http_client.get(f"{prefix}/cases?search={marker}&limit=2&offset=2")
        assert page_two.status_code == 200, page_two.text
        assert page_two.json()["total"] == 4
        assert len(page_two.json()["items"]) == 2

        # Status values outside the lifecycle are rejected by the contract.
        bad = await http_client.get(f"{prefix}/cases?status=junk")
        assert bad.status_code == 422, bad.text
    finally:
        async with factory() as session:
            if created_ids:
                await session.execute(delete(Case).where(Case.id.in_(created_ids)))
            await session.commit()
