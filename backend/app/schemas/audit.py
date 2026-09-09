"""Response schemas for the audit log."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: UUID
    actor_id: UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    case_id: UUID | None
    metadata_: dict[str, Any] | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogOut]
    total: int
    limit: int
    offset: int
