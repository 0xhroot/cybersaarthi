"""DerivedArtifact - an artifact derived from evidence or analysis, with provenance.

Derived rows never replace originals: EvidenceFile bytes, SourceRecord rows and
custody events stay untouched. Every artifact carries the lineage needed to
re-derive and to authorize a citation - case scope, source file/record,
field-level locator, content hash, parser/model versions and review state -
so a reviewer can always distinguish original evidence from machine output.

``origin`` separates deterministic parser output from LLM output; ``status``
tracks the human-review workflow (consequential actions are never automatic).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# One kind per evidence-intelligence feature; extended only by migration.
DERIVED_ARTIFACT_KINDS = (
    "extraction",
    "entity_resolution",
    "timeline_proposal",
    "contradiction",
    "financial_finding",
    "cross_case_link",
    "translation",
    "triage_observation",
    "custody_finding",
    "report_claim_review",
)

DERIVED_ARTIFACT_ORIGINS = ("llm", "deterministic")

# pending_review -> approved | rejected (human review); failed = pipeline error;
# superseded = a later derivation replaced it; recorded = deterministic fact or
# informational output (verification results, AI explanations) that is never
# queued for approval - it does not claim a decision was made.
DERIVED_ARTIFACT_STATUSES = (
    "pending_review",
    "approved",
    "rejected",
    "failed",
    "superseded",
    "recorded",
)

# Deterministic schema/source validation outcome, independent of review.
DERIVED_ARTIFACT_VALIDATION = ("valid", "flagged", "invalid")


class DerivedArtifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "derived_artifacts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('extraction', 'entity_resolution', 'timeline_proposal', "
            "'contradiction', 'financial_finding', 'cross_case_link', 'translation', "
            "'triage_observation', 'custody_finding', 'report_claim_review')",
            name="derived_artifact_kind_valid",
        ),
        CheckConstraint(
            "origin IN ('llm', 'deterministic')",
            name="derived_artifact_origin_valid",
        ),
        CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'failed', "
            "'superseded', 'recorded')",
            name="derived_artifact_status_valid",
        ),
        CheckConstraint(
            "validation_status IN ('valid', 'flagged', 'invalid')",
            name="derived_artifact_validation_valid",
        ),
        # Idempotent derivation: identical payload for the same kind in the same
        # case maps to one row, so retries and re-runs never duplicate accepted
        # artifacts.
        UniqueConstraint(
            "case_id", "kind", "content_hash", name="uq_derived_artifacts_case_kind_hash"
        ),
        Index(
            "ix_derived_artifacts_case_kind_status",
            "case_id",
            "kind",
            "status",
        ),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending_review", nullable=False)
    validation_status: Mapped[str] = mapped_column(String(16), default="flagged", nullable=False)

    evidence_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_files.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_records.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    # e.g. {"record_no": 12, "field": "amount", "page": null, "char_start": 410}
    source_locator: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    parser_version: Mapped[str] = mapped_column(
        String(64), default="deterministic:1", nullable=False
    )
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_profile: Mapped[str | None] = mapped_column(String(16), nullable=True)
    analysis_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # Field-level schema/source issues found at derivation time (JSONB list of
    # {"field", "code", "message"}), kept even after review.
    validation_errors: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)

    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("derived_artifacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<DerivedArtifact id={self.id} kind={self.kind!r} "
            f"status={self.status!r} hash={self.content_hash[:12]}...>"
        )
