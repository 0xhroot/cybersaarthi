"""API contract tests: authentication and user management.

Exercises the public login, the ADMIN-only register endpoint and the /auth/me
identity endpoint, including validation and conflict handling.
"""

from __future__ import annotations

import uuid

import httpx
from app.core.auth import decode_access_token
from app.core.config import get_settings
from app.main import app

from tests.api.conftest import ApiUser

PASSWORD = "phase4-super-secret!"


async def _client(token: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_login_round_trip_and_me(http_client, api_user: ApiUser) -> None:
    prefix = get_settings().API_V1_PREFIX

    login = await http_client.post(
        f"{prefix}/auth/login",
        json={"username": api_user.username, "password": api_user.password},
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert body["user"]["username"] == api_user.username
    assert (
        decode_access_token(body["access_token"], secret=get_settings().SECRET_KEY) == api_user.id
    )

    me = await _client(body["access_token"])
    async with me:
        response = await me.get(f"{prefix}/auth/me")
    assert response.status_code == 200, response.text
    assert response.json()["user"]["id"] == str(api_user.id)
    assert "INVESTIGATOR" in response.json()["roles"]
    assert "case.create" in response.json()["permissions"]


async def test_login_supports_email_lookup(http_client, api_user: ApiUser) -> None:
    prefix = get_settings().API_V1_PREFIX
    email = f"{api_user.username}@cybersaarthi.test"
    login = await http_client.post(
        f"{prefix}/auth/login", json={"username": email, "password": api_user.password}
    )
    assert login.status_code == 200, login.text


async def test_login_rejects_bad_credentials(http_client, api_user: ApiUser) -> None:
    prefix = get_settings().API_V1_PREFIX
    for payload in (
        {"username": api_user.username, "password": "wrong-password-here"},
        {"username": f"ghost-{uuid.uuid4().hex[:8]}", "password": PASSWORD},
    ):
        response = await http_client.post(f"{prefix}/auth/login", json=payload)
        assert response.status_code == 401, response.text


async def test_me_requires_a_valid_token(http_client) -> None:
    prefix = get_settings().API_V1_PREFIX
    anon = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    async with anon:
        assert (await anon.get(f"{prefix}/auth/me")).status_code == 401
        response = await anon.get(
            f"{prefix}/auth/me", headers={"Authorization": "Bearer not-a-token"}
        )
        assert response.status_code == 401


async def test_register_requires_admin(http_client) -> None:
    prefix = get_settings().API_V1_PREFIX
    payload = {
        "username": f"nobody-{uuid.uuid4().hex[:8]}",
        "email": "nobody@cybersaarthi.test",
        "password": PASSWORD,
    }
    anon = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    async with anon:
        # Anonymous: no credentials at all.
        assert (await anon.post(f"{prefix}/auth/register", json=payload)).status_code == 401
    # Authenticated but not an administrator (no users.manage) -> 403.
    response = await http_client.post(f"{prefix}/auth/register", json=payload)
    assert response.status_code == 403, response.text


async def test_register_validates_payload(http_client, user_factory) -> None:
    prefix = get_settings().API_V1_PREFIX
    admin = await user_factory(role="ADMIN")
    async with await _client(admin.token) as client:
        cases = [
            {"username": "ab", "email": "x@y.test", "password": PASSWORD},  # username too short
            {"username": "ok-name", "email": "not-an-email", "password": PASSWORD},
            {"username": "ok-name", "email": "ok@y.test", "password": "short"},  # weak password
            {"username": "ok-name", "email": "ok@y.test", "password": PASSWORD, "role": "BOSS"},
        ]
        for payload in cases:
            response = await client.post(f"{prefix}/auth/register", json=payload)
            assert response.status_code == 422, response.text


async def test_register_creates_user_and_conflicts(http_client, user_factory) -> None:
    prefix = get_settings().API_V1_PREFIX
    admin = await user_factory(role="ADMIN")
    username = f"analyst-{uuid.uuid4().hex[:8]}"
    email = f"{username}@cybersaarthi.test"

    async with await _client(admin.token) as client:
        response = await client.post(
            f"{prefix}/auth/register",
            json={
                "username": username,
                "email": email,
                "password": PASSWORD,
                "role": "ANALYST",
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["user"]["username"] == username
        assert body["roles"] == ["ANALYST"]

        duplicate_name = await client.post(
            f"{prefix}/auth/register",
            json={"username": username, "email": f"other-{email}", "password": PASSWORD},
        )
        assert duplicate_name.status_code == 409

        duplicate_email = await client.post(
            f"{prefix}/auth/register",
            json={"username": f"other-{username}", "email": email, "password": PASSWORD},
        )
        assert duplicate_email.status_code == 409

    # The new analyst can authenticate.
    login = await http_client.post(
        f"{prefix}/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    me_payload = login.json()["user"]
    assert me_payload["username"] == username


async def test_login_throttled_after_too_many_failures(
    http_client, user_factory, monkeypatch
) -> None:
    """A06: /auth/login returns 429 once the IP+username budget is exhausted,
    then 200 again once the counters are cleared after a successful login."""
    from app.main import app as _app
    from app.services import throttle

    test_ip = "213.100.50.10"
    monkeypatch.setattr(throttle, "client_ip", lambda _request: test_ip)

    prefix = get_settings().API_V1_PREFIX
    user = await user_factory()
    settings = get_settings()
    saved = (settings.LOGIN_MAX_ATTEMPTS, settings.LOGIN_IP_MAX_ATTEMPTS)
    settings.LOGIN_MAX_ATTEMPTS = 2
    settings.LOGIN_IP_MAX_ATTEMPTS = 100
    try:
        for _ in range(settings.LOGIN_MAX_ATTEMPTS):
            response = await http_client.post(
                f"{prefix}/auth/login",
                json={"username": user.username, "password": "wrong-password"},
            )
            assert response.status_code == 401, response.text

        blocked = await http_client.post(
            f"{prefix}/auth/login",
            json={"username": user.username, "password": user.password},
        )
        assert blocked.status_code == 429, blocked.text

        # A successful login on the same IP+username clears the counters.
        await throttle.clear_attempts(_app.state.cache, user.username, test_ip)
        allowed = await http_client.post(
            f"{prefix}/auth/login",
            json={"username": user.username, "password": user.password},
        )
        assert allowed.status_code == 200, allowed.text
    finally:
        settings.LOGIN_MAX_ATTEMPTS, settings.LOGIN_IP_MAX_ATTEMPTS = saved
        await throttle.clear_attempts(_app.state.cache, user.username, test_ip)


async def test_logout_revokes_token_when_enabled(http_client, user_factory) -> None:
    """A07: with TOKEN_REVOCATION_ENABLED, /auth/logout makes the same bearer
    token unusable immediately (401 on a later authenticated call)."""
    from app.main import app as _app
    from app.services import token as token_svc

    settings = get_settings()
    saved = settings.TOKEN_REVOCATION_ENABLED
    settings.TOKEN_REVOCATION_ENABLED = True
    prefix = get_settings().API_V1_PREFIX
    user = await user_factory()
    try:
        login = await http_client.post(
            f"{prefix}/auth/login",
            json={"username": user.username, "password": user.password},
        )
        assert login.status_code == 200, login.text
        access_token = login.json()["access_token"]

        authed = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        async with authed:
            assert (await authed.get(f"{prefix}/auth/me")).status_code == 200
            assert (await authed.post(f"{prefix}/auth/logout")).status_code == 204
            assert (await authed.get(f"{prefix}/auth/me")).status_code == 401
    finally:
        settings.TOKEN_REVOCATION_ENABLED = saved
        jti = token_svc.token_jti(access_token, secret=settings.SECRET_KEY)
        if jti:
            await token_svc.revoke_token(_app.state.cache, jti, ttl_seconds=0)


async def test_logout_is_noop_when_disabled(http_client, user_factory) -> None:
    """A07: with revocation disabled, logout returns 204 but the token is not
    denylisted (stateless mode preserved)."""
    settings = get_settings()
    saved = settings.TOKEN_REVOCATION_ENABLED
    settings.TOKEN_REVOCATION_ENABLED = False
    prefix = get_settings().API_V1_PREFIX
    user = await user_factory()
    try:
        login = await http_client.post(
            f"{prefix}/auth/login",
            json={"username": user.username, "password": user.password},
        )
        access_token = login.json()["access_token"]
        authed = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        async with authed:
            assert (await authed.post(f"{prefix}/auth/logout")).status_code == 204
            assert (await authed.get(f"{prefix}/auth/me")).status_code == 200
    finally:
        settings.TOKEN_REVOCATION_ENABLED = saved
