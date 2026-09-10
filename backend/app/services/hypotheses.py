"""Hypothesis service: CRUD + evidence linking + status lifecycle."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiHTTPException
from app.models import Hypothesis

_CODE_HYPOTHESIS_NOT_FOUND = "HYPOTHESIS_NOT_FOUND"
_CODE_HYPOTHESIS_INVALID_TRANSITION = "HYPOTHESIS_INVALID_TRANSITION"


_VALID_TRANSITIONS: dict[str, set[str]] = {
    "proposed": {"under_review", "dismissed"},
    "under_review": {"supported", "contradicted", "dismissed"},
    "supported": {"concluded", "contradicted"},
    "contradicted": {"under_review", "dismissed"},
    "dismissed": {"proposed"},
    "concluded": {"proposed"},
}


async def create_hypothesis(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    kind: str,
    title: str,
    statement: str,
    confidence: float | None,
    notes: str | None,
    submitted_by: uuid.UUID | None,
) -> Hypothesis:
    hypothesis = Hypothesis(
        case_id=str(case_id),
        kind=kind,
        title=title,
        statement=statement,
        confidence=confidence,
        notes=notes,
        submitted_by=str(submitted_by) if submitted_by else None,
        supporting_evidence=[],
        contradicting_evidence=[],
        related_entities=[],
        related_relationships=[],
        evidence_weight=0,
        status="proposed",
    )
    session.add(hypothesis)
    await session.flush()
    return hypothesis


async def get_hypothesis(
    session: AsyncSession,
    hypothesis_id: uuid.UUID,
) -> Hypothesis | None:
    return await session.get(Hypothesis, hypothesis_id)


async def list_hypotheses(
    *,
    session: AsyncSession,
    case_id: uuid.UUID,
    kind: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Hypothesis], int]:
    where = [Hypothesis.case_id == str(case_id)]
    if kind is not None:
        where.append(Hypothesis.kind == kind)
    if status is not None:
        where.append(Hypothesis.status == status)
    count_q = select(func.count()).select_from(Hypothesis).where(*where)
    total = (await session.execute(count_q)).scalar_one()
    q = (
        select(Hypothesis)
        .where(*where)
        .order_by(Hypothesis.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list((await session.execute(q)).scalars())
    return rows, total


async def transition_hypothesis_status(
    *,
    session: AsyncSession,
    hypothesis: Hypothesis,
    new_status: str,
) -> Hypothesis:
    allowed = _VALID_TRANSITIONS.get(hypothesis.status, set())
    if new_status not in allowed:
        raise ApiHTTPException(
            409,
            _CODE_HYPOTHESIS_INVALID_TRANSITION,
            f"cannot transition from '{hypothesis.status}' to '{new_status}'",
        )
    hypothesis.status = new_status
    await session.flush()
    return hypothesis


async def link_evidence_to_hypothesis(
    *,
    session: AsyncSession,
    hypothesis: Hypothesis,
    evidence_id: uuid.UUID,
    support: bool,
) -> Hypothesis:
    field = "supporting_evidence" if support else "contradicting_evidence"
    current: list[str] = getattr(hypothesis, field) or []
    current.append(str(evidence_id))
    setattr(hypothesis, field, current)
    hypothesis.evidence_weight = len(hypothesis.supporting_evidence or []) - len(
        hypothesis.contradicting_evidence or []
    )
    await session.flush()
    return hypothesis


async def unlink_evidence_from_hypothesis(
    *,
    session: AsyncSession,
    hypothesis: Hypothesis,
    evidence_id: uuid.UUID,
) -> Hypothesis:
    for field in ("supporting_evidence", "contradicting_evidence"):
        current: list[str] = getattr(hypothesis, field) or []
        setattr(hypothesis, field, [eid for eid in current if eid != str(evidence_id)])
    hypothesis.evidence_weight = len(hypothesis.supporting_evidence or []) - len(
        hypothesis.contradicting_evidence or []
    )
    await session.flush()
    return hypothesis


async def delete_hypothesis(
    *,
    session: AsyncSession,
    hypothesis: Hypothesis,
) -> None:
    await session.delete(hypothesis)
    await session.flush()
