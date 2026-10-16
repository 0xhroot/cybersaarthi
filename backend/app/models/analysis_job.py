"""AnalysisJob - bounded, idempotent lifecycle for evidence-intelligence runs.

There is no durable queue in this deployment (documented limitation in
docs/ai/EVIDENCE_INTELLIGENCE_AUDIT.md); work runs in-process and this table is
the durable record of it. Uniqueness on (case_id, idempotency_key) makes retries
safe: a rerun with the same key returns the existing job instead of starting a
duplicate. ``cancel_requested`` is the cooperative cancellation flag checked by
long-running feature loops; a canceled job can never be marked succeeded
(the transition table forbids it).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# One feature per evidence-intelligence workflow (master prompt features 1-10).
ANALYSIS_JOB_FEATURES = (
    "ingestion",
    "entity_resolution",
    "timeline",
    "contradiction",
    "financial_flow",
    "cross_case",
    "multilingual",
    "triage",
    "custody",
    "report_audit",
)

ANALYSIS_JOB_STATUSES = ("pending", "running", "succeeded", "partial", "failed", "canceled")


class AnalysisJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'partial', 'failed', 'canceled')",
            name="analysis_job_status_valid",
        ),
        CheckConstraint(
            "feature IN ('ingestion', 'entity_resolution', 'timeline', 'contradiction', "
            "'financial_flow', 'cross_case', 'multilingual', 'triage', 'custody', "
            "'report_audit')",
            name="analysis_job_feature_valid",
        ),
        CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="analysis_job_progress_valid",
        ),
        UniqueConstraint("case_id", "idempotency_key", name="uq_analysis_jobs_case_idempotency"),
        Index("ix_analysis_jobs_case_feature_status", "case_id", "feature", "status"),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    feature: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    timeout_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    evidence_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<AnalysisJob id={self.id} feature={self.feature!r} status={self.status!r}>"
