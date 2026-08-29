"""CommunityResult - a detected community within a case's knowledge graph."""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CommunityResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "community_results"
    __table_args__ = (
        UniqueConstraint("case_id", "run_id", "community_id", name="uq_community_run_id"),
        Index("ix_community_results_case_id", "case_id"),
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
    community_id: Mapped[str] = mapped_column(String(32), nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    density: Mapped[float] = mapped_column(Float, nullable=False)
    internal_edges: Mapped[int] = mapped_column(Integer, nullable=False)
    external_edges: Mapped[int] = mapped_column(Integer, nullable=False)
    dominant_entity_types: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    dominant_relationship_types: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    member_entity_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<CommunityResult id={self.id} community={self.community_id!r} "
            f"members={self.member_count} density={self.density:.3f}>"
        )
