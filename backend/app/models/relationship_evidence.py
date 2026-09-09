"""RelationshipEvidence - provenance for one relationship (field pair or co-occurrence)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RelationshipEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "relationship_evidence"
    __table_args__ = (
        UniqueConstraint(
            "relationship_id",
            "source_record_id",
            "evidence_type",
            name="uq_relationship_evidence_rel_record_type",
        ),
    )

    relationship_id: Mapped[str] = mapped_column(
        ForeignKey("relationships.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_records.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(32), default="field", nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<RelationshipEvidence id={self.id} type={self.evidence_type!r}>"
