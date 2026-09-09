"""Entity - a resolved entity (person, phone, vehicle, organisation, ...) per case."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

ENTITY_TYPES = (
    "person",
    "phone",
    "vehicle",
    "organization",
    "account",
    "location",
    "document",
    "event",
)


class Entity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "entities"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('person', 'phone', 'vehicle', 'organization', "
            "'account', 'location', 'document', 'event')",
            name="entity_type_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'merged', 'review', 'rejected')",
            name="entity_status_valid",
        ),
        UniqueConstraint(
            "case_id", "entity_type", "canonical_value", name="uq_entities_case_type_value"
        ),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    canonical_value: Mapped[str] = mapped_column(String(512), nullable=False)
    blocking_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    display_value: Mapped[str] = mapped_column(String(512), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    context: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<Entity id={self.id} type={self.entity_type!r} value={self.display_value!r}>"
