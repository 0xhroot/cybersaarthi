"""Pydantic contracts for integrity verification & chain-of-custody (feature 9).

Deterministic outcomes are first-class values here: a verification result can
be ``match``, ``mismatch``, ``missing_expected``, ``missing_source`` or
``unsupported_algorithm`` - the API returns all of them as 200 responses with
explicit states, never as invented green checks. Custody events are append-only
requests; nothing in this contract can edit or delete recorded history.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field

from app.schemas.evidence_intelligence import AnalysisJobOut, DerivedArtifactOut

CustodyEventType = Literal[
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
]


class IntegrityVerificationRequest(BaseModel):
    """Hash-verify one evidence item against its original stored bytes."""

    evidence_file_id: UUID


class IntegrityVerificationResponse(BaseModel):
    """One verification result. ``status`` distinguishes every outcome.

    ``expected_sha256``/``calculated_sha256`` are None exactly when the check
    could not conclude (missing recorded hash, missing object bytes); the
    frontend must render those as explicit unknowns, not as passes.
    """

    evidence_id: UUID
    artifact_id: UUID
    status: Literal[
        "match",
        "mismatch",
        "missing_expected",
        "missing_source",
        "unsupported_algorithm",
    ]
    algorithm: str | None
    expected_sha256: str | None
    calculated_sha256: str | None
    object_present: bool
    file_size_bytes: int | None
    duration_ms: int
    verified_at: str


class CustodyAuditRequest(BaseModel):
    """Run the deterministic custody rule set (whole case or one item)."""

    evidence_file_id: UUID | None = None


class CustodyEventCreate(BaseModel):
    """Append one custody event. All fields optional except type + time.

    Required party fields per type (collector/transferor/recipient) are
    enforced deterministically against policy v1.0.0 in the service layer with
    the typed ``CUSTODY_FIELD_REQUIRED`` code.
    """

    event_type: CustodyEventType
    occurred_at: datetime
    collector: str | None = Field(default=None, max_length=255)
    transferor: str | None = Field(default=None, max_length=255)
    recipient: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    method: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=4000)
    recorded_sha256: str | None = Field(default=None, max_length=64)


class CustodyEventOut(BaseModel):
    """One recorded custody event (immutable history as stored).

    ``recorded_at`` is the row's ``created_at`` - when it was documented,
    distinct from ``occurred_at`` - the rule engine checks the pair.
    """

    id: UUID
    case_id: UUID
    evidence_file_id: UUID | None
    event_type: str
    occurred_at: datetime
    recorded_at: datetime = Field(validation_alias=AliasChoices("recorded_at", "created_at"))
    actor_user_id: UUID | None
    collector: str | None
    transferor: str | None
    recipient: str | None
    location: str | None
    method: str | None
    notes: str | None
    recorded_sha256: str | None


class CustodyChronologyResponse(BaseModel):
    """Evidence summary + its custody events in occurred-at order.

    ``deleted_at``/``last_verification`` surface state honestly: no computed
    verification happens on read, and deleted evidence reports its deletion
    instead of appearing green.
    """

    evidence_id: UUID
    original_filename: str
    sha256: str
    algorithm: str
    format: str | None
    file_size: int
    created_at: datetime
    deleted_at: datetime | None
    events: list[CustodyEventOut]
    event_count: int


class ExplainResponse(BaseModel):
    """AI explanation of one recorded finding (facts-only, review-independent)."""

    explanation_artifact: DerivedArtifactOut
    text: str
    rule: str
    # Structured explanation for Phase 4 findings (financial/cross-case); the
    # custody narration is plain text and leaves this None.
    explanation: dict[str, Any] | None = None


class JobSubmitResponse(BaseModel):
    """Accepted analysis job + whether this call collapsed onto an existing job."""

    job: AnalysisJobOut
    duplicate: bool
