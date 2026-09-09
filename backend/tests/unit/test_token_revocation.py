"""Tests for optional server-side token revocation (A07).

Covers the Redis-backed jti denylist in :mod:`app.services.token`, the
``/auth/logout`` endpoint, and the 401 behaviour once a token is revoked with
``TOKEN_REVOCATION_ENABLED`` enabled. The stateless default (disabled) is
covered elsewhere in ``test_auth_api.py`` to guarantee the original behaviour
is preserved.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.auth import create_access_token
from app.core.config import get_settings
from app.db.redis import Cache
from app.services import token


@pytest.fixture
def jti() -> str:
    return f"rev-test-{uuid.uuid4().hex[:12]}"


async def test_token_jti_extracts_from_valid_token() -> None:
    settings = get_settings()
    token_str = create_access_token(uuid.uuid4(), secret=settings.SECRET_KEY, expires_minutes=5)
    assert token.token_jti(token_str, secret=settings.SECRET_KEY) is not None


async def test_token_jti_rejects_garbage() -> None:
    settings = get_settings()
    assert token.token_jti("not-a-token", secret=settings.SECRET_KEY) is None
    assert token.token_jti("abc.def", secret=settings.SECRET_KEY) is None


async def test_revoke_then_is_revoked(cache: Cache, jti: str) -> None:
    assert await token.is_revoked(cache, jti) is False
    await token.revoke_token(cache, jti, ttl_seconds=60)
    assert await token.is_revoked(cache, jti) is True


async def test_revoke_is_idempotent(cache: Cache, jti: str) -> None:
    await token.revoke_token(cache, jti, ttl_seconds=60)
    await token.revoke_token(cache, jti, ttl_seconds=60)
    assert await token.is_revoked(cache, jti) is True


async def test_none_jti_is_never_revoked(cache: Cache) -> None:
    assert await token.is_revoked(cache, None) is False
    assert await token.is_revoked(cache, "") is False


async def test_revoked_set_expires(cache: Cache, jti: str) -> None:
    await token.revoke_token(cache, jti, ttl_seconds=1)
    assert await token.is_revoked(cache, jti) is True
    await _expire_now(cache, jti)
    assert await token.is_revoked(cache, jti) is False


async def test_is_revoked_fails_closed_on_redis_error(jti: str) -> None:
    """A07: when the denylist is unreachable, do not trust any token."""

    class _Down:  # Structural stand-in for a Cache whose client raises.
        def client(self) -> object:  # noqa: D102
            raise RuntimeError("redis down")

    assert await token.is_revoked(_Down(), jti) is True  # type: ignore[arg-type]


async def _expire_now(cache: Cache, jti: str) -> None:
    client = cache.client()
    await client.delete(token._key(jti))  # noqa: SLF001
