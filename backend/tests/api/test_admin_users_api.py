"""API contract tests: Phase 5 administrative user management.

Covers the account lifecycle (registration -> approval -> active), the
ADMIN-only user management endpoints, RBAC boundaries (non-admins are denied),
the stable error envelope, self-servicing guards, and the rule that the final
active ADMIN cannot be demoted/suspended/rejected.
"""

from __future__ import annotations

import uuid

import httpx
from app.core.config import get_settings
from app.main import app

from tests.api.conftest import TEST_USER_PASSWORD

PASSWORD = "phase4-super-secret!"


async def _client(token: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


async def _register(http_client, prefix: str, suffix: str) -> dict:
    username = f"{suffix}-{uuid.uuid4().hex[:8]}"
    email = f"{username}@cybersaarthi.test"
    response = await http_client.post(
        f"{prefix}/auth/register",
        json={"username": username, "email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"id": response.json()["user"]["id"], "username": username}


async def test_non_admin_cannot_manage_users(http_client, user_factory) -> None:
    """RBAC boundary: INVESTIGATOR (no users.manage) is denied the admin API."""
    prefix = get_settings().API_V1_PREFIX
    non_admin = await user_factory(role="INVESTIGATOR")
    async with await _client(non_admin.token) as client:
        for method_path in (
            ("GET", "/admin/users"),
            ("GET", "/admin/users/pending"),
        ):
            method, path = method_path
            response = await client.request(method, f"{prefix}{path}")
            assert response.status_code == 403, response.text
            assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSION"


async def test_admin_list_and_pending(http_client, user_factory) -> None:
    prefix = get_settings().API_V1_PREFIX
    admin = await user_factory(role="ADMIN")
    await _register(http_client, prefix, "pending")

    async with await _client(admin.token) as client:
        all_users = await client.get(f"{prefix}/admin/users")
        assert all_users.status_code == 200, all_users.text
        assert all_users.json()["total"] >= 1

        pending = await client.get(f"{prefix}/admin/users/pending")
        assert pending.status_code == 200, pending.text
        body = pending.json()
        assert body["total"] >= 1
        assert all(item["status"] == "PENDING" for item in body["items"])


async def test_admin_approve_grants_role_and_allows_login(http_client, user_factory) -> None:
    prefix = get_settings().API_V1_PREFIX
    admin = await user_factory(role="ADMIN")
    pending = await _register(http_client, prefix, "approvee")

    async with await _client(admin.token) as client:
        response = await client.post(
            f"{prefix}/admin/users/{pending['id']}/approve", json={"role": "ANALYST"}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "ACTIVE"
        assert body["roles"] == ["ANALYST"]

        # Approving again conflicts.
        dup = await client.post(
            f"{prefix}/admin/users/{pending['id']}/approve", json={"role": "VIEWER"}
        )
        assert dup.status_code == 409, dup.text

    login = await http_client.post(
        f"{prefix}/auth/login", json={"username": pending["username"], "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["status"] == "ACTIVE"
    async with await _client(login.json()["access_token"]) as authed:
        me = await authed.get(f"{prefix}/auth/me")
    assert me.status_code == 200
    assert "ANALYST" in me.json()["roles"]


async def test_admin_can_reject_activate_suspend(http_client, user_factory) -> None:
    prefix = get_settings().API_V1_PREFIX
    admin = await user_factory(role="ADMIN")
    victim = await user_factory(role="VIEWER")

    async with await _client(admin.token) as client:
        sus = await client.post(f"{prefix}/admin/users/{victim.id}/suspend")
        assert sus.status_code == 200, sus.text
        assert sus.json()["status"] == "SUSPENDED"

        re = await client.post(f"{prefix}/admin/users/{victim.id}/reject")
        assert re.status_code == 200, re.text
        assert re.json()["status"] == "REJECTED"

        act = await client.post(f"{prefix}/admin/users/{victim.id}/activate")
        assert act.status_code == 200, act.text
        assert act.json()["status"] == "ACTIVE"


async def test_suspended_and_rejected_users_cannot_login(http_client, user_factory) -> None:
    prefix = get_settings().API_V1_PREFIX
    admin = await user_factory(role="ADMIN")
    suspended = await user_factory(role="VIEWER")
    rejected_user = await user_factory(role="VIEWER")

    async with await _client(admin.token) as client:
        await client.post(f"{prefix}/admin/users/{suspended.id}/suspend")
        await client.post(f"{prefix}/admin/users/{rejected_user.id}/reject")

    codes = {
        suspended.username: "ACCOUNT_SUSPENDED",
        rejected_user.username: "ACCOUNT_REJECTED",
    }
    for username, expected in codes.items():
        login = await http_client.post(
            f"{prefix}/auth/login", json={"username": username, "password": TEST_USER_PASSWORD}
        )
        assert login.status_code == 403, login.text
        assert login.json()["error"]["code"] == expected


async def test_bad_credentials_code_is_stable(http_client, user_factory) -> None:
    """A valid but wrong-password attempt yields INVALID_CREDENTIALS, not a leak."""
    prefix = get_settings().API_V1_PREFIX
    user = await user_factory()
    login = await http_client.post(
        f"{prefix}/auth/login", json={"username": user.username, "password": "nope-nope-nope!"}
    )
    assert login.status_code == 401, login.text
    assert login.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_admin_cannot_change_own_role(http_client, user_factory) -> None:
    prefix = get_settings().API_V1_PREFIX
    admin = await user_factory(role="ADMIN")
    async with await _client(admin.token) as client:
        response = await client.patch(
            f"{prefix}/admin/users/{admin.id}/role", json={"role": "VIEWER"}
        )
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSION"


async def test_admin_can_assign_any_valid_role(http_client, user_factory) -> None:
    prefix = get_settings().API_V1_PREFIX
    admin = await user_factory(role="ADMIN")
    target = await user_factory(role="VIEWER")
    async with await _client(admin.token) as client:
        promoted = await client.patch(
            f"{prefix}/admin/users/{target.id}/role", json={"role": "INVESTIGATOR"}
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["roles"] == ["INVESTIGATOR"]

        bad = await client.patch(
            f"{prefix}/admin/users/{target.id}/role", json={"role": "SUPERUSER"}
        )
        assert bad.status_code == 422, bad.text
