"""Authorization-first retrieval for AI prompts and tools.

Every function here takes an already-validated ``Case`` row (loaded through
``get_case_or_404``) or an already-validated user. Tool arguments coming from
the model are re-checked in ``tools.py`` before these helpers run — nothing in
this module trusts model output as an access-control input.

Retrieved text is capped and formatted as DATA blocks: evidence summaries use
metadata only (filenames, hashes, timestamps) — raw binary contents are never
loaded into prompts.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import fence_data
from app.ai.schemas import SourceRef
from app.models import (
    Case,
    CaseMember,
    Entity,
    EvidenceFile,
    Finding,
    MetricResult,
    Relationship,
    Role,
    TimelineEvent,
    User,
    UserRole,
    Victim,
)

# Caps keep an 8B model inside a small per-slot context window with room to
# answer. Slots split the total context (--parallel), so stay conservative.
EVIDENCE_LIMIT = 15
ENTITIES_LIMIT = 15
TIMELINE_LIMIT = 10
FINDINGS_LIMIT = 8
VICTIMS_LIMIT = 6
METRICS_LIMIT = 12
CASE_SEARCH_LIMIT = 10
MAX_FIELD_CHARS = 300

logger = logging.getLogger(__name__)


def _clip(value: str | None, limit: int = MAX_FIELD_CHARS) -> str:
    if not value:
        return ""
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _iso(value: Any) -> str:
    return value.isoformat(sep=" ", timespec="seconds") if value is not None else ""


async def case_summary(
    session: AsyncSession, case: Case
) -> tuple[str, list[SourceRef], dict[str, int]]:
    """Compact case header plus record counts.

    Returns ``(text, sources, counts)``. ``counts`` lets callers distinguish a
    case that exists but is empty from one that carries records without
    re-querying.
    """
    case_id = str(case.id)

    async def count(model: Any) -> int:
        return int(
            (await session.execute(select(func.count(model.id)).where(model.case_id == case_id)))
            .scalar_one()
        )

    entity_count, evidence_count, finding_count, timeline_count = await asyncio.gather(
        count(Entity), count(EvidenceFile), count(Finding), count(TimelineEvent)
    )
    victim_count = int(
        (await session.execute(select(func.count(Victim.id)).where(Victim.case_id == case.id)))
        .scalar_one()
    )
    counts: dict[str, int] = {
        "entities": entity_count,
        "evidence": evidence_count,
        "findings": finding_count,
        "victims": victim_count,
        "timeline": timeline_count,
    }
    lines = [
        f"case_id: {case_id}",
        f"case_number: {case.case_number}",
        f"title: {_clip(case.title, 200)}",
        f"status: {case.status}",
        f"created: {_iso(case.created_at)}",
        f"updated: {_iso(case.updated_at)}",
        f"description: {_clip(case.description) or '(none)'}",
        f"counts: entities={entity_count} evidence={evidence_count} "
        f"findings={finding_count} victims={victim_count}",
    ]
    sources = [
        SourceRef(type="case", id=case_id, label=case.case_number, url=f"/cases/{case_id}")
    ]
    return "\n".join(lines), sources, counts


async def evidence_digest(
    session: AsyncSession, case: Case, limit: int = EVIDENCE_LIMIT
) -> tuple[str, list[SourceRef]]:
    """Evidence metadata only — never file contents."""
    rows = (
        (
            await session.execute(
                select(EvidenceFile)
                .where(EvidenceFile.case_id == str(case.id))
                .order_by(EvidenceFile.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return "No evidence files registered for this case.", []
    lines: list[str] = []
    sources: list[SourceRef] = []
    for row in rows:
        lines.append(
            f"- id={row.id} file={_clip(row.original_filename, 120)} "
            f"type={_clip(row.content_type, 80)} size={row.file_size}B "
            f"sha256={row.sha256[:16]}… uploaded={_iso(row.created_at)}"
        )
        sources.append(
            SourceRef(type="evidence", id=str(row.id), label=row.original_filename)
        )
    return "\n".join(lines), sources


async def entities_digest(
    session: AsyncSession, case: Case, limit: int = ENTITIES_LIMIT
) -> tuple[str, list[SourceRef]]:
    """Most-connected entities plus their relationship counts."""
    rows = (
        await session.execute(
            select(Entity, func.count(Relationship.id).label("rel_count"))
            .outerjoin(
                Relationship,
                (Relationship.case_id == str(case.id))
                & (
                    (Relationship.source_entity_id == Entity.id)
                    | (Relationship.target_entity_id == Entity.id)
                ),
            )
            .where(Entity.case_id == str(case.id), Entity.status == "active")
            .group_by(Entity.id)
            .order_by(func.count(Relationship.id).desc(), Entity.created_at.desc())
            .limit(limit)
        )
    ).all()
    if not rows:
        return "No active entities extracted for this case.", []
    lines: list[str] = []
    sources: list[SourceRef] = []
    for entity, rel_count in rows:
        lines.append(
            f"- id={entity.id} type={entity.entity_type} value={_clip(entity.display_value, 160)} "
            f"confidence={entity.confidence} relationships={int(rel_count)}"
        )
        sources.append(
            SourceRef(
                type="entity",
                id=str(entity.id),
                label=_clip(entity.display_value, 80),
                url=f"/cases/{case.id}/entities",
            )
        )
    return "\n".join(lines), sources


async def timeline_digest(
    session: AsyncSession, case: Case, limit: int = TIMELINE_LIMIT
) -> tuple[str, list[SourceRef]]:
    rows = (
        (
            await session.execute(
                select(TimelineEvent)
                .where(TimelineEvent.case_id == str(case.id))
                .order_by(TimelineEvent.occurred_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return "No timeline events recorded for this case.", []
    lines: list[str] = []
    sources: list[SourceRef] = []
    for row in rows:
        lines.append(
            f"- id={row.id} when={_iso(row.occurred_at)} kind={row.kind} "
            f"title={_clip(row.title, 160)} detail={_clip(row.description, 200) or '(none)'}"
        )
        sources.append(SourceRef(type="timeline", id=str(row.id), label=_clip(row.title, 80)))
    return "\n".join(lines), sources


async def findings_digest(
    session: AsyncSession, case: Case, limit: int = FINDINGS_LIMIT
) -> tuple[str, list[SourceRef]]:
    rows = (
        (
            await session.execute(
                select(Finding)
                .where(Finding.case_id == str(case.id))
                .order_by(Finding.score.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return "No findings recorded for this case.", []
    lines: list[str] = []
    sources: list[SourceRef] = []
    for row in rows:
        lines.append(
            f"- id={row.id} severity={row.severity} status={row.status} score={row.score:.2f} "
            f"type={row.finding_type} title={_clip(row.title, 160)} "
            f"summary={_clip(row.summary, 200)}"
        )
        sources.append(
            SourceRef(
                type="finding",
                id=str(row.id),
                label=_clip(row.title, 80),
                url=f"/cases/{case.id}/findings",
            )
        )
    return "\n".join(lines), sources


async def victims_digest(
    session: AsyncSession, case: Case, limit: int = VICTIMS_LIMIT
) -> tuple[str, list[SourceRef]]:
    rows = (
        (
            await session.execute(
                select(Victim)
                .where(Victim.case_id == case.id)
                .order_by(Victim.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return "No victims registered for this case.", []
    lines: list[str] = []
    sources: list[SourceRef] = []
    for row in rows:
        amount = row.amount_lost if row.amount_lost is not None else row.reported_amount
        incident = _clip(row.incident_type, 80) or "n/a"
        lines.append(
            f"- id={row.id} name={_clip(row.name, 120)} type={incident} "
            f"amount_lost={amount} {row.currency or ''} status={row.status}"
        )
        sources.append(SourceRef(type="victim", id=str(row.id), label=_clip(row.name, 80)))
    return "\n".join(lines), sources


async def analytics_digest(
    session: AsyncSession, case: Case, limit: int = METRICS_LIMIT
) -> tuple[str, list[SourceRef]]:
    rows = (
        await session.execute(
            select(MetricResult)
            .where(MetricResult.case_id == str(case.id))
            .order_by(MetricResult.metric_name, MetricResult.rank.is_(None), MetricResult.rank)
            .limit(limit)
        )
    ).scalars().all()
    if not rows:
        return "No graph analytics metrics computed for this case yet.", []
    lines: list[str] = []
    sources: list[SourceRef] = []
    for row in rows:
        lines.append(
            f"- metric={row.metric_name} entity_id={row.entity_id or '-'} "
            f"value={row.raw_value:.4f} score={row.normalized_score} rank={row.rank} "
            f"note={_clip(row.explanation, 120)}"
        )
        sources.append(
            SourceRef(type="metric", id=str(row.id), label=_clip(row.metric_name, 60))
        )
    return "\n".join(lines), sources


async def graph_relationships_digest(
    session: AsyncSession, case: Case, limit: int = 15
) -> tuple[str, list[SourceRef]]:
    """Relationship type histogram plus the strongest relationships."""
    hist = (
        await session.execute(
            select(Relationship.relationship_type, func.count(Relationship.id))
            .where(Relationship.case_id == str(case.id))
            .group_by(Relationship.relationship_type)
            .order_by(func.count(Relationship.id).desc())
        )
    ).all()
    if not hist:
        return "No relationships stored for this case.", []
    top = (
        (
            await session.execute(
                select(Relationship)
                .where(Relationship.case_id == str(case.id))
                .order_by(Relationship.confidence.desc().nullslast())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    lines = ["relationship counts by type:"]
    lines += [f"- {rtype}: {int(count)}" for rtype, count in hist[:12]]
    if top:
        lines.append("strongest relationships:")
        for rel in top:
            lines.append(
                f"- id={rel.id} type={rel.relationship_type} confidence={rel.confidence} "
                f"source={rel.source_entity_id} target={rel.target_entity_id}"
            )
    sources = [
        SourceRef(type="graph", id=str(case.id), label="case graph", url=f"/cases/{case.id}/graph")
    ]
    return "\n".join(lines), sources


async def build_case_context(
    session: AsyncSession,
    case: Case,
    *,
    include_evidence: bool = True,
    include_graph: bool = True,
    include_victims: bool = True,
    include_analytics: bool = False,
) -> tuple[str, list[SourceRef]]:
    """Assemble the fenced DATA block for one authorized case."""
    blocks: list[str] = []
    all_sources: list[SourceRef] = []

    summary_text, sources, _counts = await case_summary(session, case)
    blocks.append(fence_data("case summary", summary_text))
    all_sources.extend(sources)

    if include_evidence:
        text, sources = await evidence_digest(session, case)
        blocks.append(fence_data("evidence metadata", text))
        all_sources.extend(sources)

    text, sources = await entities_digest(session, case)
    blocks.append(fence_data("entities", text))
    all_sources.extend(sources)

    text, sources = await findings_digest(session, case)
    blocks.append(fence_data("findings", text))
    all_sources.extend(sources)

    text, sources = await timeline_digest(session, case)
    blocks.append(fence_data("timeline", text))
    all_sources.extend(sources)

    if include_victims:
        text, sources = await victims_digest(session, case)
        blocks.append(fence_data("victims", text))
        all_sources.extend(sources)

    if include_graph:
        text, sources = await graph_relationships_digest(session, case)
        blocks.append(fence_data("graph", text))
        all_sources.extend(sources)

    if include_analytics:
        text, sources = await analytics_digest(session, case)
        blocks.append(fence_data("analytics", text))
        all_sources.extend(sources)

    return "\n\n".join(blocks), all_sources


async def _visibility_condition(
    session: AsyncSession, user: User
) -> Any | None:
    """Owner/member predicate for *user*; ``None`` means "every case" (admin).

    Single source of truth for case visibility, shared by the ``search_cases``
    tool and the case resolver so the AI can never observe a different case set
    than the normal case API (``app.api.routes.cases._case_filters``).
    """
    from app.core import rbac

    roles = list(
        (
            await session.execute(
                select(Role.name)
                .select_from(UserRole)
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.user_id == user.id)
            )
        ).scalars()
    )
    if any(rbac.is_admin_role(role) for role in roles):
        return None
    member_ids = select(CaseMember.case_id).where(CaseMember.user_id == user.id)
    return (Case.owner_id == user.id) | (Case.id.in_(member_ids))


@dataclass(slots=True)
class CaseResolution:
    """Outcome of resolving a user/model case reference to an authorized case.

    ``status`` is one of ``found`` / ``ambiguous`` / ``not_found`` / ``error``.
    ``not_found`` deliberately merges "no such case" with "not visible to this
    user" so a case existence oracle cannot be built through the tool.
    """

    status: str
    case: Case | None = None
    # Authorized matches only (already filtered by the visibility predicate).
    candidates: list[Case] = field(default_factory=list)
    error: str | None = None


async def resolve_case_reference(
    session: AsyncSession, user: User, reference: Any
) -> CaseResolution:
    """Resolve a case by internal UUID, public case number, or exact name.

    Authorization is applied *before* any case is returned: matches are scoped
    by the same owner/member/admin predicate the normal case API uses, so this
    can never disclose a case the caller may not read. A reference that exists
    but is not accessible resolves exactly like one that does not exist.
    Database failures surface as ``error`` — never as "not found".
    """
    ref = str(reference if reference is not None else "").strip()
    if not ref:
        return CaseResolution(status="error", error="case reference is empty")

    # Internal UUID path.
    try:
        parsed_uuid: uuid.UUID | None = uuid.UUID(ref)
    except ValueError:
        parsed_uuid = None

    try:
        condition = await _visibility_condition(session, user)
        if parsed_uuid is not None:
            stmt = select(Case).where(Case.id == parsed_uuid)
            if condition is not None:
                stmt = stmt.where(condition)
            case = (await session.execute(stmt)).scalar_one_or_none()
            if case is None:
                return CaseResolution(status="not_found")
            return CaseResolution(status="found", case=case)

        # Exact public case number (case-insensitive) — unique, at most one.
        stmt = select(Case).where(func.lower(Case.case_number) == ref.lower())
        if condition is not None:
            stmt = stmt.where(condition)
        case = (await session.execute(stmt)).scalar_one_or_none()
        if case is not None:
            return CaseResolution(status="found", case=case)

        # Exact case name/title (case-insensitive) — may be ambiguous.
        stmt = select(Case).where(func.lower(Case.title) == ref.lower())
        if condition is not None:
            stmt = stmt.where(condition)
        stmt = stmt.order_by(Case.created_at, Case.id).limit(8)
        matches = list((await session.execute(stmt)).scalars())
        if len(matches) == 1:
            return CaseResolution(status="found", case=matches[0])
        if len(matches) > 1:
            return CaseResolution(status="ambiguous", candidates=matches)
        return CaseResolution(status="not_found")
    except Exception:
        logger.exception("case reference lookup failed")
        return CaseResolution(status="error", error="case lookup failed")


async def accessible_cases(
    session: AsyncSession,
    user: User,
    *,
    query: str | None = None,
    limit: int = CASE_SEARCH_LIMIT,
) -> list[Case]:
    """Cases the user may read (owner, member, or admin) — used by search tool."""
    condition = await _visibility_condition(session, user)
    stmt = select(Case)
    if condition is not None:
        stmt = stmt.where(condition)
    if query:
        needle = query.strip()
        pattern = f"%{needle}%"
        cond = (Case.title.ilike(pattern)) | (Case.case_number.ilike(pattern))
        # A UUID query should match the internal id too, not only number/title.
        try:
            parsed = uuid.UUID(needle)
        except ValueError:
            parsed = None
        if parsed is not None:
            cond = cond | (Case.id == parsed)
        stmt = stmt.where(cond)
    cases = (
        (await session.execute(stmt.order_by(Case.updated_at.desc().nullslast()).limit(limit)))
        .scalars()
        .all()
    )
    return list(cases)


# -- post-generation claim validation (analysis mode) -----------------------

UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)
# Metric-number claims the model can state. Two shapes are recognized because
# models naturally echo the DATA line format instead of a synthetic grammar:
#   echo  (mandated by the analysis prompt, mirrors DATA verbatim):
#     metric=<name> entity_id=<entity_id> value=<value>   (score= accepted too;
#     `metric:` instead of `metric=` also occurs)
#   strict (earlier contract, kept for robustness):
#     metric:<name>@<entity_id> = <value>
# Both exist so numbers the model states can be machine-checked against
# metric_results after generation.
_UUID_BODY = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_NUM = r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
METRIC_CLAIM_RE = re.compile(
    rf"metric[=:]([a-z_]+)\s+entity_id=({_UUID_BODY})\s+(?:value|score)=({_NUM})",
    re.I,
)
METRIC_CLAIM_STRICT_RE = re.compile(
    rf"metric:([a-z_]+)@({_UUID_BODY})\s*=\s*({_NUM})",
    re.I,
)
CLAIM_LIST_LIMIT = 10


async def validate_cited_claims(
    session: AsyncSession,
    case: Case,
    answer: str,
    data_block: str,
    sources: list[SourceRef],
) -> dict[str, Any]:
    """Machine-check the ids and metric numbers the model cited.

    Two independent checks, both against what was actually retrieved for THIS
    authorized case (never against model output):

    - **id citations** — every UUID-shaped id in the answer must appear either
      in the DATA block that was shown to the model or in the response's
      source list; anything else is reported as ``unverified`` (review, not a
      verdict — the model may quote an id from a tool result we no longer
      hold).
    - **metric claims** — each quoted metric (``metric=<name> entity_id=<id>
      value=<v>`` echoing the DATA line, or the strict
      ``metric:<name>@<id> = <v>`` form) is looked up in ``metric_results``
      scoped to this case. Unknown name/entity pairs or values matching
      neither the raw value nor the normalized score (within rounding
      tolerance) are reported as ``mismatches``.

    Failures never raise: validation is advisory metadata on the response, and
    an empty/missing check is never dressed up as a pass.
    """
    cited = {m.group(0).lower() for m in UUID_RE.finditer(answer)}
    known = {m.group(0).lower() for m in UUID_RE.finditer(data_block)}
    known.update(s.id.lower() for s in sources)
    unverified = sorted(cited - known)

    claims: dict[tuple[str, str], list[float]] = {}
    for pattern in (METRIC_CLAIM_RE, METRIC_CLAIM_STRICT_RE):
        for match in pattern.finditer(answer):
            name, entity_id, value = (
                match.group(1),
                match.group(2).lower(),
                float(match.group(3)),
            )
            claims.setdefault((name, entity_id), []).append(value)

    mismatches: list[str] = []
    for (name, entity_id), values in claims.items():
        rows = (
            await session.execute(
                select(MetricResult.raw_value, MetricResult.normalized_score).where(
                    MetricResult.case_id == str(case.id),
                    MetricResult.metric_name == name,
                    MetricResult.entity_id == entity_id,
                )
            )
        ).all()
        if not rows:
            mismatches.append(
                f"metric:{name}@{entity_id}: no such metric for this case"
            )
            continue
        for value in values:
            matches = any(
                # DATA prints value with 4 decimals; require a near-exact echo
                # (1e-5 relative — a changed digit at the scale of the value is
                # flagged) or a match against the stored normalized score.
                abs(value - float(raw)) <= max(0.005, 1e-5 * abs(float(raw)))
                or abs(value - float(score)) <= 0.01
                for raw, score in rows
            )
            if not matches:
                sample = ", ".join(f"{float(r):.4f}" for r, _ in rows[:3])
                mismatches.append(
                    f"metric:{name}@{entity_id} = {value}: data says {sample}"
                )

    return {
        "cited_ids": len(cited),
        "verified_ids": len(cited) - len(unverified),
        "unverified_ids": unverified[:CLAIM_LIST_LIMIT],
        "metric_claims_checked": sum(len(v) for v in claims.values()),
        "metric_claims_mismatched": mismatches[:CLAIM_LIST_LIMIT],
    }
