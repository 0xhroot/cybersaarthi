"""User service.

Internal building block for Phase 2 authentication. Not exposed via the public
API yet; kept here so the security primitives are exercised end to end.
"""

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
        is_active: bool = True,
    ) -> User:
        password_hash = hash_password(password)
        return await self._repository.create(
            username=username,
            email=email,
            password_hash=password_hash,
            is_active=is_active,
        )

    async def get(self, user_id: UUID) -> User | None:
        return await self._repository.get(user_id)
