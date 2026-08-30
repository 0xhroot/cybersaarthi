"""Request/response schemas for case management."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

CaseStatus = Literal["open", "in_progress", "closed"]


class CaseCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    case_number: str | None = Field(default=None, min_length=3, max_length=32)
    status: CaseStatus = "open"


class CaseUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    status: CaseStatus | None = None


class CaseOut(BaseModel):
    id: UUID
    case_number: str
    title: str
    description: str | None
    status: str
    owner_id: UUID | None
    created_at: datetime
    updated_at: datetime


class CaseListResponse(BaseModel):
    items: list[CaseOut]
    total: int
    limit: int
    offset: int
