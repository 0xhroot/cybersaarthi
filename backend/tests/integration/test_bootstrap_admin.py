"""Bootstrap admin lifecycle.

Verifies ``scripts.create_admin.ensure_admin`` against a real database. The
deployed dev database already contains the seeded ``admin`` account, so the
"create first admin" branch is not reachable here; the tests assert the
deterministic branches that hold in that state:

* a fresh username is refused (``admin_exists``) because an ADMIN already exists;
* re-running on an existing ADMIN username is idempotent (``existing_admin``);
* a non-admin user whose username collides is promoted to ADMIN (``promoted``).

Each case cleans up the users it introduces so the store stays tidy.
"""

from __future__ import annotations

import uuid

from app.core.rbac import ROLE_ADMIN
from app.db.postgres import Database
from app.models import User
from app.repositories.user_repository import UserRepository
from app.services.users import UserService
from scripts.create_admin import ensure_admin
from sqlalchemy import delete


async def _delete_user(database: Database, username: str) -> None:
    factory = database.session_factory()
    async with factory() as session:
        await session.execute(delete(User).where(User.username == username))
        await session.commit()


async def _make_service(
    database: Database,
) -> tuple[UserService, object]:
    factory = database.session_factory()
    session = factory()
    return UserService(UserRepository(session)), session


async def _seed_pending(
    database: Database,
    suffix: str,
) -> tuple[UserService, object, str]:
    """Create a PENDING user and a service bound to an open session."""
    service, session = await _make_service(database)
    username = f"boot-promote-{suffix}"
    user = await service.register_pending(
        username=username,
        email=f"{username}@cybersaarthi.test",
        password="barely-secret-bootstrap!",
    )
    return service, session, user.username


async def test_bootstrap_is_idempotent_for_existing_admin(database: Database) -> None:
    service, session = await _make_service(database)
    username = "admin"
    outcome = await ensure_admin(
        service,
        username=username,
        email="admin@cybersaarthi.local",
        password="barely-secret-bootstrap!",
    )
    assert outcome["status"] in {"existing_admin", "promoted"}
    user = await service.get_by_username(username)
    assert user is not None and ROLE_ADMIN in await service.roles(user.id)
    await session.close()


async def test_bootstrap_refuses_second_admin(database: Database) -> None:
    service, session = await _make_service(database)
    username = f"boot-new-{uuid.uuid4().hex[:8]}"
    try:
        outcome = await ensure_admin(
            service,
            username=username,
            email=f"{username}@cybersaarthi.test",
            password="barely-secret-bootstrap!",
        )
        assert outcome["status"] == "admin_exists"
        user = await service.get_by_username(username)
        assert user is None or ROLE_ADMIN not in await service.roles(user.id)
    finally:
        await session.close()
        await _delete_user(database, username)


async def test_bootstrap_promotes_existing_non_admin(database: Database) -> None:
    service, session, username = await _seed_pending(database, uuid.uuid4().hex[:8])
    try:
        outcome = await ensure_admin(
            service,
            username=username,
            email=f"{username}@cybersaarthi.test",
            password="barely-secret-bootstrap!",
        )
        assert outcome["status"] == "promoted"
        user = await service.get_by_username(username)
        assert user is not None and ROLE_ADMIN in await service.roles(user.id)
    finally:
        await session.close()
        await _delete_user(database, username)
