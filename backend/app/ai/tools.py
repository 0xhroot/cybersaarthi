"""Controlled, read-only tools exposed to the local model.

Design rules:
- v1 is read-only. Nothing here mutates cases, evidence, findings or users;
  report drafting is a dedicated service endpoint, not a model tool.
- Arguments arrive from the model (untrusted). Each handler re-validates
  identifiers and re-checks the caller's authorization scope before touching
  the database — a forged ``case_id`` can never cross an isolation boundary.
- Every execution is audited with actor id, tool name, sanitized arguments
  and outcome.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import knowledge, retrieval
from app.ai.schemas import SourceRef, ToolExecutionResult
from app.models import Case, Entity, User
from app.services.audit import record_audit

logger = logging.getLogger(__name__)

Handler = Callable[["ToolContext", dict[str, Any]], Awaitable[ToolExecutionResult]]


@dataclass(slots=True)
class ToolContext:
    """Everything a handler is allowed to touch — never the raw request."""

    request: Request
    session: AsyncSession
    user: User
    # Case scope validated by the route via get_case_or_404, if the request
    # was case-scoped. Tools that take a case_id argument still re-validate.
    case: Case | None = None


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema for the model
    handler: Handler
    case_scoped: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def _ok(
    tool: str, payload: dict[str, Any], sources: list[SourceRef] | None = None
) -> ToolExecutionResult:
    return ToolExecutionResult(tool=tool, ok=True, payload=payload, sources=sources or [])


def _err(tool: str, message: str) -> ToolExecutionResult:
    return ToolExecutionResult(tool=tool, ok=False, error=message)


def _limit(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


async def _authorize_case(
    ctx: ToolContext, arguments: dict[str, Any]
) -> tuple[Case | None, str | None]:
    """Re-validate a model-supplied case id against the caller's access."""
    from app.api.dependencies import assert_case_access

    raw = arguments.get("case_id")
    if raw is None and ctx.case is not None:
        return ctx.case, None
    if raw is None:
        return None, "case_id is required"
    try:
        case_uuid = uuid.UUID(str(raw))
    except ValueError:
        return None, "case_id is not a valid identifier"
    case = await ctx.session.get(Case, case_uuid)
    if case is None:
        return None, "case not found"
    try:
        await assert_case_access(ctx.request, case, ctx.user, ctx.session)
    except Exception:  # noqa: BLE001 - re-raised as a sanitized tool error
        return None, "access to this case is denied"
    return case, None


# -- handlers ------------------------------------------------------------


async def tool_search_cases(ctx: ToolContext, arguments: dict[str, Any]) -> ToolExecutionResult:
    query = str(arguments.get("query", ""))[:200]
    cases = await retrieval.accessible_cases(ctx.session, ctx.user, query=query or None)
    payload = {
        "cases": [
            {
                "case_id": str(case.id),
                "case_number": case.case_number,
                "title": case.title,
                "status": case.status,
                "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            }
            for case in cases
        ]
    }
    sources = [
        SourceRef(type="case", id=str(case.id), label=case.case_number, url=f"/cases/{case.id}")
        for case in cases
    ]
    return _ok("search_cases", payload, sources)


async def tool_get_case_summary(ctx: ToolContext, arguments: dict[str, Any]) -> ToolExecutionResult:
    case, error = await _authorize_case(ctx, arguments)
    if error or case is None:
        return _err("get_case_summary", error or "case unavailable")
    text, sources = await retrieval.case_summary(ctx.session, case)
    return _ok("get_case_summary", {"text": text}, sources)


async def tool_list_evidence(ctx: ToolContext, arguments: dict[str, Any]) -> ToolExecutionResult:
    case, error = await _authorize_case(ctx, arguments)
    if error or case is None:
        return _err("list_evidence", error or "case unavailable")
    text, sources = await retrieval.evidence_digest(
        ctx.session, case, limit=_limit(arguments.get("limit"), retrieval.EVIDENCE_LIMIT, 50)
    )
    return _ok("list_evidence", {"text": text}, sources)


async def tool_get_entity(ctx: ToolContext, arguments: dict[str, Any]) -> ToolExecutionResult:
    raw_id = str(arguments.get("entity_id", ""))
    try:
        entity_uuid = uuid.UUID(raw_id)
    except ValueError:
        return _err("get_entity", "entity_id is not a valid identifier")
    entity = await ctx.session.get(Entity, entity_uuid)
    if entity is None:
        return _err("get_entity", "entity not found")
    case, error = await _authorize_case(ctx, {"case_id": entity.case_id})
    if error or case is None:
        return _err("get_entity", error or "access denied")
    payload = {
        "entity_id": str(entity.id),
        "type": entity.entity_type,
        "value": entity.display_value[:512],
        "confidence": entity.confidence,
        "status": entity.status,
        "case_id": entity.case_id,
    }
    sources = [
        SourceRef(type="entity", id=str(entity.id), label=entity.display_value[:80],
                  url=f"/cases/{entity.case_id}/entities")
    ]
    return _ok("get_entity", payload, sources)


async def tool_get_timeline(ctx: ToolContext, arguments: dict[str, Any]) -> ToolExecutionResult:
    case, error = await _authorize_case(ctx, arguments)
    if error or case is None:
        return _err("get_timeline", error or "case unavailable")
    text, sources = await retrieval.timeline_digest(
        ctx.session, case, limit=_limit(arguments.get("limit"), retrieval.TIMELINE_LIMIT, 50)
    )
    return _ok("get_timeline", {"text": text}, sources)


async def tool_get_analytics_summary(
    ctx: ToolContext, arguments: dict[str, Any]
) -> ToolExecutionResult:
    case, error = await _authorize_case(ctx, arguments)
    if error or case is None:
        return _err("get_analytics_summary", error or "case unavailable")
    metrics_text, metric_sources = await retrieval.analytics_digest(ctx.session, case)
    graph_text, graph_sources = await retrieval.graph_relationships_digest(ctx.session, case)
    return _ok(
        "get_analytics_summary",
        {"metrics": metrics_text, "graph": graph_text},
        metric_sources + graph_sources,
    )


async def tool_search_knowledge(ctx: ToolContext, arguments: dict[str, Any]) -> ToolExecutionResult:
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.AI_KNOWLEDGE_ENABLED:
        return _err("search_knowledge", "knowledge search is disabled")
    query = str(arguments.get("query", ""))[:300]
    if not query.strip():
        return _err("search_knowledge", "query is required")
    chunks = knowledge.search(settings.repo_root, query)
    return _ok(
        "search_knowledge",
        {"text": knowledge.format_chunks(chunks)},
        [chunk.as_source() for chunk in chunks],
    )


# -- registry ------------------------------------------------------------

TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec(
            name="search_cases",
            description=(
                "Search cases the current user can access by title or case "
                "number. Returns case_id, number, title, status."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "keywords or case number"}
                },
                "required": ["query"],
            },
            handler=tool_search_cases,
        ),
        ToolSpec(
            name="get_case_summary",
            description="Fetch the summary and record counts for one authorized case.",
            parameters={
                "type": "object",
                "properties": {"case_id": {"type": "string", "description": "case UUID"}},
                "required": ["case_id"],
            },
            handler=tool_get_case_summary,
            case_scoped=True,
        ),
        ToolSpec(
            name="list_evidence",
            description=(
                "List evidence metadata (filename, hash, size, time) for one "
                "authorized case. Never returns file contents."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["case_id"],
            },
            handler=tool_list_evidence,
            case_scoped=True,
        ),
        ToolSpec(
            name="get_entity",
            description="Fetch one entity by UUID; access to its case is re-checked.",
            parameters={
                "type": "object",
                "properties": {"entity_id": {"type": "string", "description": "entity UUID"}},
                "required": ["entity_id"],
            },
            handler=tool_get_entity,
        ),
        ToolSpec(
            name="get_timeline",
            description="Fetch recent timeline events for one authorized case.",
            parameters={
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["case_id"],
            },
            handler=tool_get_timeline,
            case_scoped=True,
        ),
        ToolSpec(
            name="get_analytics_summary",
            description=(
                "Fetch analytics metrics and relationship statistics for one "
                "authorized case."
            ),
            parameters={
                "type": "object",
                "properties": {"case_id": {"type": "string"}},
                "required": ["case_id"],
            },
            handler=tool_get_analytics_summary,
            case_scoped=True,
        ),
        ToolSpec(
            name="search_knowledge",
            description=(
                "Keyword-search the approved CyberSaarthi documentation "
                "(how-to, architecture)."
            ),
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=tool_search_knowledge,
        ),
    )
}


def tool_list_for_prompt(enabled_tools: dict[str, ToolSpec] | None = None) -> str:
    specs = enabled_tools if enabled_tools is not None else TOOLS
    return ", ".join(
        f"{spec.name}({', '.join(spec.parameters.get('properties', {}))})"
        for spec in specs.values()
    )


async def execute_tool(
    ctx: ToolContext,
    name: str,
    arguments: dict[str, Any],
    *,
    enabled_tools: dict[str, ToolSpec] | None = None,
) -> ToolExecutionResult:
    """Validate, dispatch and audit one tool call (model output is untrusted)."""
    specs = enabled_tools if enabled_tools is not None else TOOLS
    if name not in specs:
        return _err(name or "unknown", f"unknown tool: {name}")
    spec = specs[name]
    if not isinstance(arguments, dict):
        return _err(name, "arguments must be a JSON object")
    result = await spec.handler(ctx, arguments)
    await record_audit(
        ctx.session,
        actor_id=ctx.user.id,
        action="ai_tool_call",
        resource_type="ai_tool",
        resource_id=name,
        case_id=ctx.case.id if ctx.case is not None else None,
        metadata={
            "tool": name,
            "ok": result.ok,
            "arguments": _sanitize_arguments(arguments),
            "error": result.error,
        },
    )
    return result


def _sanitize_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Truncate values before they hit the audit log."""
    clean: dict[str, Any] = {}
    for key, value in list(arguments.items())[:10]:
        if isinstance(value, (int, float, bool, type(None))):
            clean[str(key)[:64]] = value
        else:
            clean[str(key)[:64]] = str(value)[:200]
    return clean
