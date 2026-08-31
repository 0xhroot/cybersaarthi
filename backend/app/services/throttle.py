"""Login throttling backed by the shared Redis cache.

Counters are keyed by **client IP + username** (so one attacker cannot lock a
victim's account from their own IP) plus an **independent per-IP budget** (so a
firehose of attempts across many usernames is still capped at one source).
Lockout windows grow **exponentially** with the failure count.

Redis outage behaviour is a configuration choice (``LOGIN_THROTTLE_FAIL_CLOSED``):
by default the endpoint fails open and the failure is logged (a readiness probe
already surfaces Redis health); an operator may flip the flag to block login
attempts until Redis recovers.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.db.redis import Cache

logger = logging.getLogger(__name__)

_ATTEMPTS_PREFIX = "auth:login:attempts"
_IP_PREFIX = "auth:login:ip"


def _user_ip_key(ip: str, username: str) -> str:
    return f"{_ATTEMPTS_PREFIX}:{ip}:{username.lower()}"


def _ip_key(ip: str) -> str:
    return f"{_IP_PREFIX}:{ip}"


def client_ip(request: Any) -> str:
    """Best-effort client address for throttling keys."""
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    return host or "unknown"


async def counts(cache: Cache, username: str, ip: str, settings: Settings) -> tuple[int, int]:
    """(per-user@ip, per-ip) failed-attempt counts.

    Raises nothing on a Redis error; fails open (or closed, per settings).
    """
    if settings.LOGIN_MAX_ATTEMPTS <= 0:
        return 0, 0
    try:
        client = cache.client()
        user_value = await client.get(_user_ip_key(ip, username))
        ip_value = await client.get(_ip_key(ip))
        user_count = int(user_value) if user_value is not None else 0
        ip_count = int(ip_value) if ip_value is not None else 0
        return user_count, ip_count
    except Exception:  # noqa: BLE001 - Redis outage must not crash login
        logger.warning("login-throttle read failed", exc_info=True)
        if settings.LOGIN_THROTTLE_FAIL_CLOSED:
            return settings.LOGIN_MAX_ATTEMPTS, settings.LOGIN_IP_MAX_ATTEMPTS
        return 0, 0


async def is_throttled(cache: Cache, username: str, ip: str, settings: Settings) -> bool:
    """True when either the per-user@ip or the per-ip budget is exhausted."""
    if settings.LOGIN_MAX_ATTEMPTS <= 0:
        return False
    user_count, ip_count = await counts(cache, username, ip, settings)
    return user_count >= settings.LOGIN_MAX_ATTEMPTS or ip_count >= settings.LOGIN_IP_MAX_ATTEMPTS


def _backoff_ttl(count: int, settings: Settings) -> int:
    """Exponential lockout window: base * 2^(failures-1), capped."""
    growth = 2 ** min(count - 1, 10)
    return min(settings.LOGIN_MAX_LOCKOUT_SECONDS, settings.LOGIN_LOCKOUT_SECONDS * growth)


async def record_failed_attempt(cache: Cache, username: str, ip: str, settings: Settings) -> None:
    """Increment both counters with an exponentially growing lockout window."""
    if settings.LOGIN_MAX_ATTEMPTS <= 0:
        return
    try:
        client = cache.client()
        for key in (_user_ip_key(ip, username), _ip_key(ip)):
            value = await client.incr(key)
            await client.expire(key, _backoff_ttl(int(value), settings))
    except Exception:  # noqa: BLE001 - best-effort record
        logger.warning("login-throttle write failed, failing open", exc_info=True)


async def clear_attempts(cache: Cache, username: str, ip: str) -> None:
    """Reset both counters after a successful authentication."""
    try:
        client = cache.client()
        await client.delete(_user_ip_key(ip, username))
        await client.delete(_ip_key(ip))
    except Exception:  # noqa: BLE001
        logger.warning("login-throttle clear failed, failing open", exc_info=True)
