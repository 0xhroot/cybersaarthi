"""Async SQLAlchemy engine and session factory for PostgreSQL."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.core.config import Settings
from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    """Lazily-created async engine bound to the application settings."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None

    def engine(self) -> AsyncEngine:
        if self._engine is None:
            # NB: psycopg (async) performs its own connection-validity checks;
            # ``pool_pre_ping`` attempts a ping outside the greenlet context and
            # intermittently raises ``MissingGreenlet`` when a pooled connection
            # is reused, so it must be left disabled for this driver.
            self._engine = create_async_engine(self._settings.postgres_dsn)
        return self._engine

    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(self.engine(), expire_on_commit=False)

    async def ping(self) -> None:
        """Raise if PostgreSQL is unreachable; used by the readiness check."""
        async with self.engine().connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None


def get_database(request: Request) -> Database:
    return request.app.state.database


async def get_db_session(
    database: Database = Depends(get_database),
) -> AsyncIterator[AsyncSession]:
    factory = database.session_factory()
    async with factory() as session:
        yield session
