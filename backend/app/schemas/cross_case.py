"""Schemas: cross-case pattern discovery (phase 4, feature B).

Submission takes an explicit, bounded, fully authorized scope; candidate reads
are filtered through the same per-response scope recheck, so a payload that
leaves this module can only ever describe cases the caller may already read.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.evidence_intelligence import DerivedArtifactOut


class CrossCaseDiscoverRequest(BaseModel):
    """One bounded cross-case discovery run.

    ``anchor_case_id`` is the case the job row is anchored to (``AnalysisJob``
    has a NOT NULL case constraint) and must itself be part of ``case_ids``:
    discovery always runs over an explicit scope that includes the requesting
    case, never over "every case I can see".
    """

    anchor_case_id: UUID
    case_ids: list[UUID] = Field(min_length=2)


class CrossCaseCandidateListResponse(BaseModel):
    """Authorized, scope-rechecked cross-case candidates for one anchor case.

    ``total`` counts only candidates whose *entire* scope (anchor plus every
    side) is visible to the caller right now; candidates touching an
    inaccessible case are omitted entirely - not redacted, not counted.
    """

    items: list[DerivedArtifactOut]
    total: int
    anchor_case_id: UUID
    crosscase_rules_version: str
    graph_freshness_note: str
