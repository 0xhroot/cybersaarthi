"""One-shot ADMIN bootstrap CLI.

A fresh deployment has no accounts at all, so there is nothing to log in with
after first boot. Run this to create the initial administrator:

    docker compose exec backend python -m scripts.create_admin

Credentials come from ``ADMIN_USERNAME`` / ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD``
(or sensible local-development defaults). The operation is idempotent: if an
ACTIVE administrator already exists, it refuses to mint another one (preventing
accidental duplicate privileged accounts). Outside ``development``/``test`` the
settings validator already rejects placeholder secrets, so this script cannot
seed a known default password into production.
"""

from __future__ import annotations

import asyncio
import logging
import os

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.rbac import ROLE_ADMIN
from app.db.postgres import Database
from app.repositories.user_repository import UserRepository
from app.services.users import UserService

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_EMAIL = "admin@cybersaarthi.local"
DEFAULT_ADMIN_PASSWORD = "admin-dev-password"


async def ensure_admin(
    service: UserService,
    *,
    username: str,
    email: str,
    password: str,
) -> dict[str, str]:
    """Create a single ACTIVE ADMIN if none exists; describe the outcome."""
    existing = await service.get_by_username(username)
    if existing is not None:
        if "ADMIN" in await service.roles(existing.id):
            return {"username": username, "status": "existing_admin"}
        await service.set_role(existing.id, ROLE_ADMIN)
        return {"username": username, "status": "promoted"}
    # Refuse to create a second admin when one already exists.
    admins = [
        u
        for u in (await service.list_users(limit=200, offset=0, status="ACTIVE"))[0]
        if "ADMIN" in (await service.roles(u.id))
    ]
    if admins:
        return {"status": "admin_exists"}
    user = await service.create_user_with_role(
        username=username,
        email=email,
        password=password,
        role=ROLE_ADMIN,
    )
    logger.info("bootstrapped admin", extra={"username": username, "id": str(user.id)})
    return {"username": username, "status": "created"}


async def _run() -> None:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    client = Database(settings)
    factory = client.session_factory()
    try:
        async with factory() as session:
            service = UserService(UserRepository(session))
            outcome = await ensure_admin(
                service,
                username=os.environ.get("ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME),
                email=os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL),
                password=os.environ.get("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD),
            )
            await session.commit()
        status = outcome["status"]
        if status == "created":
            print(
                f"created ADMIN user: {outcome['username']} / "
                f"{os.environ.get('ADMIN_PASSWORD', DEFAULT_ADMIN_PASSWORD)}"
            )
        elif status == "promoted":
            print(f"promoted existing user {outcome['username']} to ADMIN")
        elif status == "existing_admin":
            print(f"ADMIN user {outcome['username']} already exists; nothing to do")
        else:
            print("an ACTIVE administrator already exists; refusing to create another")
    finally:
        await client.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
