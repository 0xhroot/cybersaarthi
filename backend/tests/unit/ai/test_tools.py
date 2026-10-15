"""Unit tests: read-only tool registry, sanitization, prompt listing."""

from __future__ import annotations

from app.ai.schemas import ToolExecutionResult
from app.ai.tools import TOOLS, _limit, _sanitize_arguments, execute_tool, tool_list_for_prompt

# The v1 contract: exactly these tools, all read-only. Any change here is a
# behavior change that must be reviewed against SECURITY_AND_ISOLATION.md.
EXPECTED_TOOLS = {
    "search_cases",
    "get_case_summary",
    "list_evidence",
    "get_entity",
    "get_timeline",
    "get_analytics_summary",
    "search_knowledge",
}


def test_registry_is_exactly_the_read_only_v1_set() -> None:
    assert set(TOOLS) == EXPECTED_TOOLS


def test_every_tool_has_schema_and_description() -> None:
    for spec in TOOLS.values():
        assert spec.description
        assert spec.parameters.get("type") == "object"
        assert "properties" in spec.parameters


def test_case_scoped_tools_declare_case_id() -> None:
    for name, spec in TOOLS.items():
        if spec.case_scoped:
            assert "case_id" in spec.parameters.get("properties", {}), name


def test_tool_list_for_prompt_formats() -> None:
    listing = tool_list_for_prompt()
    assert "search_cases" in listing
    assert "query" in listing  # parameter names surface in the prompt
    assert listing.count(", ") >= 1


async def test_unknown_tool_returns_error_result() -> None:
    result = await execute_tool(
        _FakeCtx(), "delete_everything", {"case_id": "x"}  # type: ignore[arg-type]
    )
    assert isinstance(result, ToolExecutionResult)
    assert result.ok is False
    assert "unknown tool" in (result.error or "")


async def test_non_dict_arguments_return_error() -> None:
    result = await execute_tool(_FakeCtx(), "search_cases", ["not", "a", "dict"])  # type: ignore[arg-type]
    assert result.ok is False
    assert "JSON object" in (result.error or "")


def test_limit_is_clamped() -> None:
    assert _limit(None, default=7, maximum=50) == 7
    assert _limit("abc", default=7, maximum=50) == 7
    assert _limit(0, default=7, maximum=50) == 1
    assert _limit(999, default=7, maximum=50) == 50
    assert _limit(10, default=7, maximum=50) == 10


def test_arguments_are_sanitized_for_audit() -> None:
    clean = _sanitize_arguments(
        {"query": "x" * 500, "limit": 5, "nested": {"deep": True}, "flag": True}
    )
    assert len(clean["query"]) == 200
    assert clean["limit"] == 5
    assert clean["flag"] is True
    # Nested dicts collapse to a truncated string for the audit log.
    assert isinstance(clean["nested"], str)


def test_sanitize_handles_more_than_ten_keys() -> None:
    args = {f"k{i}": i for i in range(20)}
    clean = _sanitize_arguments(args)
    assert len(clean) == 10


class _FakeCtx:
    """Placeholder ctx for paths that fail before touching the session."""

    request = None
    session = None
    user = None
    case = None
