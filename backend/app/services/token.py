"""Optional server-side access-token revocation (Redis-backed denylist).

Tokens are stateless HMAC-signed bearer tokens carrying a unique ``jti``
(see :mod:`app.core.auth`). By default they live for the full
``ACCESS_TOKEN_EXPIRE_MINUTES`` window with no way to invalidate a leaked one.
When ``TOKEN_REVOCATION_ENABLED`` is true, a revoked ``jti`` is written to Redis
(as a set with a TTL matching the token lifetime) and every authenticated
request checks it, so a logout or an admin revoke takes effect immediately.

Redis outage behaviour: if revocation is enabled but Redis is unreachable the
check fails **closed** for reads (an unreachable denylist must not trust a
token) and **open** for writes (a logout cannot wedge the service permanently).
"""

from __future__ import annotations

import logging

from app.core.auth import decode_access_token_claims
from app.db.redis import Cache

logger = logging.getLogger(__name__)

_PREFIX = "auth:jti:revoked"


def _key(jti: str) -> str:
    return f"{_PREFIX}:{jti}"


def token_jti(token: str, secret: str) -> str | None:
    """Return the validated token's ``jti``, or ``None`` if invalid/absent."""
    claims = decode_access_token_claims(token, secret=secret)
    if not claims:
        return None
    jti = claims.get("jti")
    return jti if isinstance(jti, str) and jti else None


async def revoke_token(cache: Cache, jti: str, ttl_seconds: int) -> None:
    """Mark a token id revoked for ``ttl_seconds``. Best-effort (fail open)."""
    try:
        await cache.client().set(_key(jti), "1", ex=ttl_seconds)
    except Exception:  # noqa: BLE001 - logout must not crash the request
        logger.warning("token-revocation write failed, failing open", exc_info=True)


async def is_revoked(cache: Cache, jti: str | None) -> bool:
    """True if *jti* is revoke-listed. Fails closed on a Redis error."""
    if not jti:
        return False
    try:
        return bool(await cache.client().exists(_key(jti)))
    except Exception:  # noqa: BLE001 - never trust a token when the denylist is down
        logger.warning("token-revocation read failed, failing closed", exc_info=True)
        return True
