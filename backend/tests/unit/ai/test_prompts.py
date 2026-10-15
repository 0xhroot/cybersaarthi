"""Unit tests: versioned prompt assembly (no format-brace hazards)."""

from __future__ import annotations

from app.ai.prompts import (
    BASE_PREAMBLE,
    PROMPT_VERSION,
    build_system_prompt,
    fence_data,
)


def test_prompt_version_is_embedded() -> None:
    assert PROMPT_VERSION in BASE_PREAMBLE


def test_tool_instruction_placeholders_do_not_raise() -> None:
    # TOOL_INSTRUCTION contains literal JSON braces; build_system_prompt must
    # substitute the tool list without str.format exploding on them.
    tools = "search_cases(query), get_case_summary(case_id)"
    prompt = build_system_prompt("general", tool_list=tools)
    assert "search_cases" in prompt
    assert "{tool_list}" not in prompt
    assert '{"tool": "<name>"' in prompt  # literal braces survive


def test_no_tools_means_no_tool_instruction() -> None:
    prompt = build_system_prompt("general")
    assert "```tool_call" not in prompt


def test_specialized_mode_text_is_included() -> None:
    prompt = build_system_prompt("report", tool_list=None, has_case_data=True)
    assert "draft" in prompt.lower()
    assert "human" in prompt.lower()


def test_unknown_mode_falls_back_to_general() -> None:
    prompt = build_system_prompt("nonexistent-mode")
    assert "CyberSaarthi" in prompt


def test_has_case_data_appends_preference() -> None:
    with_data = build_system_prompt("case", has_case_data=True)
    without = build_system_prompt("case", has_case_data=False)
    assert len(with_data) > len(without)


def test_knowledge_mode_requires_tool_lookup_before_answering() -> None:
    """Guard against the found-in-live-testing hallucination: knowledge mode
    has no DATA block, so the model must reach for search_knowledge rather
    than inventing a port/path/filename from memory."""
    prompt = build_system_prompt("knowledge", has_case_data=False)
    assert "search_knowledge" in prompt
    assert "Never guess" in prompt


def test_fence_data_marks_untrusted() -> None:
    fenced = fence_data("evidence", "filename: a.txt")
    assert "BEGIN DATA: evidence" in fenced
    assert "untrusted" in fenced
    assert "filename: a.txt" in fenced
    assert fenced.endswith("=== END DATA ===")
