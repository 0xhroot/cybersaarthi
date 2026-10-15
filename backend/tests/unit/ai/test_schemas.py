"""Unit tests: internal AI schemas (source refs, tool parsing helpers)."""

from __future__ import annotations

import pytest
from app.ai.schemas import (
    SOURCE_TYPES,
    ChatOutcome,
    SourceRef,
    ToolCallProposal,
    ToolExecutionResult,
)
from pydantic import ValidationError


def test_source_ref_accepts_every_declared_type() -> None:
    for source_type in SOURCE_TYPES:
        ref = SourceRef(type=source_type, id="x", label="y")
        assert ref.type == source_type


def test_source_ref_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        SourceRef(type="not-a-real-type", id="x")


def test_source_ref_id_and_label_length_caps() -> None:
    with pytest.raises(ValidationError):
        SourceRef(type="case", id="i" * 200)
    with pytest.raises(ValidationError):
        SourceRef(type="case", id="i", label="l" * 300)


def test_tool_call_proposal_defaults() -> None:
    proposal = ToolCallProposal(tool="search_cases")
    assert proposal.arguments == {}


def test_tool_execution_result_defaults() -> None:
    result = ToolExecutionResult(tool="t", ok=False, error="nope")
    assert result.payload == {}
    assert result.sources == []


def test_chat_outcome_defaults() -> None:
    outcome = ChatOutcome(text="hello")
    assert outcome.grounded is False
    assert outcome.sources == []
    assert outcome.iterations == 1
