"""Deterministic evidence integrity verification (feature 9, hash half).

The comparison itself is pure and boring on purpose: exact string equality of
lowercased hex digests over the *original stored bytes*, with explicit states
for every way the check cannot conclude (missing bytes, missing recorded
hash, unsupported algorithm). Nothing here ever writes to the evidence row or
the object store - a verification observes, it does not "repair".

Scope of the claim: a ``match`` proves the compared bytes hash to the recorded
digest. It does NOT prove authentic collection, lawful handling or an
unbroken historical chain of custody; those are custody-event and human-review
questions (``app.services.custody``).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.codes import CODE_EVIDENCE_NOT_FOUND, CODE_EVIDENCE_UNAVAILABLE
from app.models import EvidenceFile
from app.services import artifacts as artifacts_svc
from app.services import audit as audit_svc
from app.services.validation import fingerprint

if TYPE_CHECKING:
    from app.db.storage import Storage

SUPPORTED_HASH_ALGORITHMS = frozenset({"sha256"})
_ALGORITHM_ALIASES = {
    "sha256": "sha256",
    "sha-256": "sha256",
    "sha_256": "sha256",
}

# Result statuses (typed, stable for clients and fixtures).
STATUS_MATCH = "match"
STATUS_MISMATCH = "mismatch"
STATUS_MISSING_EXPECTED = "missing_expected"
STATUS_MISSING_SOURCE = "missing_source"
STATUS_UNSUPPORTED_ALGORITHM = "unsupported_algorithm"


class IntegrityRejected(ValueError):
    """Verification cannot be attempted; ``code`` is the typed API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class HashComparison:
    """Outcome of one deterministic hash comparison."""

    status: str
    algorithm: str | None
    expected: str | None
    calculated: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "algorithm": self.algorithm,
            "expected_sha256": self.expected,
            "calculated_sha256": self.calculated,
        }


def normalize_algorithm(algorithm: str) -> str | None:
    """Canonical name, or None when this deployment cannot compute it."""
    return _ALGORITHM_ALIASES.get(algorithm.strip().lower())


def compare_hashes(algorithm: str, expected: str | None, calculated: str | None) -> HashComparison:
    """Compare two digests with explicit, deterministic outcomes.

    - unknown/unsupported algorithm -> ``unsupported_algorithm`` (never guessed)
    - no computed bytes digest -> ``missing_source``
    - empty/absent recorded digest -> ``missing_expected``
    - otherwise exact lowercase-hex equality -> ``match`` | ``mismatch``
    """
    normalized = normalize_algorithm(algorithm)
    if normalized is None:
        return HashComparison(STATUS_UNSUPPORTED_ALGORITHM, algorithm, expected, calculated)
    if calculated is None:
        return HashComparison(STATUS_MISSING_SOURCE, normalized, expected, None)
    if expected is None or not expected.strip():
        return HashComparison(STATUS_MISSING_EXPECTED, normalized, None, calculated)
    exp = expected.strip().lower()
    calc = calculated.strip().lower()
    status = STATUS_MATCH if exp == calc else STATUS_MISMATCH
    return HashComparison(status, normalized, exp, calc)


async def _scoped_evidence(
    session: AsyncSession, case_id: uuid.UUID, evidence_id: uuid.UUID
) -> EvidenceFile | None:
    result = await session.execute(
        select(EvidenceFile).where(
            EvidenceFile.id == str(evidence_id),
            EvidenceFile.case_id == str(case_id),
        )
    )
    return result.scalar_one_or_none()


async def verify_evidence_integrity(
    session: AsyncSession,
    *,
    storage: Storage,
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> dict[str, Any]:
    """Hash-verify one evidence item against its original object bytes.

    Returns the full result (including ``missing_source``/``missing_expected``
    outcomes - which are results, not errors) and records it as a deterministic
    ``recorded`` artifact plus an ``integrity.verified`` audit entry. The
    evidence row and its bytes are never modified.
    """
    evidence = await _scoped_evidence(session, case_id, evidence_id)
    if evidence is None:
        raise IntegrityRejected(CODE_EVIDENCE_NOT_FOUND, "evidence not found in this case")
    if evidence.deleted_at is not None:
        raise IntegrityRejected(
            CODE_EVIDENCE_UNAVAILABLE,
            "evidence is deleted; restore it before verification",
        )

    started = time.monotonic()
    object_present = await asyncio.to_thread(storage.exists, evidence.stored_key)
    calculated: str | None = None
    size_bytes: int | None = None
    if object_present:
        raw = await asyncio.to_thread(storage.download, evidence.stored_key)
        calculated = fingerprint(raw)
        size_bytes = len(raw)
    comparison = compare_hashes("sha256", evidence.sha256, calculated)
    duration_ms = int((time.monotonic() - started) * 1000)
    verified_at = datetime.now(UTC)

    payload: dict[str, Any] = {
        "type": "hash_verification",
        "rule": "integrity.hash_comparison",
        "evidence_file_id": str(evidence_id),
        "file_size_bytes": size_bytes,
        "duration_ms": duration_ms,
        "verified_at": verified_at.isoformat(),
        **comparison.as_dict(),
    }
    artifact, _ = await artifacts_svc.record_artifact(
        session,
        case_id=case_id,
        kind="custody_finding",
        origin="deterministic",
        payload=payload,
        evidence_file_id=evidence_id,
        validation_status="valid",
        parser_version="deterministic:1",
        created_by=actor_id,
        # Facts never queue for approval: review applies to findings, not to
        # the observed result of a hash comparison.
        status="recorded",
    )
    await audit_svc.record_audit(
        session,
        actor_id=actor_id,
        action="integrity.verified",
        resource_type="evidence_file",
        resource_id=str(evidence_id),
        case_id=case_id,
        metadata={"status": comparison.status, "algorithm": comparison.algorithm},
    )
    await session.commit()
    return {
        "evidence_id": str(evidence_id),
        "artifact_id": str(artifact.id),
        "verified_at": verified_at.isoformat(),
        "object_present": object_present,
        "file_size_bytes": size_bytes,
        "duration_ms": duration_ms,
        **comparison.as_dict(),
    }
