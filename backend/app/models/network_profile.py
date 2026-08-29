"""NetworkProfile - the deterministic Network DNA profile of a single entity.

Every feature is a real, documented measurement of the entity within its case
graph; overall_score is a weighted aggregate of the normalized dimensions.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

NETWORK_PROFILE_TIERS = ("FOCAL", "SIGNIFICANT", "MONITORED", "PERIPHERAL")


class NetworkProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "network_profiles"
    __table_args__ = (
        CheckConstraint(
            "tier IN ('FOCAL', 'SIGNIFICANT', 'MONITORED', 'PERIPHERAL')",
            name="network_profile_tier_valid",
        ),
        UniqueConstraint("entity_id", "run_id", name="uq_network_profile_entity_run"),
        Index("ix_network_profiles_case_id", "case_id"),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analytics_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    signals: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<NetworkProfile id={self.id} entity={self.entity_id} "
            f"score={self.overall_score:.3f} tier={self.tier!r}>"
        )
