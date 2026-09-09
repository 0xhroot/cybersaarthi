"""Neo4j driver wrapper.

Phase 1 only establishes the connection and a readiness probe. Knowledge-graph
building (persons, phones, organisations, relationships) arrives in Phase 2.
"""

from __future__ import annotations

from app.core.config import Settings
from neo4j import AsyncDriver, AsyncGraphDatabase


class GraphStore:
    """Lazily-created async Neo4j driver."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._driver: AsyncDriver | None = None

    def driver(self) -> AsyncDriver:
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                self._settings.NEO4J_URI,
                auth=(self._settings.NEO4J_USER, self._settings.NEO4J_PASSWORD),
            )
        return self._driver

    async def ping(self) -> None:
        """Execute a trivial query; raises if Neo4j is unreachable."""
        driver = self.driver()
        async with driver.session() as session:
            await session.run("RETURN 1")

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
