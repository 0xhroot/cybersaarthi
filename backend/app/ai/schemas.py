"""Internal typed schemas for the AI gateway (tool calls, sources, results).

These are *not* the public HTTP schemas (those live in ``app.schemas.ai``);
they type the boundary between retrieval, tool dispatch, the inference client
and the service layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

# Source reference types returned to clients. Ids must be validated against
# the caller's authorization scope before they are attached to a response.
SOURCE_TYPES = frozenset(
    {
        "case",
        "doc",
        "entity",
        "evidence",
        "finding",
        "graph",
        "knowledge",
        "metric",
        "timeline",
        "victim",
    }
)


class SourceRef(BaseModel):
    """A citation pointing at an authorized record or document."""

    type: str = Field(pattern=f"^({'|'.join(sorted(SOURCE_TYPES))})$")
    id: str = Field(max_length=128)
    label: str = Field(max_length=255, default="")
    # In-app route the client can link to (already sanitized by the backend).
    url: str | None = Field(default=None, max_length=512)


class ToolCallProposal(BaseModel):
    """A structured tool request parsed from model output (untrusted)."""

    tool: str = Field(max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResult(BaseModel):
    """Outcome of one validated tool execution."""

    tool: str
    ok: bool
    # JSON-serializable payload handed back to the model as data (not truth).
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)


@dataclass(slots=True)
class ChatOutcome:
    """Everything one gateway completion produced."""

    text: str
    sources: list[SourceRef] = field(default_factory=list)
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    grounded: bool = False
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int = 0
    first_token_ms: int | None = None
    iterations: int = 1
