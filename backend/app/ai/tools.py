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

from app.ai import knowledge, ranking, retrieval
from app.ai.schemas import (
    CASE_AMBIGUOUS,
    CASE_FOUND_BUT_EMPTY,
    CASE_FOUND_WITH_DATA,
    CASE_NOT_FOUND_OR_NOT_ACCESSIBLE,
    LOOKUP_ERROR,
    SourceRef,
    ToolExecutionResult,
)
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
    tool: str,
    payload: dict[str, Any],
    sources: list[SourceRef] | None = None,
    status: str | None = None,
) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool=tool, ok=True, payload=payload, status=status, sources=sources or []
    )


def _err(tool: str, message: str, status: str | None = None) -> ToolExecutionResult:
    return ToolExecutionResult(tool=tool, ok=False, error=message, status=status)


def _limit(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


def _first_str(arguments: dict[str, Any], *keys: str) -> str:
    """First non-empty string among *keys* (model arguments are untrusted).

    Accepting several aliases for the same intent means a filter the model
    intended can never be silently dropped (the original production defect:
    the search handler read only ``query`` while the model emitted ``case_id``).
    """
    for key in keys:
        value = arguments.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


@dataclass(slots=True)
class _CaseLookup:
    """Structured outcome of resolving + authorizing a case reference."""

    case: Case | None
    status: str
    error: str | None = None
    candidates: list[Case] = field(default_factory=list)


async def _lookup_case(ctx: ToolContext, arguments: dict[str, Any]) -> _CaseLookup:
    """Resolve a model-supplied case reference and re-check the caller's access.

    Accepts an internal UUID, a public case number, or an exact case name.
    Authorization is enforced *before* any case is returned, using the caller's
    preserved principal (``ctx.user``). Failures carry an explicit structured
    status so a database error or a permission denial can never be reported to
    the model as a flat "the case does not exist".
    """
    from app.api.dependencies import assert_case_access

    raw = _first_str(arguments, "case_id", "case_number", "case_name", "case", "name")
    if not raw:
        if ctx.case is not None:
            # Route already authorized this bound case; caller refines status.
            return _CaseLookup(ctx.case, CASE_FOUND_WITH_DATA)
        return _CaseLookup(
            None,
            LOOKUP_ERROR,
            "case_id is required (a case UUID, case number, or exact case name)",
        )

    resolution = None
    try:
        resolution = await retrieval.resolve_case_reference(ctx.session, ctx.user, raw)
    except Exception:  # noqa: BLE001 - a DB failure must be a lookup_error,
        # never a crash and never reported as "the case does not exist".
        logger.exception("case lookup raised")
        return _CaseLookup(None, LOOKUP_ERROR, "case lookup failed (database error)")
    if resolution.status == "error":
        return _CaseLookup(None, LOOKUP_ERROR, resolution.error or "case lookup failed")
    if resolution.status == "not_found":
        return _CaseLookup(
            None,
            CASE_NOT_FOUND_OR_NOT_ACCESSIBLE,
            "case not found or access denied: no case with that identifier is "
            "visible to your account (it may not exist, or it may belong to "
            "another user or tenant)",
        )
    if resolution.status == "ambiguous":
        options = "; ".join(
            f"{c.case_number} — {c.title}" for c in resolution.candidates[:8]
        )
        return _CaseLookup(
            None,
            CASE_AMBIGUOUS,
            "that name matches several authorized cases — ask the user to pick one "
            f"by case number: {options}",
            candidates=resolution.candidates,
        )

    case = resolution.case
    assert case is not None
    # Defense in depth: re-run the canonical authorization gate on the resolved
    # row with the caller's principal, even though the resolver already scoped
    # matches by the same owner/member/admin predicate.
    try:
        await assert_case_access(ctx.request, case, ctx.user, ctx.session)
    except Exception:  # noqa: BLE001 - never leak a cross-tenant case
        return _CaseLookup(
            None,
            CASE_NOT_FOUND_OR_NOT_ACCESSIBLE,
            "access to this case is denied",
        )
    return _CaseLookup(case, CASE_FOUND_WITH_DATA)


# -- handlers ------------------------------------------------------------


async def tool_search_cases(ctx: ToolContext, arguments: dict[str, Any]) -> ToolExecutionResult:
    # The model may address a search by `query` (canonical) or by a case
    # identifier (`case_id` / `case_number` / a name). Accept every alias so the
    # user's filter is never silently dropped and an unfiltered default window
    # is never mistaken for "the only cases that exist".
    query = _first_str(
        arguments, "query", "case_id", "case_number", "case_name", "q", "name", "title"
    )[:200]
    cases = await retrieval.accessible_cases(ctx.session, ctx.user, query=query or None)
    payload = {
        "query": query,
        "match_count": len(cases),
        "cases": [
            {
                "case_id": str(case.id),
                "case_number": case.case_number,
                "title": case.title,
                "status": case.status,
                "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            }
            for case in cases
        ],
    }
    if not cases:
        payload["note"] = (
            "No authorized case matches that query. This does NOT prove a case "
            "does not exist — it may belong to another user or use a different "
            "identifier. Do not invent a case."
        )
        return _ok("search_cases", payload, status=CASE_NOT_FOUND_OR_NOT_ACCESSIBLE)
    sources = [
        SourceRef(type="case", id=str(case.id), label=case.case_number, url=f"/cases/{case.id}")
        for case in cases
    ]
    return _ok("search_cases", payload, sources, status=CASE_FOUND_WITH_DATA)


async def tool_get_case_summary(ctx: ToolContext, arguments: dict[str, Any]) -> ToolExecutionResult:
    lookup = await _lookup_case(ctx, arguments)
    if lookup.case is None:
        # Ambiguity is a successful, actionable result (candidate list to choose
        # from); a miss or a hard error is a structured failure — never a flat
        # "the case does not exist".
        if lookup.status == CASE_AMBIGUOUS and lookup.candidates:
            return _ok(
                "get_case_summary",
                {
                    "status": lookup.status,
                    "error": lookup.error,
                    "candidates": [
                        {"case_id": str(c.id), "case_number": c.case_number, "title": c.title}
                        for c in lookup.candidates
                    ],
                },
                status=lookup.status,
            )
        return _err("get_case_summary", lookup.error or "case unavailable", status=lookup.status)
    case = lookup.case
    text, sources, counts = await retrieval.case_summary(ctx.session, case)
    status = CASE_FOUND_WITH_DATA if any(counts.values()) else CASE_FOUND_BUT_EMPTY
    payload: dict[str, Any] = {"text": text, "status": status, "counts": counts}
    if status == CASE_FOUND_BUT_EMPTY:
        payload["note"] = (
            "case_found_but_empty: the case exists and is authorized, but it has "
            "no linked entities, evidence, findings, victims or timeline events."
        )
    return _ok("get_case_summary", payload, sources, status=status)


async def tool_list_evidence(ctx: ToolContext, arguments: dict[str, Any]) -> ToolExecutionResult:
    lookup = await _lookup_case(ctx, arguments)
    if lookup.case is None:
        return _err("list_evidence", lookup.error or "case unavailable", status=lookup.status)
    case = lookup.case
    text, sources = await retrieval.evidence_digest(
        ctx.session, case, limit=_limit(arguments.get("limit"), retrieval.EVIDENCE_LIMIT, 50)
    )
    return _ok("list_evidence", {"text": text}, sources, status=CASE_FOUND_WITH_DATA)


async def tool_get_entity(ctx: ToolContext, arguments: dict[str, Any]) -> ToolExecutionResult:
    raw_id = str(arguments.get("entity_id", ""))
    try:
        entity_uuid = uuid.UUID(raw_id)
    except ValueError:
        return _err("get_entity", "entity_id is not a valid identifier")
    entity = await ctx.session.get(Entity, entity_uuid)
    if entity is None:
        return _err("get_entity", "entity not found")
    lookup = await _lookup_case(ctx, {"case_id": entity.case_id})
    if lookup.case is None:
        return _err("get_entity", lookup.error or "access denied", status=lookup.status)
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
    return _ok("get_entity", payload, sources, status=CASE_FOUND_WITH_DATA)


async def tool_get_timeline(ctx: ToolContext, arguments: dict[str, Any]) -> ToolExecutionResult:
    lookup = await _lookup_case(ctx, arguments)
    if lookup.case is None:
        return _err("get_timeline", lookup.error or "case unavailable", status=lookup.status)
    case = lookup.case
    text, sources = await retrieval.timeline_digest(
        ctx.session, case, limit=_limit(arguments.get("limit"), retrieval.TIMELINE_LIMIT, 50)
    )
    return _ok("get_timeline", {"text": text}, sources, status=CASE_FOUND_WITH_DATA)


async def tool_get_analytics_summary(
    ctx: ToolContext, arguments: dict[str, Any]
) -> ToolExecutionResult:
    lookup = await _lookup_case(ctx, arguments)
    if lookup.case is None:
        return _err(
            "get_analytics_summary",
            lookup.error or "case unavailable",
            status=lookup.status,
        )
    case = lookup.case
    metrics_text, metric_sources = await retrieval.analytics_digest(ctx.session, case)
    graph_text, graph_sources = await retrieval.graph_relationships_digest(ctx.session, case)
    return _ok(
        "get_analytics_summary",
        {"metrics": metrics_text, "graph": graph_text},
        metric_sources + graph_sources,
        status=CASE_FOUND_WITH_DATA,
    )


async def tool_rank_entities(
    ctx: ToolContext, arguments: dict[str, Any]
) -> ToolExecutionResult:
    """Authoritative top-N entity ranking — deterministic, case-scoped.

    The model must call this instead of eyeballing the entities digest for
    questions like "most connected entity" or "highest PageRank". It returns a
    typed record with the exact metric, definition and ranked entity ids.
    """
    lookup = await _lookup_case(ctx, arguments)
    if lookup.case is None:
        return _err("rank_entities", lookup.error or "case unavailable", status=lookup.status)
    case = lookup.case
    metric = str(arguments.get("metric", "relationship_count")).strip()
    raw_top = arguments.get("top_n", ranking.DEFAULT_TOP_N)
    try:
        top_n = int(raw_top)
    except (TypeError, ValueError):
        return _err("rank_entities", "top_n must be an integer", status=LOOKUP_ERROR)
    try:
        record = await ranking.rank_entities(
            ctx.session, str(case.id), metric=metric, top_n=top_n
        )
    except ranking.UnsupportedMetricError as exc:
        return _err("rank_entities", str(exc))

    # Cite the top entities so every ranked id resolves to a real, authorized
    # record. The model explains these; it cannot invent rows.
    sources = [
        SourceRef(
            type="entity",
            id=row["entity_id"],
            label=str(row["label"])[:80],
            url=f"/cases/{case.id}/entities",
        )
        for row in record["results"]
    ]
    payload = {
        "text": _format_ranking(record),
        "record": record,
    }
    return _ok("rank_entities", payload, sources)


def _format_ranking(record: dict[str, Any]) -> str:
    """Compact, unambiguous text rendering of an authoritative ranking."""
    header = (
        f"metric={record['metric']} ({record['metric_definition']}) "
        f"unit={record['unit']} total_entities={record['total_entities']}"
    )
    lines = [header]
    for row in record["results"]:
        lines.append(
            f"{row['rank']}. {row['label']} (entity_id={row['entity_id']}) "
            f"{record['metric']}={row['value']}"
        )
    if record["total_entities"] == 0:
        lines.append("(no active entities in this case)")
    return "\n".join(lines)


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
                "number. Pass `query` (keywords) or a case identifier "
                "(`case_id`/`case_number` — a UUID, case number like "
                "SHOW-2026-001, or an exact case name). Returns matching cases "
                "with case_id, number, title, status; use that case_id for the "
                "other case tools."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "keywords or case number"},
                    "case_id": {
                        "type": "string",
                        "description": (
                            "optional: a case UUID, case number, or exact case name"
                        ),
                    },
                },
            },
            handler=tool_search_cases,
        ),
        ToolSpec(
            name="get_case_summary",
            description=(
                "Fetch the summary and record counts for one authorized case. "
                "`case_id` accepts a case UUID, a public case number (e.g. "
                "SHOW-2026-001), or an exact case name. Returns an explicit "
                "status: case_found_with_data, case_found_but_empty, "
                "case_not_found_or_not_accessible, case_ambiguous, or lookup_error."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "string",
                        "description": "case UUID, case number, or exact case name",
                    }
                },
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
            name="rank_entities",
            description=(
                "Authoritative top-N entity ranking for one authorized case, "
                "computed deterministically in the backend. Use this for any "
                "question about the most/least connected entity, highest "
                "PageRank, or top-N entities by relationship count or degree. "
                "Returns the exact metric, its definition, and ranked entity "
                "ids with values. Never guess a ranking from other text."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "case_id": {"type": "string", "description": "case UUID"},
                    "metric": {
                        "type": "string",
                        "enum": [
                            "relationship_count",
                            "distinct_neighbors",
                            "pagerank",
                            "degree",
                        ],
                        "description": "which measure to rank by",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "how many entities to return (default 5)",
                    },
                },
                "required": ["case_id"],
            },
            handler=tool_rank_entities,
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
