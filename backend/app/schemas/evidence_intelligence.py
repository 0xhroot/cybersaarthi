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
    graph_synced: bool | None = None
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


class MultilingualSubmitRequest(BaseModel):
    """Queue one multilingual complaint analysis run for an evidence file.

    ``translate`` additionally forces translation of English text (translation
    always runs for non-English text; the original is preserved either way).
    """

    evidence_file_id: UUID
    translate: bool = False


class TriageSubmitRequest(BaseModel):
    """Queue one digital-forensics triage run for an evidence file.

    Deterministic parsing and structural rules run regardless; the single
    model call only explains the recorded observations.
    """

    evidence_file_id: UUID


class CaseAnalysisSubmitRequest(BaseModel):
    """Queue one case-level phase-3 analysis run (features A, B, C).

    Intentionally empty: these jobs scan the whole case, are idempotent
    (one active job per feature, attempt-numbered retries) and take their
    bounds from deployment settings, not from the request.
    """


class ContradictionResolveRequest(BaseModel):
    """Append a reviewer resolution state to one contradiction candidate.

    ``state`` and ``note`` are validated in the service layer so the API
    answers with typed codes (``CONTRADICTION_STATE_INVALID``,
    ``REVIEW_NOTE_REQUIRED``) instead of a generic validation error.
    """

    state: str = Field(max_length=32)
    note: str = Field(max_length=2000)


class FlowTraceRequest(BaseModel):
    """One bounded, read-only structure trace over a case's financial facts.

    ``edge_kind="transfer"`` is a supported capability whose answer today is
    ``insufficient_data`` (``reason="no_transfer_edges_in_ingest"``): the ingest
    contains no transfer edges, so the API reports the trail as absent rather
    than substituting associations. ``max_depth`` / ``max_paths`` are clamped to
    the server's configured bounds and the effective values are echoed back.
    """

    target: str = Field(min_length=1, max_length=512)
    target_kind: Literal["account", "transaction"] = "account"
    edge_kind: Literal["association", "transfer"] = "association"
    max_depth: int | None = Field(default=None, ge=1)
    max_paths: int | None = Field(default=None, ge=1)


class FlowTraceHop(BaseModel):
    """One traversed edge, typed so a UI can warn it is not a transfer."""

    source: str
    target: str
    edge_kind: str
    derivation: str
    confidence: str
    relationship_type: str | None = None
    supporting_source_record_ids: list[str]


class FlowTracePath(BaseModel):
    """One maximal path; ``incomplete`` marks a trail that stops in the evidence."""

    nodes: list[str]
    hops: list[FlowTraceHop]
    depth: int
    end_state: str
    incomplete: bool


class FlowTraceBounds(BaseModel):
    """Effective bounds actually applied to this request."""

    max_depth: int
    max_paths: int
    max_records: int
    records_scanned: int


class FlowTraceNetworkSummary(BaseModel):
    """Honest scan scope: always zero confirmed transfer edges today."""

    nodes_total: int
    edges_total: int
    confirmed_transfer_edges: int


class FlowTraceResponse(BaseModel):
    """Deterministic trace result with its limitations stated inline."""

    case_id: UUID
    flow_rules_version: str
    target: str
    target_kind: str
    edge_kind: str
    status: Literal["ok", "not_found", "insufficient_data"]
    reason: str | None = None
    start_node: str | None = None
    matched_facts: int = 0
    target_degree: int = 0
    paths: list[FlowTracePath] = []
    paths_bounded: bool = False
    records_bounded: bool = False
    bounds: FlowTraceBounds
    network: FlowTraceNetworkSummary
    limitations: list[str]
