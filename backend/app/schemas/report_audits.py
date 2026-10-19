"""Pydantic contracts for the AI report auditor API (phase 6)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.evidence_intelligence import DerivedArtifactOut


class ReportAuditSubmitRequest(BaseModel):
    """Queue one audit of a report draft.

    Exactly one source: ``conversation_id`` + ``message_id`` (a report-mode
    assistant message of this case) XOR ``draft_text`` (the common case of an
    externally edited draft). The source is validated server-side with typed
    refusals; the original draft is never modified.
    """

    conversation_id: UUID | None = None
    message_id: UUID | None = None
    draft_text: str | None = None


class ReportAuditOut(BaseModel):
    """One audit run: job state, artifact linkage and staleness.

    ``stale`` compares the audited ``draft_hash`` with the current content of
    the referenced message (``None`` when the audit did not reference a
    message or the message is gone).
    """

    id: UUID
    case_id: UUID
    status: str
    created_at: datetime
    completed_at: datetime | None
    error: str | None
    draft_source_type: str | None
    draft_hash: str | None
    draft_chars: int | None
    conversation_id: UUID | None
    message_id: UUID | None
    artifact_id: UUID | None
    claims: int | None
    stale: bool | None
    result_summary: dict[str, Any] | None


class ReportAuditDetailOut(ReportAuditOut):
    """Detail view: the full ``report_claim_review`` findings payload."""

    artifact: DerivedArtifactOut | None


class ReportAuditListResponse(BaseModel):
    items: list[ReportAuditOut]
    total: int
    limit: int
    offset: int
