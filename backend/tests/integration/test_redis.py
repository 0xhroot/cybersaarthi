"""Integration tests for Redis connectivity."""

from __future__ import annotations

import uuid

from app.db.redis import Cache


async def test_redis_connectivity(cache: Cache) -> None:
    await cache.ping()


async def test_redis_set_get_delete(cache: Cache) -> None:
    key = f"test:{uuid.uuid4().hex}"
    client = cache.client()
    await client.set(key, "phase-1")
    try:
        assert await client.get(key) == "phase-1"
        assert await client.ttl(key) > -2
    finally:
        await client.delete(key)
