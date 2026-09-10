"""TimelineEvent - investigator-facing chronological case timeline.

Events are either generated automatically by the platform (evidence uploaded,
collection sealed, package imported, analytics run) or recorded by analysts.
``occurred_at`` is the semantic timestamp of the underlying activity; ``created_at``
is when the record was written.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

TIMELINE_EVENT_KINDS = (
    "evidence_uploaded",
    "evidence_restored",
    "collection_created",
    "collection_sealed",
    "package_imported",
    "device_registered",
    "device_approved",
    "device_revoked",
    "analytics_run",
    "finding_created",
    "entity_merged",
    "match_accepted",
    "match_rejected",
    "hypothesis_created",
    "hypothesis_status_changed",
    "report_generated",
    "case_event",
    "iot_event",
)


class TimelineEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "timeline_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('evidence_uploaded', 'evidence_restored', 'collection_created', "
            "'collection_sealed', 'package_imported', 'device_registered', "
            "'device_approved', 'device_revoked', 'analytics_run', 'finding_created', "
            "'entity_merged', 'match_accepted', 'match_rejected', 'hypothesis_created', "
            "'hypothesis_status_changed', 'report_generated', 'case_event', 'iot_event')",
            name="timeline_event_kind_valid",
        ),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    evidence_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_files.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    collection_id: Mapped[str | None] = mapped_column(
        ForeignKey("collections.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    device_id: Mapped[str | None] = mapped_column(
        ForeignKey("field_devices.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<TimelineEvent id={self.id} kind={self.kind!r} at={self.occurred_at}>"
