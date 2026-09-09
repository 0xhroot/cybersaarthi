"""Request/response schemas for authentication and user management."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.enums import AccountStatus

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 12


class RegisterRequest(BaseModel):
    """Self-registration. Creates a PENDING account; no role is granted."""

    username: str = Field(min_length=3, max_length=64)
    email: str = Field(max_length=320)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)

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


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: UUID
    username: str
    email: str
    status: str
    is_active: bool

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in tuple(status.value for status in AccountStatus):
            raise ValueError("unknown account status")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class MeResponse(BaseModel):
    user: UserOut
    roles: list[str]
    permissions: list[str]


class RegisteredUserOut(BaseModel):
    user: UserOut
    roles: list[str] = []
    created_at: datetime


class RoleOut(BaseModel):
    id: UUID
    name: str
    description: str | None


class AdminUserOut(BaseModel):
    """User row surfaced to administrators (no secrets, no password hashes)."""

    id: UUID
    username: str
    email: str
    status: str
    roles: list[str]
    created_at: datetime
    updated_at: datetime


class AdminUserList(BaseModel):
    items: list[AdminUserOut]
    total: int
    limit: int
    offset: int


class ApproveRequest(BaseModel):
    """Role to grant when approving a PENDING account (admin decision)."""

    role: str = Field(min_length=2, max_length=32)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        from app.core.rbac import ALL_ROLES, is_valid_role

        if not is_valid_role(value):
            raise ValueError(f"role must be one of {', '.join(ALL_ROLES)}")
        return value


class RoleChangeRequest(BaseModel):
    role: str = Field(min_length=2, max_length=32)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        from app.core.rbac import ALL_ROLES, is_valid_role

        if not is_valid_role(value):
            raise ValueError(f"role must be one of {', '.join(ALL_ROLES)}")
        return value
