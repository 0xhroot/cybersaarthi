"""Report - a generated, downloadable case artifact (JSON / CSV / PDF)."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

REPORT_TYPES = ("case_summary", "intelligence", "evidence_manifest", "timeline", "network_analysis")

REPORT_FORMATS = ("json", "csv", "pdf")

REPORT_STATUSES = ("generating", "ready", "failed")


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "report_type IN ('case_summary', 'intelligence', 'evidence_manifest', "
            "'timeline', 'network_analysis')",
            name="report_type_valid",
        ),
        CheckConstraint(
            "format IN ('json', 'csv', 'pdf')",
            name="report_format_valid",
        ),
        CheckConstraint(
            "status IN ('generating', 'ready', 'failed')",
            name="report_status_valid",
        ),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="generating", nullable=False)
    minio_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Report id={self.id} type={self.report_type!r} format={self.format!r}>"
