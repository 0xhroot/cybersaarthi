"""Public HTTP schemas for the AI assistant endpoints.

These are the only AI shapes the browser sees. Internal tool payloads and
raw model transcripts never cross this boundary unsanitized.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AiMode = Literal["general", "case", "evidence", "graph", "copilot", "report", "knowledge"]
# ``think`` is the user-facing name for the ``deep`` budget plus a structured
# rationale/uncertainty response (see AnswerProfile.structured). ``deep`` is
# kept for compatibility — the two share one budget definition.
AiProfile = Literal["quick", "standard", "deep", "think"]


class AiSourceOut(BaseModel):
    type: str
    id: str
    label: str = ""
    url: str | None = None


class AiToolEventOut(BaseModel):
    tool: str
    ok: bool
    arguments: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    # Structured outcome (case_not_found_or_not_accessible / case_found_but_empty
    # / case_found_with_data / case_ambiguous / lookup_error) so clients can tell
    # an authorized miss from an empty case from a hard lookup failure.
    status: str | None = None
    duration_ms: int | None = None


class AiChatRequest(BaseModel):
    """One chat turn. ``conversation_id`` continues an owned thread.

    ``profile`` selects a latency/quality trade-off: ``quick`` (short answers,
    fewer tool iterations), ``standard`` (default), ``deep`` (larger budget,
    more tool iterations), ``think`` (the ``deep`` budget plus a structured
    rationale/uncertainty/citations response and streamed progress states).
    Defaults to the server-configured ``AI_DEFAULT_PROFILE`` when omitted, so
    existing clients are unaffected.
    """

    question: str = Field(min_length=1, max_length=4000)
    mode: AiMode = "general"
    case_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    profile: AiProfile | None = None


class AiChatResponse(BaseModel):
    answer: str
    conversation_id: uuid.UUID
    message_id: uuid.UUID | None = None
    sources: list[AiSourceOut] = Field(default_factory=list)
    tool_events: list[AiToolEventOut] = Field(default_factory=list)
    grounded: bool = False
    prompt_version: str
    duration_ms: int = 0
    first_token_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class AiConversationOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID | None
    title: str
    mode: str
    status: str
    prompt_version: str | None
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None

    model_config = {"from_attributes": True}


class AiConversationListResponse(BaseModel):
    items: list[AiConversationOut]
    total: int


class AiConversationRenameRequest(BaseModel):
    """Rename an owned conversation."""

    title: str = Field(min_length=1, max_length=120)


class AiMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    sources: list[AiSourceOut] | None = None
    tool_events: list[AiToolEventOut] | None = None
    grounded: bool = False
    prompt_version: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AiMessageListResponse(BaseModel):
    items: list[AiMessageOut]


class AiStatusResponse(BaseModel):
    enabled: bool
    ready: bool
    managed: bool
    model_configured: str
    model_valid: bool
    context_length: int
    max_output_tokens: int
    gpu_layers: int
    started: bool
    load_seconds: float | None
    restarts: int
    requests_total: int
    errors_total: int
    generations_active: int
    last_error: str | None = None
    prompt_version: str | None = None
    tools: list[str] = Field(default_factory=list)
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    # Observability (null when unavailable — e.g. no GPU tooling in the pod).
    last_request_ms: int | None = None
    avg_request_ms: int | None = None
    gpu_name: str | None = None
    vram_used_mb: int | None = None
    vram_total_mb: int | None = None
    gpu_util_percent: int | None = None


class AiReportDraftRequest(BaseModel):
    case_id: uuid.UUID


class AiReportDraftResponse(BaseModel):
    draft: str
    sources: list[AiSourceOut] = Field(default_factory=list)
    grounded: bool = False
    prompt_version: str
    duration_ms: int = 0
