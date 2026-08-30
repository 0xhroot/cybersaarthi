"""Data access for users and their role assignments."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, User, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        username: str,
        email: str,
        password_hash: str,
        is_active: bool = True,
    ) -> User:
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            is_active=is_active,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def get_role(self, name: str) -> Role | None:
        result = await self._session.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    async def assign_role(self, user_id: uuid.UUID, role_id: uuid.UUID) -> None:
        existing = await self._session.execute(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
        self._session.add(UserRole(user_id=user_id, role_id=role_id))
        await self._session.flush()

    async def roles_for_user(self, user_id: uuid.UUID) -> list[str]:
        result = await self._session.execute(
            select(Role.name)
            .select_from(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
            .order_by(Role.name)
        )
        return list(result.scalars())
