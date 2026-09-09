"""SourceRecord - one parsed record from an evidence file, with full provenance."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SourceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('parsed', 'normalized', 'extracted', 'resolved', 'failed')",
            name="source_record_status_valid",
        ),
        UniqueConstraint("evidence_file_id", "record_no", name="uq_source_records_file_record"),
    )

    evidence_file_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_files.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    record_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    normalized_data: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    entity_mentions: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)
    relationships_data: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="parsed", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<SourceRecord id={self.id} record_no={self.record_no}>"
