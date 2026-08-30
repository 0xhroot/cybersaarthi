"""User service: account lifecycle and role management."""

from __future__ import annotations

from uuid import UUID

from app.core.security import hash_password
from app.models import User
from app.repositories.user_repository import UserRepository


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    async def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        hashed: bool = False,
        is_active: bool = True,
    ) -> User:
        password_hash = password if hashed else hash_password(password)
        return await self._repository.create(
            username=username,
            email=email,
            password_hash=password_hash,
            is_active=is_active,
        )

    async def create_user_with_role(
        self,
        *,
        username: str,
        email: str,
        password: str,
        role: str,
    ) -> User:
        """Create a user and assign a single initial role."""
        user = await self.create_user(username=username, email=email, password=password)
        await self.set_role(user.id, role)
        return user

    async def set_role(self, user_id: UUID, role: str) -> None:
        role_row = await self._repository.get_role(role)
        if role_row is None:
            raise ValueError(f"role {role} is not defined")
        await self._repository.assign_role(user_id, role_row.id)

    async def roles(self, user_id: UUID) -> list[str]:
        return await self._repository.roles_for_user(user_id)

    async def permissions(self, user_id: UUID) -> list[str]:
        from app.core.rbac import ROLE_PERMISSIONS

        roles = await self.roles(user_id)
        perms = {permission for role in roles for permission in ROLE_PERMISSIONS.get(role, ())}
        return sorted(perms)

    async def get(self, user_id: UUID) -> User | None:
        return await self._repository.get(user_id)

    async def get_by_username(self, username: str) -> User | None:
        return await self._repository.get_by_username(username)

    async def get_by_email(self, email: str) -> User | None:
        return await self._repository.get_by_email(email)

    async def username_exists(self, username: str) -> bool:
        return await self.get_by_username(username) is not None

    async def email_exists(self, email: str) -> bool:
        return await self.get_by_email(email) is not None
