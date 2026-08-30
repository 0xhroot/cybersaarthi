"""API contract tests: the append-only audit trail."""

from __future__ import annotations

from app.core.config import get_settings
from app.main import app
from httpx import ASGITransport, AsyncClient

from tests.api.conftest import ApiUser


async def _client(token: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )


async def test_audit_records_case_creation_and_filters_by_case(
    http_client, api_user: ApiUser
) -> None:
    prefix = get_settings().API_V1_PREFIX
    created = await http_client.post(f"{prefix}/cases", json={"title": "audit trail case"})
    assert created.status_code == 201
    case_id = created.json()["id"]

    try:
        unfiltered = await http_client.get(f"{prefix}/audit-logs")
        assert unfiltered.status_code == 200
        assert unfiltered.json()["total"] >= 1

        by_case = await http_client.get(f"{prefix}/audit-logs", params={"case_id": case_id})
        assert by_case.status_code == 200
        assert all(item["case_id"] == case_id for item in by_case.json()["items"])

        by_action = await http_client.get(
            f"{prefix}/audit-logs", params={"case_id": case_id, "action": "case.created"}
        )
        assert by_action.json()["total"] == 1
        event = by_action.json()["items"][0]
        assert event["actor_id"] == str(api_user.id)
        assert event["resource_type"] == "case"
        assert event["resource_id"] == case_id
    finally:
        from app.db.postgres import Database
        from app.models import Case
        from sqlalchemy import delete

        db = Database(get_settings())
        factory = db.session_factory()
        async with factory() as session:
            await session.execute(delete(Case).where(Case.id == case_id))
            await session.commit()
        await db.close()


async def test_audit_records_login_success_and_failure(http_client, api_user: ApiUser) -> None:
    prefix = get_settings().API_V1_PREFIX
    import uuid as _uuid

    await http_client.post(
        f"{prefix}/auth/login",
        json={"username": api_user.username, "password": api_user.password},
    )
    # Wrong password on a KNOWN account records a login_failed event.
    await http_client.post(
        f"{prefix}/auth/login",
        json={"username": api_user.username, "password": "wrong-password"},
    )
    # An unknown username records NOTHING so account existence is not leaked.
    ghost = f"ghost-{_uuid.uuid4().hex[:8]}"
    await http_client.post(f"{prefix}/auth/login", json={"username": ghost, "password": "wrong"})

    succeeded = await http_client.get(
        f"{prefix}/audit-logs", params={"action": "auth.login_succeeded"}
    )
    assert any(item["actor_id"] == str(api_user.id) for item in succeeded.json()["items"])

    failed = await http_client.get(f"{prefix}/audit-logs", params={"action": "auth.login_failed"})
    assert any(item["actor_id"] == str(api_user.id) for item in failed.json()["items"])
    assert all(item["resource_id"] != ghost for item in failed.json()["items"])


async def test_audit_pagination_is_stable(http_client) -> None:
    prefix = get_settings().API_V1_PREFIX
    page_one = await http_client.get(f"{prefix}/audit-logs", params={"limit": 5, "offset": 0})
    assert page_one.status_code == 200
    body = page_one.json()
    assert body["limit"] == 5
    assert body["offset"] == 0
    assert len(body["items"]) <= 5
    assert body["total"] >= len(body["items"])
    # Newest first: timestamps are monotonically non-increasing.
    timestamps = [item["created_at"] for item in body["items"]]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_audit_log_is_denied_for_viewers(http_client, user_factory) -> None:
    prefix = get_settings().API_V1_PREFIX
    viewer = await user_factory(role="VIEWER")
    async with await _client(viewer.token) as client:
        assert (await client.get(f"{prefix}/audit-logs")).status_code == 403
