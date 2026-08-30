"""Login throttling backed by the shared Redis cache.

A per-username failure counter limits brute-force attempts on the public
``/auth/login`` endpoint. The window is refreshed on the first failure and the
counter is cleared after a successful authentication. All operations fail open:
if Redis is unavailable the login proceeds (a readiness probe already surfaces
Redis health) and the outcome is logged instead of disrupting authentication.
"""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.db.redis import Cache

logger = logging.getLogger(__name__)

_ATTEMPTS_PREFIX = "auth:login:attempts"


def _key(username: str) -> str:
    return f"{_ATTEMPTS_PREFIX}:{username.lower()}"


async def attempts(cache: Cache, username: str, settings: Settings) -> int:
    """Current failed-attempt count for *username*."""
    if settings.LOGIN_MAX_ATTEMPTS <= 0:
        return 0
    try:
        value = await cache.client().get(_key(username))
        if value is None:
            return 0
        return int(value)
    except Exception:  # noqa: BLE001 - Redis outage must not block login
        logger.warning("login-throttle read failed, failing open", exc_info=True)
        return 0


async def record_failed_attempt(cache: Cache, username: str, settings: Settings) -> None:
    """Increment the failure counter, applying TTL on the first hit."""
    if settings.LOGIN_MAX_ATTEMPTS <= 0:
        return
    try:
        key = _key(username)
        client = cache.client()
        value = await client.incr(key)
        if value == 1:
            await client.expire(key, settings.LOGIN_LOCKOUT_SECONDS)
    except Exception:  # noqa: BLE001
        logger.warning("login-throttle write failed, failing open", exc_info=True)


async def clear_attempts(cache: Cache, username: str) -> None:
    """Reset the failure counter (successful authentication)."""
    try:
        await cache.client().delete(_key(username))
    except Exception:  # noqa: BLE001
        logger.warning("login-throttle clear failed, failing open", exc_info=True)
