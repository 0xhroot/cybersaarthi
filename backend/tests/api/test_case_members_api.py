"""API contract tests: case membership and IDOR hardening.

Sharing a case grants the member read (and the appropriate scoped mutations if
their roles allow it) without making them the owner. Membership management is
restricted to the owner or an ADMIN. A non-owner, non-member still gets 403
(IDOR), and once removed a former member loses access immediately.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from app.db.postgres import Database
from app.main import app
from app.models import Case, CaseMember
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
async def _owned_case(database: Database, api_user: ApiUser) -> uuid.UUID:
    case = Case(
        id=uuid.uuid4(),
        case_number=f"CSM-{uuid.uuid4().hex[:8]}",
        title="case membership test case",
        description="created directly for membership tests",
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
        await session.execute(delete(CaseMember).where(CaseMember.case_id == case_id))
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()


async def test_stranger_is_denied_member_management(http_client, _owned_case, user_factory) -> None:
    prefix = get_settings().API_V1_PREFIX
    stranger = await user_factory(role="INVESTIGATOR")
    member = await user_factory(role="VIEWER")
    async with _client(stranger.token) as client:
        list_resp = await client.get(f"{prefix}/cases/{_owned_case}/members")
        assert list_resp.status_code == 403, list_resp.text
        add_resp = await client.post(
            f"{prefix}/cases/{_owned_case}/members",
            json={"user_id": str(member.id), "role": "viewer"},
        )
        assert add_resp.status_code == 403, add_resp.text


async def test_member_gains_access_and_former_member_loses_it(
    http_client, _owned_case, user_factory
) -> None:
    prefix = get_settings().API_V1_PREFIX
    member = await user_factory(role="VIEWER")

    # Not yet a member: GET 403.
    async with _client(member.token) as client:
        assert (await client.get(f"{prefix}/cases/{_owned_case}")).status_code == 403

    # Owner adds the member.
    add_resp = await http_client.post(
        f"{prefix}/cases/{_owned_case}/members",
        json={"user_id": str(member.id), "role": "viewer"},
    )
    assert add_resp.status_code == 201, add_resp.text
    assert any(item["user_id"] == str(member.id) for item in add_resp.json()["items"])

    # Member can now read the case, and sees it in their own list.
    async with _client(member.token) as client:
        assert (await client.get(f"{prefix}/cases/{_owned_case}")).status_code == 200
        listed = await client.get(f"{prefix}/cases")
        assert listed.status_code == 200, listed.text
        assert any(item["id"] == str(_owned_case) for item in listed.json()["items"])

    # Owner removes the member -> access is revoked immediately.
    remove_resp = await http_client.delete(f"{prefix}/cases/{_owned_case}/members/{member.id}")
    assert remove_resp.status_code == 200, remove_resp.text
    async with _client(member.token) as client:
        assert (await client.get(f"{prefix}/cases/{_owned_case}")).status_code == 403


async def test_adding_duplicate_member_conflicts(http_client, _owned_case, user_factory) -> None:
    prefix = get_settings().API_V1_PREFIX
    member = await user_factory(role="VIEWER")
    await http_client.post(
        f"{prefix}/cases/{_owned_case}/members",
        json={"user_id": str(member.id), "role": "viewer"},
    )
    dup = await http_client.post(
        f"{prefix}/cases/{_owned_case}/members",
        json={"user_id": str(member.id), "role": "viewer"},
    )
    assert dup.status_code == 409, dup.text


async def test_missing_user_and_missing_member_are_404(
    http_client, _owned_case, user_factory
) -> None:
    prefix = get_settings().API_V1_PREFIX
    bogus = await http_client.post(
        f"{prefix}/cases/{_owned_case}/members",
        json={"user_id": str(uuid.uuid4()), "role": "viewer"},
    )
    assert bogus.status_code == 404, bogus.text

    removed = await http_client.delete(f"{prefix}/cases/{_owned_case}/members/{uuid.uuid4()}")
    assert removed.status_code == 404, removed.text


async def test_member_management_requires_case_update_permission(
    http_client, _owned_case, user_factory
) -> None:
    """VIEWER members can read but cannot manage membership of the case."""
    prefix = get_settings().API_V1_PREFIX
    member = await user_factory(role="VIEWER")
    await http_client.post(
        f"{prefix}/cases/{_owned_case}/members",
        json={"user_id": str(member.id), "role": "viewer"},
    )
    other = await user_factory(role="VIEWER")
    async with _client(member.token) as client:
        add = await client.post(
            f"{prefix}/cases/{_owned_case}/members",
            json={"user_id": str(other.id), "role": "viewer"},
        )
        assert add.status_code == 403, add.text
