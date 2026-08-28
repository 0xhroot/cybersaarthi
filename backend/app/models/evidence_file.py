"""EvidenceFile - an uploaded evidence file bound to a case, retained in MinIO."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
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


class EvidenceFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_files"
    __table_args__ = (
        CheckConstraint(
            "status IN ('stored', 'parsed', 'processing', 'failed')",
            name="evidence_file_status_valid",
        ),
        UniqueConstraint("case_id", "sha256", name="uq_evidence_files_case_sha256"),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    data_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    format: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    encoding: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="stored", nullable=False)
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<EvidenceFile id={self.id} file={self.original_filename!r} "
            f"sha256={self.sha256[:12]}...>"
        )
