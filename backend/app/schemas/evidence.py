"""Pydantic models for the evidence ingestion API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class EvidenceCreateResponse(BaseModel):
    id: UUID
    case_id: UUID
    original_filename: str
    stored_key: str
    content_type: str
    file_size: int
    sha256: str
    format: str | None
    encoding: str | None
    status: str
    status_detail: str | None
    created_at: datetime


class EvidenceListItem(BaseModel):
    id: UUID
    original_filename: str
    sha256: str
    format: str | None
    file_size: int
    status: str
    record_count: int | None
    created_at: datetime


class EvidenceListResponse(BaseModel):
    items: list[EvidenceListItem]
    total: int


class IngestRequest(BaseModel):
    evidence_file_id: UUID
    metadata: dict[str, Any] | None = Field(default=None, description="Job metadata (optional)")


class IngestJobResponse(BaseModel):
    id: UUID
    case_id: UUID
    evidence_file_id: UUID | None
    stage: str
    status: Literal["pending", "running", "completed", "failed", "partial"]
    progress: int
    total_records: int
    processed_records: int
    graph_sync_status: Literal["pending", "synced", "failed"]
    error: str | None
    graph_error: str | None
    summary: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class IngestJobListResponse(BaseModel):
    items: list[IngestJobResponse]
    total: int


class IngestAcceptedResponse(BaseModel):
    job: IngestJobResponse
    duplicate: bool = False


class GraphSyncResult(BaseModel):
    job_id: UUID
    graph_sync_status: Literal["pending", "synced", "failed"]
    nodes_synced: int
    edges_synced: int
    error: str | None = None
