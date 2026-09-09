"""Request/response schemas for victim management."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

VictimStatus = Literal[
    "reported",
    "under_investigation",
    "evidence_collected",
    "recovery_initiated",
    "recovered",
    "closed",
]

VictimClassification = Literal[
    "individual",
    "organization",
    "government",
    "financial_institution",
    "unknown",
]


class VictimCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    age: int | None = Field(default=None, ge=0, le=200)
    date_of_birth: datetime | None = None
    gender: str | None = Field(default=None, max_length=32)
    classification: VictimClassification = "individual"
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=320)
    address: str | None = Field(default=None, max_length=5000)
    incident_date: datetime | None = None
    incident_type: str | None = Field(default=None, max_length=128)
    fraud_category: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=10000)
    reported_amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=16)
    amount_lost: float | None = Field(default=None, ge=0)
    recovery_amount: float | None = Field(default=None, ge=0)
    digital_accounts: list[dict[str, object]] | None = None
    devices: list[dict[str, object]] | None = None
    wallet_addresses: list[str] | None = None
    status: VictimStatus = "reported"
    statement: str | None = Field(default=None, max_length=20000)
    investigator_notes: str | None = Field(default=None, max_length=20000)
    recovery_status: str | None = Field(default=None, max_length=64)


class VictimUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    age: int | None = Field(default=None, ge=0, le=200)
    date_of_birth: datetime | None = None
    gender: str | None = Field(default=None, max_length=32)
    classification: VictimClassification | None = None
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=320)
    address: str | None = Field(default=None, max_length=5000)
    incident_date: datetime | None = None
    incident_type: str | None = Field(default=None, max_length=128)
    fraud_category: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=10000)
    reported_amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=16)
    amount_lost: float | None = Field(default=None, ge=0)
    recovery_amount: float | None = Field(default=None, ge=0)
    digital_accounts: list[dict[str, object]] | None = None
    devices: list[dict[str, object]] | None = None
    wallet_addresses: list[str] | None = None
    status: VictimStatus | None = None
    statement: str | None = Field(default=None, max_length=20000)
    investigator_notes: str | None = Field(default=None, max_length=20000)
    recovery_status: str | None = Field(default=None, max_length=64)


class VictimOut(BaseModel):
    id: UUID
    case_id: UUID
    name: str
    age: int | None
    date_of_birth: datetime | None
    gender: str | None
    classification: str
    phone: str | None
    email: str | None
    address: str | None
    incident_date: datetime | None
    incident_type: str | None
    fraud_category: str | None
    description: str | None
    reported_amount: float | None
    currency: str | None
    amount_lost: float | None
    recovery_amount: float | None
    digital_accounts: list[dict[str, object]] | None
    devices: list[dict[str, object]] | None
    wallet_addresses: list[str] | None
    status: str
    statement: str | None
    investigator_notes: str | None
    recovery_status: str | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class VictimListResponse(BaseModel):
    items: list[VictimOut]
    total: int
    limit: int
    offset: int
