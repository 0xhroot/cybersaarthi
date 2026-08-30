"""Unit tests for the Redis-backed login throttling (fail-open by design)."""

from __future__ import annotations

import uuid

import pytest
from app.core.config import Settings
from app.db.redis import Cache
from app.services import throttle

USERNAME = f"throttle-{uuid.uuid4().hex[:10]}"


class _BrokenCache:
    """A cache whose client raises: throttling must fail open."""

    def client(self):  # noqa: D102
        raise RuntimeError("redis down")


@pytest.fixture(autouse=True)
async def _use_isolated_key(cache: Cache) -> None:
    """Ensure the counter key is fresh for each run of this module."""
    yield
    try:
        await cache.client().delete(throttle._key(USERNAME))  # noqa: SLF001
    except Exception:  # noqa: BLE001,S110 - best-effort key cleanup
        pass


async def test_unknown_username_has_zero_attempts(cache: Cache, settings: Settings) -> None:
    assert await throttle.attempts(cache, USERNAME, settings) == 0


async def test_failure_counter_round_trip(cache: Cache, settings: Settings) -> None:
    for _ in range(3):
        await throttle.record_failed_attempt(cache, USERNAME, settings)
    assert await throttle.attempts(cache, USERNAME, settings) == 3
    await throttle.clear_attempts(cache, USERNAME)
    assert await throttle.attempts(cache, USERNAME, settings) == 0


async def test_disabled_throttling_is_a_permanent_pass(cache: Cache, settings: Settings) -> None:
    settings.LOGIN_MAX_ATTEMPTS = 0
    try:
        await throttle.record_failed_attempt(cache, USERNAME, settings)
        # Disabled mode: the counter must stay at zero even after attempts().
        assert await throttle.attempts(cache, USERNAME, settings) == 0
    finally:
        settings.LOGIN_MAX_ATTEMPTS = 5


async def test_fail_open_when_redis_is_unavailable(settings: Settings) -> None:
    broken = _BrokenCache()
    assert await throttle.attempts(broken, USERNAME, settings) == 0
    await throttle.record_failed_attempt(broken, USERNAME, settings)  # must not raise
    await throttle.clear_attempts(broken, USERNAME)  # must not raise


async def test_attempts_is_case_insensitive(cache: Cache, settings: Settings) -> None:
    await throttle.record_failed_attempt(cache, USERNAME.upper(), settings)
    assert await throttle.attempts(cache, USERNAME.lower(), settings) == 1
