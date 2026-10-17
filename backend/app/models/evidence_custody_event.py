"""EvidenceCustodyEvent - an append-only custody record for one evidence file.

There was no chain-of-custody model anywhere in the schema before phase 2, so
this table is the honest starting point: events are only ever *recorded*
through an authorized endpoint going forward. Nothing is back-filled, no
history is synthesized, and rows are never rewritten to hide gaps - a
correction is a new event.

Semantics (policy v1.0.0, enforced by ``app.services.custody``):

- ``collected``   - item documented as collected/acquired; ``collector`` required.
- ``transferred`` - a hand-off began; ``transferor`` and ``recipient`` required.
- ``received``    - item received into custody (acknowledges a hand-off);
  ``recipient`` required.
- other types (``sealed``, ``unsealed``, ``verified``, ``accessed``,
  ``exported``, ``restored``, ``disposed``) are recorded with actor context in
  ``actor_user_id``/``notes`` and carry no mandatory party fields.

``occurred_at`` is the business time the event happened (timezone-aware);
``created_at`` (TimestampMixin) is when the row was documented - the auditor
checks the two against each other, never the other way round.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CUSTODY_EVENT_TYPES = (
    "collected",
    "transferred",
    "received",
    "sealed",
    "unsealed",
    "verified",
    "accessed",
    "exported",
    "restored",
    "disposed",
)

# Policy v1.0.0: which party fields an event type must document. Empty tuple =
# no mandatory party fields (their absence is NOT a finding).
CUSTODY_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "collected": ("collector",),
    "transferred": ("transferor", "recipient"),
    "received": ("recipient",),
    "sealed": (),
    "unsealed": (),
    "verified": (),
    "accessed": (),
    "exported": (),
    "restored": (),
    "disposed": (),
}


class EvidenceCustodyEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_custody_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('collected', 'transferred', 'received', 'sealed', "
            "'unsealed', 'verified', 'accessed', 'exported', 'restored', 'disposed')",
            name="custody_event_type_valid",
        ),
        # Chronology lives on (evidence, occurred_at): the audit reads events
        # in business-time order per evidence item.
        Index(
            "ix_evidence_custody_events_evidence_occurred",
            "evidence_file_id",
            "occurred_at",
        ),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # SET NULL, not CASCADE: if an evidence row is ever hard-deleted the custody
    # history survives as an explicit orphan (the auditor reports broken
    # references) instead of silently disappearing with it.
    evidence_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_files.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    collector: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transferor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Hash claimed at event time (optional): a later auditor compares it
    # against the actual object bytes; absence is a documented gap, not
    # evidence of tampering.
    recorded_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<EvidenceCustodyEvent id={self.id} type={self.event_type!r} "
            f"occurred={self.occurred_at.isoformat()}>"
        )
