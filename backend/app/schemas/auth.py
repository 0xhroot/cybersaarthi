"""Request/response schemas for authentication and user management."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.rbac import ALL_ROLES

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 12


class RegisterRequest(BaseModel):
    """Create a user with an initial role (ADMIN-only endpoint)."""

    username: str = Field(min_length=3, max_length=64)
    email: str = Field(max_length=320)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    role: str = "VIEWER"

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not _USERNAME_RE.fullmatch(value):
            raise ValueError(
                "username must be 3-64 characters using letters, digits, '.', '_' or '-'"
            )
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not _EMAIL_RE.fullmatch(value):
            raise ValueError("email must be a valid address")
        return value.lower()

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in ALL_ROLES:
            raise ValueError(f"role must be one of {', '.join(ALL_ROLES)}")
        return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: UUID
    username: str
    email: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class MeResponse(BaseModel):
    user: UserOut
    roles: list[str]
    permissions: list[str]


class RoleOut(BaseModel):
    id: UUID
    name: str
    description: str | None


class RegisteredUserOut(BaseModel):
    user: UserOut
    roles: list[str]
    created_at: datetime
