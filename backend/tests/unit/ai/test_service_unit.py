"""Unit tests: service-level pure logic (tool-call parsing, source filtering)."""

from __future__ import annotations

import uuid

import pytest
from app.ai.schemas import SourceRef
from app.ai.service import AIService
from app.api.errors import ApiHTTPException
from app.core.config import get_settings
from app.models import Case


@pytest.fixture
def service() -> AIService:
    return AIService(get_settings())


def _case(case_id: uuid.UUID) -> Case:
    return Case(case_number="TEST-1", title="t", id=case_id)


def test_parse_tool_call_valid(service: AIService) -> None:
    answer = (
        'Sure.\n```tool_call\n'
        '{"tool": "list_evidence", "arguments": {"case_id": "abc", "limit": 5}}\n'
        "```"
    )
    proposal = service._parse_tool_call(answer)
    assert proposal is not None
    assert proposal.tool == "list_evidence"
    assert proposal.arguments == {"case_id": "abc", "limit": 5}


def test_parse_tool_call_no_fence(service: AIService) -> None:
    assert service._parse_tool_call("just an answer") is None


def test_parse_tool_call_invalid_json(service: AIService) -> None:
    assert service._parse_tool_call('```tool_call\n{"tool":\n```') is None


def test_parse_tool_call_not_a_dict(service: AIService) -> None:
    assert service._parse_tool_call('```tool_call\n[1, 2]\n```') is None


def test_parse_tool_call_missing_tool_key(service: AIService) -> None:
    assert service._parse_tool_call('```tool_call\n{"arguments": {}}\n```') is None


def test_parse_tool_call_non_dict_arguments(service: AIService) -> None:
    assert (
        service._parse_tool_call('```tool_call\n{"tool": "x", "arguments": [1]}\n```') is None
    )


def test_parse_tool_call_empty_answer(service: AIService) -> None:
    assert service._parse_tool_call("") is None
    assert service._parse_tool_call(None) is None  # type: ignore[arg-type]


def test_filter_sources_keeps_same_case(service: AIService) -> None:
    case_id = uuid.uuid4()
    case = _case(case_id)
    sources = [
        SourceRef(type="case", id=str(case_id), label="c"),
        SourceRef(type="evidence", id=str(uuid.uuid4()), label="e"),
    ]
    kept = service._filter_sources(sources, case)
    assert len(kept) == 2


def test_filter_sources_drops_other_case_urls(service: AIService) -> None:
    case_id = uuid.uuid4()
    other = uuid.uuid4()
    case = _case(case_id)
    sources = [
        SourceRef(type="case", id=str(case_id), label="mine"),
        # Same-case id but URL points at another case — dropped.
        SourceRef(type="doc", id=str(case_id), label="sneaky", url=f"/cases/{other}/graph"),
        SourceRef(type="metric", id="centrality", label="m", url=f"/cases/{other}/analytics"),
    ]
    kept = service._filter_sources(sources, case)
    assert [s.label for s in kept] == ["mine"]


def test_filter_sources_without_case_keeps_everything(service: AIService) -> None:
    sources = [
        SourceRef(type="knowledge", id="README.md#intro", label="intro"),
        SourceRef(type="doc", id="x", label="linked", url="/cases/anything"),
    ]
    kept = service._filter_sources(sources, None)
    assert [s.label for s in kept] == ["intro", "linked"]


def test_ensure_enabled_refuses_when_disabled() -> None:
    settings = get_settings().model_copy(update={"AI_ENABLED": False})
    service = AIService(settings)
    with pytest.raises(ApiHTTPException) as excinfo:
        service.ensure_enabled()
    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "AI_DISABLED"
