"""IngestionJob - tracks end-to-end ingestion of one evidence file into the case."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import GraphSyncStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IngestionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'partial')",
            name="ingestion_job_status_valid",
        ),
        CheckConstraint(
            "graph_sync_status IN ('pending', 'synced', 'failed')",
            name="ingestion_job_graph_sync_valid",
        ),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    evidence_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_files.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    stage: Mapped[str] = mapped_column(String(64), default="created", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    graph_sync_status: Mapped[str] = mapped_column(
        String(32), default=GraphSyncStatus.PENDING, nullable=False
    )
    graph_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<IngestionJob id={self.id} status={self.status!r}>"
