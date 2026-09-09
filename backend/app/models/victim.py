"""Victim - a person harmed in a cyber fraud case.

The victim model captures incident-specific information relevant to a cyber
fraud investigation: identity, incident details, financial impact, digital
footprint, communication records and recovery status.  It is intentionally
distinct from the generic Entity model (used for resolved NER entities) — a
victim is an investigation-specific role that carries structured financial and
incident metadata that an Entity row does not.

PostgreSQL is the system of record. Victims are intentionally kept out of the
Neo4j analytics projection (which models resolved NER entities and their
relationships): they are served by their own case-scoped API, pages and audit
trail, and a bounded summary can be projected later without disturbing the
analytics entity/relationship shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

VICTIM_STATUSES = (
    "reported",
    "under_investigation",
    "evidence_collected",
    "recovery_initiated",
    "recovered",
    "closed",
)

VICTIM_CLASSIFICATIONS = (
    "individual",
    "organization",
    "government",
    "financial_institution",
    "unknown",
)


class Victim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "victims"
    __table_args__ = (
        CheckConstraint(
            "status IN ('reported', 'under_investigation', 'evidence_collected', "
            "'recovery_initiated', 'recovered', 'closed')",
            name="victim_status_valid",
        ),
        CheckConstraint(
            "classification IN ('individual', 'organization', 'government', "
            "'financial_institution', 'unknown')",
            name="victim_classification_valid",
        ),
        Index("ix_victims_case_id", "case_id"),
        Index("ix_victims_status", "status"),
        Index("ix_victims_case_status", "case_id", "status"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )

    # --- Basic identity ---
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    age: Mapped[int | None] = mapped_column(nullable=True)
    date_of_birth: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(32), nullable=True)
    classification: Mapped[str] = mapped_column(
        String(32),
        default="individual",
        nullable=False,
    )

    # --- Contact information ---
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Incident information ---
    incident_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    incident_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fraud_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Financial impact ---
    reported_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    amount_lost: Mapped[float | None] = mapped_column(Float, nullable=True)
    recovery_amount: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Digital footprint ---
    digital_accounts: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)
    devices: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)
    wallet_addresses: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    # --- Investigation ---
    status: Mapped[str] = mapped_column(
        String(32),
        default="reported",
        nullable=False,
    )
    statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    investigator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- Audit / Provenance ---
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Victim id={self.id} name={self.name!r} status={self.status!r}>"
