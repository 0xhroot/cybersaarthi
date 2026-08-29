"""MetricResult - a per-entity analytical metric computed for a case.

Metric values are always explained by the raw computation that produced them;
normalized_score is the score scaled to [0, 1] for cross-metric comparison.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

METRIC_NAMES = (
    "degree_centrality",
    "in_degree_centrality",
    "out_degree_centrality",
    "betweenness_centrality",
    "closeness_centrality",
    "pagerank",
    "community_count",
    "bridge_score",
    "spanning_score",
    "relationship_strength",
)


class MetricResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "metric_results"
    __table_args__ = (
        Index("ix_metric_results_case_id", "case_id"),
        Index("ix_metric_results_run_id", "run_id"),
        Index("ix_metric_results_case_metric", "case_id", "metric_name"),
        Index("ix_metric_results_case_entity", "case_id", "entity_id"),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analytics_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=True,
    )
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_value: Mapped[float] = mapped_column(Float, nullable=False)
    normalized_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<MetricResult id={self.id} metric={self.metric_name!r} "
            f"raw={self.raw_value} norm={self.normalized_score}>"
        )
