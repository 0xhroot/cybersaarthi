"""Unit tests for the Redis-backed login throttling.

A06 coverage: counters are keyed by IP + username, there is an independent
per-IP budget, lockout windows grow exponentially, and the endpoint fails open
(or closed, when configured) if Redis is unavailable.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.config import Settings
from app.db.redis import Cache
from app.services import throttle

USERNAME = f"throttle-{uuid.uuid4().hex[:10]}"
IP = "203.0.113.7"


class _BrokenCache:
    """A cache whose client raises: throttling must fail open (or closed)."""

    def client(self):  # noqa: D102
        raise RuntimeError("redis down")


@pytest.fixture(autouse=True)
async def _use_isolated_keys(cache: Cache) -> None:
    """Ensure the counter keys are fresh for each run of this module."""
    yield
    try:
        client = cache.client()
        await client.delete(throttle._user_ip_key(IP, USERNAME))  # noqa: SLF001
        await client.delete(throttle._ip_key(IP))  # noqa: SLF001
    except Exception:  # noqa: BLE001,S110 - best-effort key cleanup
        pass


async def test_unknown_username_has_zero_attempts(cache: Cache, settings: Settings) -> None:
    user_count, ip_count = await throttle.counts(cache, USERNAME, IP, settings)
    assert user_count == 0
    assert ip_count == 0


async def test_failure_counter_round_trip(cache: Cache, settings: Settings) -> None:
    for _ in range(3):
        await throttle.record_failed_attempt(cache, USERNAME, IP, settings)
    user_count, ip_count = await throttle.counts(cache, USERNAME, IP, settings)
    assert user_count == 3
    assert ip_count == 3
    assert await throttle.is_throttled(cache, USERNAME, IP, settings) is False
    await throttle.clear_attempts(cache, USERNAME, IP)
    assert await throttle.counts(cache, USERNAME, IP, settings) == (0, 0)


async def test_attempts_are_keyed_by_ip_plus_username(cache: Cache, settings: Settings) -> None:
    """A06: failures from one IP must not lock the same username at another IP."""
    await throttle.record_failed_attempt(cache, USERNAME, "198.51.100.1", settings)
    await throttle.record_failed_attempt(cache, USERNAME, "198.51.100.1", settings)
    await throttle.record_failed_attempt(cache, USERNAME, "198.51.100.1", settings)
    await throttle.record_failed_attempt(cache, USERNAME, "198.51.100.1", settings)
    await throttle.record_failed_attempt(cache, USERNAME, "198.51.100.1", settings)
    assert await throttle.is_throttled(cache, USERNAME, "198.51.100.1", settings) is True
    assert await throttle.is_throttled(cache, USERNAME, IP, settings) is False
    await throttle.clear_attempts(cache, USERNAME, "198.51.100.1")


async def test_per_ip_budget_is_independent_of_username(cache: Cache, settings: Settings) -> None:
    """A06: a firehose against many usernames is capped by the per-IP budget."""
    saved_ip, saved_user = settings.LOGIN_IP_MAX_ATTEMPTS, settings.LOGIN_MAX_ATTEMPTS
    settings.LOGIN_IP_MAX_ATTEMPTS = 3
    settings.LOGIN_MAX_ATTEMPTS = 100
    try:
        for index in range(3):
            await throttle.record_failed_attempt(cache, f"victim-{index}", IP, settings)
        assert await throttle.is_throttled(cache, "fresh-user", IP, settings) is True
    finally:
        settings.LOGIN_IP_MAX_ATTEMPTS = saved_ip
        settings.LOGIN_MAX_ATTEMPTS = saved_user


async def test_lockout_window_grows_exponentially(cache: Cache, settings: Settings) -> None:
    """A06: the TTL doubles with each additional failure, capped at the max."""
    saved_max = settings.LOGIN_MAX_LOCKOUT_SECONDS
    settings.LOGIN_MAX_LOCKOUT_SECONDS = 20_000
    try:
        client = cache.client()
        for count in range(1, 5):
            await throttle.record_failed_attempt(cache, USERNAME, IP, settings)
            remaining = await client.ttl(throttle._user_ip_key(IP, USERNAME))  # noqa: SLF001
            assert remaining >= settings.LOGIN_LOCKOUT_SECONDS * (2 ** (count - 1))
    finally:
        settings.LOGIN_MAX_LOCKOUT_SECONDS = saved_max


async def test_lockout_window_is_capped(cache: Cache, settings: Settings) -> None:
    client = cache.client()
    for _ in range(15):
        await throttle.record_failed_attempt(cache, USERNAME, IP, settings)
    remaining = await client.ttl(throttle._user_ip_key(IP, USERNAME))  # noqa: SLF001
    assert remaining <= settings.LOGIN_MAX_LOCKOUT_SECONDS


async def test_disabled_throttling_is_a_permanent_pass(cache: Cache, settings: Settings) -> None:
    settings.LOGIN_MAX_ATTEMPTS = 0
    try:
        await throttle.record_failed_attempt(cache, USERNAME, IP, settings)
        assert await throttle.counts(cache, USERNAME, IP, settings) == (0, 0)
        assert await throttle.is_throttled(cache, USERNAME, IP, settings) is False
    finally:
        settings.LOGIN_MAX_ATTEMPTS = 5


async def test_fail_open_when_redis_is_unavailable(settings: Settings) -> None:
    broken = _BrokenCache()
    assert await throttle.counts(broken, USERNAME, IP, settings) == (0, 0)
    assert await throttle.is_throttled(broken, USERNAME, IP, settings) is False
    await throttle.record_failed_attempt(broken, USERNAME, IP, settings)  # must not raise
    await throttle.clear_attempts(broken, USERNAME, IP)  # must not raise


async def test_fail_closed_when_redis_is_unavailable(settings: Settings) -> None:
    """A06: operators may opt into blocking logins while Redis is down."""
    saved = settings.LOGIN_THROTTLE_FAIL_CLOSED
    settings.LOGIN_THROTTLE_FAIL_CLOSED = True
    try:
        broken = _BrokenCache()
        user_count, ip_count = await throttle.counts(broken, USERNAME, IP, settings)
        assert user_count >= settings.LOGIN_MAX_ATTEMPTS
        assert ip_count >= settings.LOGIN_IP_MAX_ATTEMPTS
        assert await throttle.is_throttled(broken, USERNAME, IP, settings) is True
    finally:
        settings.LOGIN_THROTTLE_FAIL_CLOSED = saved


async def test_attempts_are_case_insensitive(cache: Cache, settings: Settings) -> None:
    await throttle.record_failed_attempt(cache, USERNAME.upper(), IP, settings)
    user_count, _ = await throttle.counts(cache, USERNAME.lower(), IP, settings)
    assert user_count == 1
