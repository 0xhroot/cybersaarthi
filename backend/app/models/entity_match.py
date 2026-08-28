"""EntityMatch - the outcome of comparing a candidate entity to a resolved entity."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EntityStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EntityMatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "entity_matches"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('auto_match', 'review', 'no_match')",
            name="entity_match_decision_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'merged', 'review', 'rejected')",
            name="entity_match_status_valid",
        ),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_candidate_id: Mapped[str] = mapped_column(
        ForeignKey("entity_candidates.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    target_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    signals: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=EntityStatus.REVIEW, nullable=False)

    def __repr__(self) -> str:
        return f"<EntityMatch id={self.id} decision={self.decision!r} score={self.score}>"
