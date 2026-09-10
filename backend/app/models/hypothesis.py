"""Hypothesis - a stand-alone reasoning object for a case.

Explicit kind ladder: FACT -> OBSERVATION -> INFERENCE -> HYPOTHESIS. Linked
evidence, entities and relationships support or contradict the statement. Status
lifecycle is administrative (state machine enforced in the service, not here).
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

HYPOTHESIS_KINDS = ("fact", "observation", "inference", "hypothesis")

HYPOTHESIS_STATUSES = (
    "proposed",
    "under_review",
    "supported",
    "contradicted",
    "dismissed",
    "concluded",
)


class Hypothesis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "hypotheses"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('fact', 'observation', 'inference', 'hypothesis')",
            name="hypothesis_kind_valid",
        ),
        CheckConstraint(
            "status IN ('proposed', 'under_review', 'supported', "
            "'contradicted', 'dismissed', 'concluded')",
            name="hypothesis_status_valid",
        ),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), default="hypothesis", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="proposed", nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    supporting_evidence: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    contradicting_evidence: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    related_entities: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    related_relationships: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    evidence_weight: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Hypothesis id={self.id} kind={self.kind!r} status={self.status!r}>"
