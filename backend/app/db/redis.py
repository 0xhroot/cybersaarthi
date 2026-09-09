"""Redis async client wrapper.

Phase 1 only establishes the connection and a readiness probe. Caching and the
background-job layer build on this in later phases.
"""

from __future__ import annotations

from app.core.config import Settings
from redis.asyncio import Redis


class Cache:
    """Lazily-created async Redis client."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Redis | None = None

    def client(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(
                self._settings.REDIS_URL,
                decode_responses=True,
            )
        return self._client

    async def ping(self) -> None:
        """Raise if Redis is unreachable; used by the readiness check."""
        await self.client().ping()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
