"""Pydantic contracts for the evidence intelligence API (shared foundation)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DerivedArtifactOut(BaseModel):
    id: UUID
    case_id: UUID
    kind: str
    origin: str
    status: str
    validation_status: str
    evidence_file_id: UUID | None
    source_record_id: UUID | None
    source_locator: dict[str, Any] | None
    payload: dict[str, Any]
    content_hash: str
    parser_version: str
    prompt_version: str | None
    model_profile: str | None
    analysis_job_id: UUID | None
    validation_errors: list[dict[str, Any]] | None
    review_note: str | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    parent_artifact_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ArtifactListResponse(BaseModel):
    items: list[DerivedArtifactOut]
    total: int
    limit: int
    offset: int


class AnalysisJobOut(BaseModel):
    id: UUID
    case_id: UUID
    feature: str
    status: str
    idempotency_key: str
    progress: int
    total_records: int
    processed_records: int
    attempts: int
    timeout_seconds: int
    cancel_requested: bool
    error: str | None
    result_summary: dict[str, Any] | None
    evidence_file_id: UUID | None
    actor_id: UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[AnalysisJobOut]
    total: int
    limit: int
    offset: int


class ArtifactReviewRequest(BaseModel):
    """Human review decision for one derived artifact.

    Consequential actions are human-only: the API never auto-approves derived
    output, and the route re-checks the reviewer's permission.

    ``payload`` optionally carries an *edited* version of an extraction
    artifact (``{"fields": {...}}``) when approving. Edits are re-validated
    against the strict schema and the artifact's source record first, and are
    stored as a new lineage-linked artifact - the original model output stays
    immutable (``superseded``), never rewritten.
    """

    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=2000)
    payload: dict[str, Any] | None = None


class ExtractionSubmitRequest(BaseModel):
    """Queue one extraction run for an authorized evidence file."""

    evidence_file_id: UUID
