"""Data access for users and their role assignments."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AccountStatus
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

    async def list_users(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[User], int]:
        """Page over users; ``status`` and ``search`` (username/email) filter."""
        base = select(User)
        if status:
            base = base.where(User.status == status)
        if search:
            escaped = (
                search.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            base = base.where(
                func.lower(User.username).like(pattern, escape="\\")
                | func.lower(User.email).like(pattern, escape="\\")
            )
        total = await self._session.execute(base.with_only_columns(func.count(User.id)))
        count = total.scalar_one()
        result = await self._session.execute(
            base.order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars()), count

    async def list_status(self, status: str) -> list[User]:
        result = await self._session.execute(
            select(User).where(User.status == status).order_by(User.created_at.asc())
        )
        return list(result.scalars())

    async def count_status(self, status: str) -> int:
        result = await self._session.execute(
            select(func.count(User.id)).where(User.status == status)
        )
        return result.scalar_one()

    async def count_admins(self) -> int:
        result = await self._session.execute(
            select(func.count(UserRole.user_id))
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.name == "ADMIN", User.status == AccountStatus.ACTIVE.value)
        )
        return result.scalar_one()

    async def create(
        self,
        *,
        username: str,
        email: str,
        password_hash: str,
        status: str,
    ) -> User:
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            status=status,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_status(self, user_id: uuid.UUID, status: str) -> User | None:
        user = await self.get(user_id)
        if user is None:
            return None
        user.status = status
        await self._session.flush()
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

    async def replace_roles(self, user_id: uuid.UUID, role: str) -> None:
        """Set a user's single active role, removing any others atomically."""
        role_row = await self.get_role(role)
        if role_row is None:
            raise ValueError(f"role {role} is not defined")
        result = await self._session.execute(select(UserRole).where(UserRole.user_id == user_id))
        for assignment in result.scalars():
            await self._session.delete(assignment)
        self._session.add(UserRole(user_id=user_id, role_id=role_row.id))
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
