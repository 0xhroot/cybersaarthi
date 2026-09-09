"""Finding - an explainable analytical conclusion about a case.

Findings are the outcome of the investigation intelligence engine: suspicious
patterns, structural anomalies, missing-link hypotheses, network insights and
relationship insights. Every finding carries structured signals, the graph
paths and evidence that support it, and the limitations of the measurement.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

FINDING_TYPES = (
    "pattern",
    "anomaly",
    "hypothesis",
    "network_insight",
    "relationship_insight",
)
FINDING_SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
FINDING_STATUSES = ("NEW", "REVIEWED", "DISMISSED", "CONFIRMED")


class Finding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(
            "finding_type IN ('pattern', 'anomaly', 'hypothesis', "
            "'network_insight', 'relationship_insight')",
            name="finding_type_valid",
        ),
        CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="finding_severity_valid",
        ),
        CheckConstraint(
            "status IN ('NEW', 'REVIEWED', 'DISMISSED', 'CONFIRMED')",
            name="finding_status_valid",
        ),
        Index("ix_findings_case_id", "case_id"),
        Index("ix_findings_case_status", "case_id", "status"),
        Index("ix_findings_case_type", "case_id", "finding_type"),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analytics_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    finding_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="NEW", nullable=False)
    affected_entities: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    affected_relationships: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    evidence_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Finding id={self.id} type={self.finding_type!r} "
            f"severity={self.severity!r} status={self.status!r}>"
        )
