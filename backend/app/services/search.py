"""Case-scoped unified search across entities, evidence, relationships, findings."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, EntityAlias, EvidenceFile, Finding


@dataclass(frozen=True)
class SearchResult:
    kind: str
    id: str
    title: str
    subtitle: str | None
    url: str


@dataclass
class SearchResponse:
    items: list[SearchResult] = field(default_factory=list)
    total: int = 0


def _ilike_escape(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def search(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    query: str,
    limit: int = 50,
    offset: int = 0,
) -> SearchResponse:
    escaped = _ilike_escape(query)
    like = f"%{escaped}%"
    items: list[SearchResult] = []

    entity_q = (
        select(Entity)
        .where(
            Entity.case_id == str(case_id),
            or_(
                Entity.canonical_value.ilike(like, escape="\\"),
                Entity.display_value.ilike(like, escape="\\"),
            ),
        )
        .limit(limit - len(items))
        .offset(offset if len(items) == 0 else 0)
    )
    for e in (await session.execute(entity_q)).scalars():
        items.append(
            SearchResult(
                kind="entity",
                id=str(e.id),
                title=e.display_value,
                subtitle=e.entity_type,
                url=f"/entities/{e.id}",
            )
        )

    if len(items) < limit:
        alias_q = (
            select(EntityAlias)
            .join(Entity, Entity.id == EntityAlias.entity_id)
            .where(
                Entity.case_id == str(case_id),
                EntityAlias.alias_value.ilike(like, escape="\\"),
            )
            .limit(limit - len(items))
        )
        for alias in (await session.execute(alias_q)).scalars():
            items.append(
                SearchResult(
                    kind="entity",
                    id=str(alias.entity_id),
                    title=alias.alias_value,
                    subtitle="alias",
                    url=f"/entities/{alias.entity_id}",
                )
            )

    if len(items) < limit:
        evidence_q = (
            select(EvidenceFile)
            .where(
                EvidenceFile.case_id == str(case_id),
                EvidenceFile.original_filename.ilike(like, escape="\\"),
            )
            .limit(limit - len(items))
        )
        for ev in (await session.execute(evidence_q)).scalars():
            items.append(
                SearchResult(
                    kind="evidence",
                    id=str(ev.id),
                    title=ev.original_filename,
                    subtitle=ev.content_type,
                    url=f"/evidence/{ev.id}",
                )
            )

    if len(items) < limit:
        finding_q = (
            select(Finding)
            .where(
                Finding.case_id == str(case_id),
                or_(
                    Finding.title.ilike(like, escape="\\"),
                    Finding.summary.ilike(like, escape="\\"),
                ),
            )
            .limit(limit - len(items))
        )
        for f in (await session.execute(finding_q)).scalars():
            items.append(
                SearchResult(
                    kind="finding",
                    id=str(f.id),
                    title=f.title,
                    subtitle=f.finding_type,
                    url=f"/findings/{f.id}",
                )
            )

    return SearchResponse(items=items, total=len(items))
