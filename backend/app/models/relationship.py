"""Relationship - a typed edge between two resolved entities of a case."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

RELATIONSHIP_TYPES = (
    "called",
    "owns",
    "works_for",
    "associated_with",
    "located_at",
    "visited",
    "transferred_to",
)


class Relationship(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "relationships"
    __table_args__ = (
        CheckConstraint(
            "relationship_type IN ('called', 'owns', 'works_for', 'associated_with', "
            "'located_at', 'visited', 'transferred_to')",
            name="relationship_type_valid",
        ),
        UniqueConstraint(
            "case_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            "source_record_id",
            name="uq_relationships_case_src_dst_type_record",
        ),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    target_entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    relationship_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_records.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    context: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Relationship id={self.id} {self.relationship_type!r} "
            f"{self.source_entity_id!r} -> {self.target_entity_id!r}>"
        )
