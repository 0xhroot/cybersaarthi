"""Security tests: the IDOR matrix and role-based permission denials.

Every case-scoped route must answer 401 to anonymous callers, 403 to an
authenticated non-owner, and 404 for a missing case. Roles gate state-changing
routes even when the actor is the owner.
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

CSV_BYTES = (
    b"name,phone,organization,vehicle_no,city\n"
    b"Rajesh Kumar,9876543210,TechSecure Pvt Ltd,MH12AB1234,Mumbai\n"
).decode()


def _client(token: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )


@pytest.fixture
async def _secure_case(database: Database, api_user: ApiUser) -> uuid.UUID:
    case = Case(
        id=uuid.uuid4(),
        case_number=f"SEC-{uuid.uuid4().hex[:8]}",
        title="security matrix case",
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


@pytest.mark.parametrize(
    "method,path_factory",
    [
        ("GET", lambda c: f"{c}"),
        ("PATCH", lambda c: f"{c}"),
        ("POST", lambda c: f"{c}/archive"),
        ("GET", lambda c: f"{c}/evidence"),
        ("GET", lambda c: f"{c}/ingest-jobs"),
        ("GET", lambda c: f"{c}/findings"),
        ("GET", lambda c: f"{c}/findings/stats"),
        ("GET", lambda c: f"{c}/entities"),
        ("GET", lambda c: f"{c}/relationships"),
        ("GET", lambda c: f"{c}/graph"),
        ("GET", lambda c: f"{c}/graph/stats"),
        ("GET", lambda c: f"{c}/analytics/summary"),
        ("POST", lambda c: f"{c}/analytics/run"),
        ("GET", lambda c: f"{c}/analytics/runs"),
    ],
)
async def test_stranger_gets_403_on_every_case_route(
    method: str, path_factory, http_client, _secure_case, user_factory
) -> None:
    prefix = get_settings().API_V1_PREFIX
    stranger = await user_factory(role="INVESTIGATOR")
    path = f"{prefix}/cases/{path_factory(_secure_case)}"
    async with _client(stranger.token) as client:
        if method == "PATCH":
            response = await client.request(method, path, json={"title": "x"})
        else:
            response = await client.request(method, path)
    assert response.status_code == 403, (method, path, response.text)


async def test_stranger_gets_403_uploading_and_ingesting(
    http_client, _secure_case, user_factory
) -> None:
    prefix = get_settings().API_V1_PREFIX
    case_id = _secure_case
    stranger = await user_factory(role="INVESTIGATOR")
    async with _client(stranger.token) as client:
        upload = await client.post(
            f"{prefix}/cases/{case_id}/evidence",
            files={"file": ("x.csv", CSV_BYTES.encode(), "text/csv")},
            data={"data_source": "csv"},
        )
        assert upload.status_code == 403
        ingest = await client.post(
            f"{prefix}/cases/{case_id}/ingest",
            json={"evidence_file_id": str(uuid.uuid4())},
        )
        assert ingest.status_code == 403


async def test_anonymous_gets_401_on_every_case_route(http_client, _secure_case) -> None:
    prefix = get_settings().API_V1_PREFIX
    case_id = _secure_case
    anon = _client("")
    async with anon:
        for method, path in [
            ("GET", f"{prefix}/cases/{case_id}"),
            ("PATCH", f"{prefix}/cases/{case_id}"),
            ("POST", f"{prefix}/cases/{case_id}/archive"),
            ("GET", f"{prefix}/cases/{case_id}/evidence"),
            ("GET", f"{prefix}/cases/{case_id}/findings"),
            ("GET", f"{prefix}/cases/{case_id}/graph"),
            ("GET", f"{prefix}/cases/{case_id}/analytics/summary"),
            ("POST", f"{prefix}/cases/{case_id}/analytics/run"),
            ("GET", f"{prefix}/audit-logs"),
        ]:
            kwargs = {"json": {"title": "x"}} if method == "PATCH" else {}
            response = await anon.request(method, path, **kwargs)
            assert response.status_code == 401, (method, path, response.text)


async def test_admin_can_access_another_investigators_case(
    http_client, _secure_case, user_factory
) -> None:
    prefix = get_settings().API_V1_PREFIX
    case_id = _secure_case
    admin = await user_factory(role="ADMIN")
    async with _client(admin.token) as client:
        assert (await client.get(f"{prefix}/cases/{case_id}")).status_code == 200
        updated = await client.patch(f"{prefix}/cases/{case_id}", json={"title": "by admin"})
        assert updated.status_code == 200
        assert (await client.post(f"{prefix}/cases/{case_id}/archive")).status_code == 200


@pytest.mark.parametrize("role", ["VIEWER", "ANALYST"])
async def test_read_only_roles_cannot_create_cases(http_client, user_factory, role: str) -> None:
    prefix = get_settings().API_V1_PREFIX
    user = await user_factory(role=role)
    async with _client(user.token) as client:
        response = await client.post(f"{prefix}/cases", json={"title": "denied"})
        assert response.status_code == 403, response.text


@pytest.mark.parametrize("role", ["VIEWER", "ANALYST"])
async def test_non_admin_roles_cannot_read_the_audit_log(
    http_client, user_factory, role: str
) -> None:
    prefix = get_settings().API_V1_PREFIX
    user = await user_factory(role=role)
    async with _client(user.token) as client:
        assert (await client.get(f"{prefix}/audit-logs")).status_code == 403


async def test_viewer_cannot_mutate_evidence_or_run_analytics(
    http_client, _secure_case, user_factory
) -> None:
    prefix = get_settings().API_V1_PREFIX
    case_id = _secure_case
    viewer = await user_factory(role="VIEWER")
    async with _client(viewer.token) as client:
        upload = await client.post(
            f"{prefix}/cases/{case_id}/evidence",
            files={"file": ("x.csv", CSV_BYTES.encode(), "text/csv")},
            data={"data_source": "csv"},
        )
        assert upload.status_code == 403
        assert (await client.post(f"{prefix}/cases/{case_id}/analytics/run")).status_code == 403


async def test_listing_is_filtered_to_owned_cases(
    http_client, database: Database, user_factory
) -> None:
    prefix = get_settings().API_V1_PREFIX
    other = await user_factory(role="INVESTIGATOR")
    other_case = Case(
        id=uuid.uuid4(),
        case_number=f"OWN-{uuid.uuid4().hex[:8]}",
        title="someone elses case",
        owner_id=other.id,
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(other_case)
        await session.commit()
        other_case_id = other_case.id

    try:
        mine = await http_client.get(f"{prefix}/cases")
        assert mine.status_code == 200
        assert all(item["owner_id"] != str(other.id) for item in mine.json()["items"])
        theirs = _client(other.token)
        async with theirs:
            listed = await theirs.get(f"{prefix}/cases")
            assert listed.json()["total"] == 1
            assert listed.json()["items"][0]["id"] == str(other_case_id)
    finally:
        async with factory() as session:
            await session.execute(delete(Case).where(Case.id == other_case_id))
            await session.commit()
