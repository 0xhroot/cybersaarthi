"""Entity resolution review: accept / reject / merge decision orchestration."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiHTTPException
from app.models import Entity, EntityAlias, EntityCandidate, EntityMatch, Relationship


async def _load_match(
    session: AsyncSession,
    case_id: uuid.UUID,
    match_id: uuid.UUID,
) -> EntityMatch:
    result = await session.execute(
        select(EntityMatch).where(
            EntityMatch.id == str(match_id),
            EntityMatch.case_id == str(case_id),
        )
    )
    match = result.scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} not found")
    if match.status != "review":
        raise ApiHTTPException(409, "MATCH_NOT_REVIEW", "match is not in review status")
    return match


async def accept_match(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    match_id: uuid.UUID,
) -> EntityMatch:
    match = await _load_match(session, case_id, match_id)
    if match.target_entity_id is None:
        raise ApiHTTPException(400, "MATCH_NO_TARGET", "match has no target entity to accept")
    match.status = "active"
    match.decision = "auto_match"

    candidate = await session.get(EntityCandidate, match.source_candidate_id)
    if candidate:
        candidate.entity_id = match.target_entity_id
        candidate.resolution_status = "auto_match"

    target = await session.get(Entity, match.target_entity_id)
    if target and candidate:
        from app.services.resolution import _context_signals, build_record_context, merge_signals

        new_signals = [candidate.raw_value]
        merged = merge_signals(_context_signals(target.context), new_signals)
        target.context = build_record_context(merged)

    await session.flush()
    return match


async def reject_match(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    match_id: uuid.UUID,
) -> EntityMatch:
    match = await _load_match(session, case_id, match_id)
    match.status = "rejected"
    match.decision = "no_match"

    candidate = await session.get(EntityCandidate, match.source_candidate_id)
    if candidate:
        candidate.resolution_status = "no_match"

    await session.flush()
    return match


async def merge_entities(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    primary_entity_id: uuid.UUID,
    merge_entity_id: uuid.UUID,
) -> Entity:
    if primary_entity_id == merge_entity_id:
        raise ApiHTTPException(400, "MERGE_SAME_ENTITY", "cannot merge an entity with itself")

    primary = await session.get(Entity, primary_entity_id)
    merge = await session.get(Entity, merge_entity_id)
    if primary is None or str(primary.case_id) != str(case_id):
        raise ApiHTTPException(404, "PRIMARY_NOT_FOUND", "primary entity not found in case")
    if merge is None or str(merge.case_id) != str(case_id):
        raise ApiHTTPException(404, "MERGE_NOT_FOUND", "entity to merge not found in case")
    if primary.status == "merged":
        raise ApiHTTPException(409, "PRIMARY_IS_MERGED", "primary entity is already merged")
    if primary.entity_type != merge.entity_type:
        raise ApiHTTPException(400, "TYPE_MISMATCH", "cannot merge entities of different types")

    aliases = list(
        (
            await session.execute(select(EntityAlias).where(EntityAlias.entity_id == str(merge.id)))
        ).scalars()
    )
    for alias in aliases:
        alias.entity_id = str(primary.id)

    rels = list(
        (
            await session.execute(
                select(Relationship).where(
                    (Relationship.source_entity_id == str(merge.id))
                    | (Relationship.target_entity_id == str(merge.id))
                )
            )
        ).scalars()
    )
    for rel in rels:
        if str(rel.source_entity_id) == str(merge.id):
            rel.source_entity_id = str(primary.id)
        if str(rel.target_entity_id) == str(merge.id):
            rel.target_entity_id = str(primary.id)

    merge.status = "merged"
    merge.merged_into_id = str(primary.id)
    await session.flush()
    return primary
