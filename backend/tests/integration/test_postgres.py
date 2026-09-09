"""Integration tests for PostgreSQL connectivity and the user data flow."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import verify_password
from app.db.postgres import Database
from app.models import User
from app.repositories.user_repository import UserRepository
from app.services.users import UserService
from sqlalchemy.exc import IntegrityError


async def test_postgres_connectivity(database: Database) -> None:
    await database.ping()


async def test_user_create_and_read_flow(database: Database) -> None:
    password = "int-test-password"
    suffix = uuid.uuid4().hex[:10]
    username = f"int_{suffix}"
    email = f"{suffix}@example.com"

    factory = database.session_factory()
    async with factory() as session:
        repository = UserRepository(session)
        service = UserService(repository)

        user = await service.create_user(
            username=username,
            email=email,
            password=password,
        )

        try:
            assert user.username == username
            assert user.email == email
            assert user.password_hash != password
            assert verify_password(password, user.password_hash)

            fetched = await repository.get_by_username(username)
            assert fetched is not None
            assert fetched.id == user.id

            by_email = await repository.get_by_email(email)
            assert by_email is not None
            assert by_email.id == user.id
        finally:
            await session.delete(user)
            await session.commit()


async def test_unique_constraint_enforced(database: Database) -> None:
    factory = database.session_factory()
    async with factory() as session:
        suffix = uuid.uuid4().hex[:10]
        password_hash = "hashed-placeholder"

        user = User(
            username=f"dup_{suffix}",
            email=f"dup_{suffix}@example.com",
            password_hash=password_hash,
        )
        session.add(user)
        await session.commit()

        duplicate = User(
            username=f"dup_{suffix}",
            email=f"other_{suffix}@example.com",
            password_hash=password_hash,
        )
        session.add(duplicate)
        try:
            await session.commit()
            pytest.fail("expected IntegrityError for duplicate username")
        except IntegrityError:
            await session.rollback()
        finally:
            await session.delete(user)
            await session.commit()
