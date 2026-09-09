"""Idempotent seeding of the default local accounts.

Creates the ``admin`` (full control) and ``investigator`` (end-to-end)
accounts referenced by the README, the E2E workflow and the Phase 4 docs.
Passwords default to local-development values and can be overridden with
``SEED_ADMIN_PASSWORD`` / ``SEED_INVESTIGATOR_PASSWORD``. The production
settings validator refuses placeholder secrets, so this script is safe only
for non-production environments.
"""

from __future__ import annotations

import asyncio
import logging
import os

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.postgres import Database
from app.repositories.user_repository import UserRepository
from app.services.users import UserService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin-dev-password"
DEFAULT_INVESTIGATOR_USERNAME = "investigator"
DEFAULT_INVESTIGATOR_PASSWORD = "investigator-dev-password"


async def ensure_seed_users(
    session: AsyncSession,
    *,
    admin_password: str | None = None,
    investigator_password: str | None = None,
) -> list[dict[str, str]]:
    """Create the default accounts if absent; describes the users created."""
    service = UserService(UserRepository(session))
    created: list[dict[str, str]] = []

    admin_password = admin_password or os.environ.get("SEED_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
    investigator_password = investigator_password or os.environ.get(
        "SEED_INVESTIGATOR_PASSWORD", DEFAULT_INVESTIGATOR_PASSWORD
    )

    await _ensure_user(
        service,
        created,
        DEFAULT_ADMIN_USERNAME,
        "admin@cybersaarthi.local",
        admin_password,
        "ADMIN",
    )
    await _ensure_user(
        service,
        created,
        DEFAULT_INVESTIGATOR_USERNAME,
        "investigator@cybersaarthi.local",
        investigator_password,
        "INVESTIGATOR",
    )
    return created


async def _ensure_user(
    service: UserService,
    created: list[dict[str, str]],
    username: str,
    email: str,
    password: str,
    role: str,
) -> None:
    existing = await service.get_by_username(username)
    if existing is not None:
        return
    user = await service.create_user_with_role(
        username=username,
        email=email,
        password=password,
        role=role,
    )
    created.append({"username": username, "password": password, "role": role})
    logger.info("seeded user", extra={"username": username, "role": role, "id": str(user.id)})


def main() -> None:
    asyncio.run(_run())


async def _run() -> None:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    client = Database(settings)
    factory = client.session_factory()
    try:
        async with factory() as session:
            created = await ensure_seed_users(session)
            await session.commit()
            for row in created:
                print(f"created {row['role']} user: {row['username']} / {row['password']}")
            if not created:
                print("seed users already present; nothing to do")
    finally:
        await client.close()


if __name__ == "__main__":
    main()
