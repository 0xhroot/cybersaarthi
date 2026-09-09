"""Unit coverage for the graph projection service (no infrastructure needed).

A11: the relationship label is the only interpolated Cypher fragment, so it is
validated against the allowlist before any statement is built.
"""

from __future__ import annotations

import uuid

import pytest
from app.models import Relationship
from app.models.relationship import RELATIONSHIP_TYPES
from app.services.graph_sync import _assert_legal_relationship_types


def _payload(rel_type: str) -> list[dict[str, object]]:
    rel = Relationship(
        id=uuid.uuid4(),
        case_id=str(uuid.uuid4()),
        source_entity_id=uuid.uuid4(),
        target_entity_id=uuid.uuid4(),
        relationship_type=rel_type,
    )
    return [
        {
            "id": str(rel.id),
            "case_id": str(rel.case_id),
            "source": str(rel.source_entity_id),
            "target": str(rel.target_entity_id),
            "type": rel.relationship_type.upper(),
            "confidence": rel.confidence,
            "explanation": rel.explanation,
        }
    ]


def test_relationship_label_allowlist_rejects_injection() -> None:
    """A non-registered label must raise before any Cypher is written (A11)."""
    with pytest.raises(ValueError, match="illegal relationship type"):
        _assert_legal_relationship_types(_payload("DROP INDEX n; MERGE"))


def test_relationship_label_allowlist_accepts_registered_types() -> None:
    """Every relationship type known to the model passes the allowlist."""
    for rtype in RELATIONSHIP_TYPES:
        _assert_legal_relationship_types(_payload(rtype))
