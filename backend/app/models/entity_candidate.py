"""EntityCandidate - an unlinked entity mention extracted from one source record."""

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


class EntityCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "entity_candidates"
    __table_args__ = (
        CheckConstraint(
            "resolution_status IN ('pending', 'auto_match', 'review', 'no_match')",
            name="entity_candidate_resolution_valid",
        ),
        UniqueConstraint(
            "source_record_id",
            "entity_type",
            "normalized_value",
            name="uq_entity_candidates_record_type_value",
        ),
    )

    source_record_id: Mapped[str] = mapped_column(
        ForeignKey("source_records.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    entity_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    raw_value: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(512), nullable=False)
    blocking_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="field", nullable=False)
    context: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<EntityCandidate id={self.id} type={self.entity_type!r} "
            f"value={self.normalized_value!r}>"
        )
