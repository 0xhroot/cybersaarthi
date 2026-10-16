"""Server-side citation validation shared by every evidence-intelligence feature.

A citation is more than an ID that exists. Before any claim is surfaced, the
server checks that the referenced record:

1. has a well-formed id and a known kind,
2. exists,
3. belongs to the case being cited (or, in explicit cross-case mode, to a case
   the current principal can actually see - membership re-checked per call),
4. carries a valid source locator (the claimed field exists in the record),
5. supports the quoted value exactly (numbers as Decimals, dates normalized,
   text whitespace/case normalized - never substring-guessing).

The result is machine-readable codes; callers turn failing codes into review
flags. The model is never trusted to evaluate its own citations, and nothing
here grants the model database access - it is a server-side check over fixed
record kinds.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import is_admin_role
from app.models import (
    Case,
    CaseMember,
    DerivedArtifact,
    Entity,
    EvidenceFile,
    Finding,
    Hypothesis,
    Relationship,
    SourceRecord,
    TimelineEvent,
    User,
    UserRole,
)
from app.models.role import Role
from app.services.structured_extraction import values_equal

CITATION_KINDS = (
    "source_record",
    "evidence_file",
    "entity",
    "relationship",
    "finding",
    "timeline_event",
    "hypothesis",
    "derived_artifact",
)

# Citation kinds -> ORM model that backs them (scope rules handled per kind).
_KIND_MODELS = {
    "source_record": SourceRecord,
    "evidence_file": EvidenceFile,
    "entity": Entity,
    "relationship": Relationship,
    "finding": Finding,
    "timeline_event": TimelineEvent,
    "hypothesis": Hypothesis,
    "derived_artifact": DerivedArtifact,
}


@dataclass(frozen=True)
class CitationRef:
    """A citation exactly as it arrived (from model output or a client)."""

    kind: str
    id: str
    case_id: str | None = None
    locator: Mapping[str, Any] | None = None
    quote: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CitationCheck:
    """Outcome: ``ok`` is True only when every applicable check passed."""

    ok: bool
    codes: tuple[str, ...] = field(default_factory=tuple)
    resolved_case_id: str | None = None
    actual: dict[str, Any] | None = None


def preflight(ref: CitationRef) -> tuple[str, ...]:
    """Shape checks that need no database: well-formed id, known kind."""
    codes: list[str] = []
    try:
        uuid.UUID(ref.id)
    except (ValueError, AttributeError, TypeError):
        codes.append("citation_invalid_id")
    if ref.kind not in CITATION_KINDS:
        codes.append("citation_unknown_kind")
    return tuple(codes)


async def case_visible_to(session: AsyncSession, user: User, case_id: uuid.UUID) -> bool:
    """Independent, per-call case visibility recheck (admin OR owner OR member).

    Deliberately re-derives roles from the database instead of trusting a
    request-scoped cache: authorization must hold even for previously derived
    results after a permission change.
    """
    role_rows = await session.execute(
        select(Role.name)
        .select_from(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user.id)
    )
    if any(is_admin_role(name) for name in role_rows.scalars()):
        return True
    case = await session.get(Case, case_id)
    if case is None:
        return False
    if case.owner_id is not None and case.owner_id == user.id:
        return True
    membership = await session.execute(
        select(CaseMember).where(CaseMember.case_id == str(case_id), CaseMember.user_id == user.id)
    )
    return membership.scalar_one_or_none() is not None


async def _scope_case_id(session: AsyncSession, kind: str, row: Any) -> str:
    """Case that owns *row* (SourceRecord resolves through its evidence file)."""
    if kind == "source_record":
        evidence = await session.get(EvidenceFile, row.evidence_file_id)
        # Orphaned record (file soft-deleted): scope is unknown -> no case.
        return str(evidence.case_id) if evidence is not None else ""
    return str(row.case_id)


async def validate_citation(
    session: AsyncSession,
    *,
    user: User,
    case_id: uuid.UUID,
    ref: CitationRef,
    allow_cross_case: bool = False,
) -> CitationCheck:
    """Full citation check for a claim made against *case_id*.

    With ``allow_cross_case=False`` (the default) a record outside *case_id*
    fails as ``citation_wrong_case`` even if the user can see its real case -
    cross-case claims must opt in explicitly, and then only for cases the user
    passes :func:`case_visible_to`.
    """
    shape = preflight(ref)
    if shape:
        return CitationCheck(ok=False, codes=shape)

    model = _KIND_MODELS[ref.kind]
    # Row type varies per citation kind; every access below is guarded by the
    # kind-specific branches, so it stays loosely typed on purpose.
    row: Any = await session.get(model, uuid.UUID(ref.id))
    if row is None:
        return CitationCheck(ok=False, codes=("citation_record_missing",))

    scope = await _scope_case_id(session, ref.kind, row)
    expected = str(case_id)
    if not scope:
        return CitationCheck(ok=False, codes=("citation_wrong_case",), resolved_case_id=None)

    if ref.case_id is not None and str(ref.case_id) != scope:
        return CitationCheck(ok=False, codes=("citation_case_mismatch",), resolved_case_id=scope)

    if scope != expected:
        if not allow_cross_case:
            return CitationCheck(ok=False, codes=("citation_wrong_case",), resolved_case_id=scope)
        if not await case_visible_to(session, user, uuid.UUID(scope)):
            return CitationCheck(
                ok=False, codes=("citation_unauthorized",), resolved_case_id=scope
            )

    codes: list[str] = []
    actual: dict[str, Any] | None = None

    # Locator: for record-backed citations the claimed field must exist.
    if ref.kind == "source_record":
        raw: Mapping[str, Any] = row.raw_data or {}
        if ref.locator is not None:
            claimed_field = ref.locator.get("field")
            if not isinstance(claimed_field, str) or claimed_field not in raw:
                codes.append("citation_locator_invalid")
        if ref.quote is not None:
            quote_field = ref.quote.get("field")
            if not isinstance(quote_field, str) or quote_field not in raw:
                codes.append("citation_locator_invalid")
            else:
                actual_value = raw[quote_field]
                actual = {quote_field: actual_value}
                if "value" in ref.quote and not values_equal(ref.quote["value"], actual_value):
                    codes.append("citation_value_mismatch")
    elif ref.kind == "derived_artifact":
        payload: Mapping[str, Any] = row.payload or {}
        if ref.locator is not None:
            claimed_field = ref.locator.get("field")
            if not isinstance(claimed_field, str) or claimed_field not in payload:
                codes.append("citation_locator_invalid")
        if ref.quote is not None:
            quote_field = ref.quote.get("field")
            if not isinstance(quote_field, str) or quote_field not in payload:
                codes.append("citation_locator_invalid")
            else:
                actual_value = payload[quote_field]
                actual = {quote_field: actual_value}
                if "value" in ref.quote and not values_equal(ref.quote["value"], actual_value):
                    codes.append("citation_value_mismatch")
    elif ref.quote is not None:
        # Quoting structured columns (title, status...) is not a supported
        # citation style; the claim must cite a record-backed locator instead.
        codes.append("citation_quote_unsupported")

    return CitationCheck(
        ok=not codes,
        codes=tuple(codes),
        resolved_case_id=scope,
        actual=actual,
    )


def flags_from_checks(results: Mapping[str, CitationCheck]) -> list[dict[str, Any]]:
    """Render failing citation checks as reviewer-facing flag records."""
    flags: list[dict[str, Any]] = []
    for claim_id, result in results.items():
        if result.ok:
            continue
        flags.append(
            {
                "claim": claim_id,
                "codes": list(result.codes),
                "resolved_case_id": result.resolved_case_id,
            }
        )
    return flags
