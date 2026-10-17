"""DerivedArtifact persistence: idempotent recording, scoped reads, review.

Recording is content-addressed: the payload is canonically hashed and the
(case, kind, hash) triple is unique, so a retried derivation returns the
existing artifact instead of duplicating accepted output. Review is a guarded
one-way transition (pending_review -> approved | rejected) requiring the
caller to have already passed its permission check; the route writes the
append-only audit entry alongside it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DerivedArtifact
from app.models.derived_artifact import (
    DERIVED_ARTIFACT_KINDS,
    DERIVED_ARTIFACT_ORIGINS,
    DERIVED_ARTIFACT_STATUSES,
    DERIVED_ARTIFACT_VALIDATION,
)
from app.services.structured_extraction import canonical_hash


class InvalidArtifactReview(ValueError):
    """Raised when a review decision cannot apply to the artifact's state."""


async def record_artifact(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    kind: str,
    origin: str,
    payload: dict[str, object],
    evidence_file_id: uuid.UUID | None = None,
    source_record_id: uuid.UUID | None = None,
    source_locator: dict[str, object] | None = None,
    validation_status: str = "valid",
    validation_errors: list[dict[str, object]] | None = None,
    parser_version: str = "deterministic:1",
    prompt_version: str | None = None,
    model_profile: str | None = None,
    analysis_job_id: uuid.UUID | None = None,
    parent_artifact_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
    status: str = "pending_review",
) -> tuple[DerivedArtifact, bool]:
    """Persist one derived artifact. Returns ``(artifact, created)``.

    ``created=False`` means an identical payload (same case, kind, content
    hash) was already recorded - the caller must not treat the derivation as a
    new finding. Validation of vocabularies happens before any write so an
    invalid artifact can never reach the table.
    """
    if kind not in DERIVED_ARTIFACT_KINDS:
        raise ValueError(f"unknown derived artifact kind {kind!r}")
    if origin not in DERIVED_ARTIFACT_ORIGINS:
        raise ValueError(f"unknown derived artifact origin {origin!r}")
    if status not in DERIVED_ARTIFACT_STATUSES:
        raise ValueError(f"unknown derived artifact status {status!r}")
    if validation_status not in DERIVED_ARTIFACT_VALIDATION:
        raise ValueError(f"unknown validation status {validation_status!r}")

    content_hash = canonical_hash(payload)
    existing = await session.execute(
        select(DerivedArtifact).where(
            DerivedArtifact.case_id == str(case_id),
            DerivedArtifact.kind == kind,
            DerivedArtifact.content_hash == content_hash,
        )
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        return row, False

    artifact = DerivedArtifact(
        case_id=str(case_id),
        kind=kind,
        origin=origin,
        status=status,
        validation_status=validation_status,
        evidence_file_id=str(evidence_file_id) if evidence_file_id is not None else None,
        source_record_id=str(source_record_id) if source_record_id is not None else None,
        source_locator=source_locator,
        payload=payload,
        content_hash=content_hash,
        parser_version=parser_version,
        prompt_version=prompt_version,
        model_profile=model_profile,
        analysis_job_id=str(analysis_job_id) if analysis_job_id is not None else None,
        validation_errors=validation_errors,
        parent_artifact_id=str(parent_artifact_id) if parent_artifact_id is not None else None,
        created_by=str(created_by) if created_by is not None else None,
    )
    session.add(artifact)
    await session.flush()
    return artifact, True


async def review_artifact(
    session: AsyncSession,
    *,
    artifact: DerivedArtifact,
    decision: str,
    reviewer_id: uuid.UUID,
    note: str | None = None,
) -> DerivedArtifact:
    """Apply a human review decision. Only ``pending_review`` is reviewable and
    decisions are one-shot (no flip-flopping without a new derivation)."""
    if decision not in ("approved", "rejected"):
        raise InvalidArtifactReview(f"unknown review decision {decision!r}")
    if artifact.status != "pending_review":
        raise InvalidArtifactReview(
            f"artifact is {artifact.status!r}; only pending_review artifacts can be reviewed"
        )
    artifact.status = decision
    artifact.reviewed_by = str(reviewer_id)
    artifact.reviewed_at = datetime.now(UTC)
    if note is not None:
        artifact.review_note = note
    await session.flush()
    return artifact


async def get_artifact(
    session: AsyncSession, case_id: uuid.UUID, artifact_id: uuid.UUID
) -> DerivedArtifact | None:
    """Case-scoped fetch (cross-case ids simply do not resolve)."""
    result = await session.execute(
        select(DerivedArtifact).where(
            DerivedArtifact.id == artifact_id,
            DerivedArtifact.case_id == str(case_id),
        )
    )
    return result.scalar_one_or_none()


async def list_artifacts(
    session: AsyncSession,
    case_id: uuid.UUID,
    *,
    kind: str | None = None,
    status: str | None = None,
    validation_status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[DerivedArtifact], int]:
    """Case-scoped listing with filters (used by the Evidence Intelligence UI).

    Cross-case candidates (``cross_case_link``) are deliberately never returned
    here: their payloads reference several cases at once, so an unscoped read
    would leak an inaccessible case's identifiers. They are read only through
    the dedicated scope-checked ``/cross-case/candidates`` endpoint.
    """
    query = (
        select(DerivedArtifact)
        .where(
            DerivedArtifact.case_id == str(case_id),
            DerivedArtifact.kind != "cross_case_link",
        )
    )
    if kind is not None:
        query = query.where(DerivedArtifact.kind == kind)
    if status is not None:
        query = query.where(DerivedArtifact.status == status)
    if validation_status is not None:
        query = query.where(DerivedArtifact.validation_status == validation_status)
    count_query = select(func.count()).select_from(query.subquery())
    total = int((await session.execute(count_query)).scalar_one())
    result = await session.execute(
        query.order_by(DerivedArtifact.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars()), total
