"""Unit tests: service-level pure logic (tool-call parsing, source filtering)."""

from __future__ import annotations

import uuid

import pytest
from app.ai.prompts import build_system_prompt
from app.ai.schemas import SourceRef
from app.ai.service import AIService, _profile_for
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
        "Sure.\n```tool_call\n"
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
    assert service._parse_tool_call("```tool_call\n[1, 2]\n```") is None


def test_parse_tool_call_missing_tool_key(service: AIService) -> None:
    assert service._parse_tool_call('```tool_call\n{"arguments": {}}\n```') is None


def test_parse_tool_call_non_dict_arguments(service: AIService) -> None:
    assert service._parse_tool_call('```tool_call\n{"tool": "x", "arguments": [1]}\n```') is None


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


# -- answer profiles --------------------------------------------------------


def test_profile_quick_is_tighter_than_standard(service: AIService) -> None:
    settings = get_settings()
    quick = _profile_for(settings, "quick")
    standard = _profile_for(settings, "standard")
    assert quick.name == "quick"
    assert quick.max_tokens < standard.max_tokens
    assert quick.tool_iterations <= standard.tool_iterations


def test_profile_deep_is_more_generous_than_standard(service: AIService) -> None:
    settings = get_settings()
    deep = _profile_for(settings, "deep")
    standard = _profile_for(settings, "standard")
    assert deep.name == "deep"
    assert deep.max_tokens > standard.max_tokens
    assert deep.tool_iterations >= standard.tool_iterations


def test_profile_falls_back_to_configured_default(service: AIService) -> None:
    """An unset profile resolves to the server's configured default."""
    settings = get_settings().model_copy(update={"AI_DEFAULT_PROFILE": "quick"})
    resolved = _profile_for(settings, None)
    assert resolved.name == "quick"
    assert resolved.max_tokens == settings.AI_PROFILE_QUICK_MAX_TOKENS


def test_profile_rejects_unknown_by_falling_back_to_default(service: AIService) -> None:
    """A stale/unknown client profile must not hard-fail — it falls back."""
    settings = get_settings()
    resolved = _profile_for(settings, "ultra-max-turbo")
    assert resolved.name == settings.AI_DEFAULT_PROFILE


def test_profile_budgets_are_respected_by_engine_settings(service: AIService) -> None:
    """Each profile's max_tokens and tool_iterations are what the engine reads."""
    settings = get_settings()
    for name in ("quick", "standard", "deep"):
        p = _profile_for(settings, name)
        assert p.max_tokens > 0
        assert p.tool_iterations >= 1


# -- think mode (Phase 1) --------------------------------------------------


def test_think_maps_onto_the_deep_budget(service: AIService) -> None:
    """`think` is an alias for `deep`'s budget — one source of truth, no drift."""
    settings = get_settings()
    think = _profile_for(settings, "think")
    deep = _profile_for(settings, "deep")
    assert think.max_tokens == deep.max_tokens
    assert think.tool_iterations == deep.tool_iterations


def test_think_requests_structured_and_deep_does_not(service: AIService) -> None:
    """Only `think` opts into the structured rationale/uncertainty contract."""
    settings = get_settings()
    assert _profile_for(settings, "think").structured is True
    assert _profile_for(settings, "deep").structured is False
    assert _profile_for(settings, "standard").structured is False
    assert _profile_for(settings, "quick").structured is False


def test_think_is_case_insensitive_and_trimmed(service: AIService) -> None:
    """A client may send any casing; budgets must not silently fall back."""
    settings = get_settings()
    resolved = _profile_for(settings, "  THINK ")
    assert resolved.name == "think"
    assert resolved.structured is True


def test_think_still_spends_more_than_quick(service: AIService) -> None:
    """Think must genuinely be the larger budget, not a relabelled quick."""
    settings = get_settings()
    think = _profile_for(settings, "think")
    quick = _profile_for(settings, "quick")
    assert think.max_tokens > quick.max_tokens
    assert think.tool_iterations > quick.tool_iterations


def test_think_prompt_contract_has_required_sections() -> None:
    """The Think prompt must demand rationale, facts, uncertainty, alternatives
    and open questions — and must never ask for hidden chain-of-thought."""
    prompt = build_system_prompt("general", structured=True)
    for section in (
        "Rationale",
        "Facts",
        "Uncertainty",
        "Alternative explanations",
        "Open questions",
    ):
        assert section in prompt, section
    # Explicitly out of scope: the contract asks for a *summary* of the
    # approach, never fabricated intermediate reasoning steps.
    assert "not hidden reasoning" in prompt
    assert "never fabricate intermediate steps" in prompt


def test_structured_prompt_is_only_added_when_requested() -> None:
    assert "Think-mode" not in build_system_prompt("general")
    assert "Think-mode" in build_system_prompt("general", structured=True)


# -- analysis mode prompt contract (Phase 2) --------------------------------


def test_analysis_prompt_separates_the_five_buckets() -> None:
    prompt = build_system_prompt("analysis")
    for section in (
        "Observed facts",
        "Deterministically computed metrics",
        "AI interpretations",
        "Hypotheses and uncertainty",
        "Missing evidence and next verification steps",
    ):
        assert section in prompt, section
    # The model interprets; it never computes — and numbers must use the
    # machine-checkable metric grammar (a verbatim echo of the DATA line).
    assert "you never compute them yourself" in prompt
    assert "`metric=<name> entity_id=<entity_id> value=<value>`" in prompt
    # Failure honesty: no analysis is described when retrieval failed.
    assert "report that failure" in prompt


def test_analysis_mode_does_not_stack_the_think_contract() -> None:
    """analysis owns its five-section structure; Think's generic one would
    contradict it, so it must not be appended even in think mode."""
    prompt = build_system_prompt("analysis", structured=True)
    assert "Think-mode" not in prompt
    assert "Observed facts" in prompt
    # Other modes still get the Think contract when they ask for it.
    assert "Think-mode" in build_system_prompt("case", structured=True)


# -- context budget enforcement (Phase 1) ----------------------------------


def test_history_is_clamped_when_prompt_would_overflow(service: AIService) -> None:
    """Oldest turns are dropped first; system/data/question are never touched."""
    huge = "word " * 20_000  # ~25k tokens, far over the 8192-token slot
    history = [
        {"role": "user", "content": huge},
        {"role": "assistant", "content": huge},
        {"role": "user", "content": "recent question"},
    ]
    trimmed = service._clamp_history_to_budget(
        "SYSTEM", "", "current question", history, max_tokens=768
    )
    # The two huge oldest turns are gone; the recent turn survives.
    assert all(huge not in m["content"] for m in trimmed)
    assert trimmed == [{"role": "user", "content": "recent question"}]


def test_history_is_left_intact_when_it_already_fits(service: AIService) -> None:
    history = [
        {"role": "user", "content": "short q"},
        {"role": "assistant", "content": "short a"},
    ]
    trimmed = service._clamp_history_to_budget("SYSTEM", "", "q", list(history), max_tokens=160)
    assert trimmed == history


def test_clamp_reserves_generation_room(service: AIService) -> None:
    """A larger max_tokens budget leaves less room for history."""
    history = [{"role": "user", "content": "filler " * 1_000}]
    small = service._clamp_history_to_budget("S", "", "q", list(history), max_tokens=160)
    large = service._clamp_history_to_budget("S", "", "q", list(history), max_tokens=768)
    assert len(large) <= len(small)


# -- cancellation (Phase 1) -------------------------------------------------


async def test_closing_the_sse_generator_cancels_the_producer(
    service: AIService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stop/disconnect contract: closing the event generator must cancel the
    in-flight llama.cpp generation, not merely abandon it."""
    import asyncio
    from types import SimpleNamespace

    from starlette.requests import Request

    cancelled = asyncio.Event()

    async def slow_stream(messages, *, max_tokens, temperature=0.2, stop=None):
        try:
            yield "token-1 "
            await asyncio.sleep(30)
            yield "token-2"  # pragma: no cover - never reached
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(service.client, "chat_stream", slow_stream)
    monkeypatch.setattr(service, "ensure_ready", noop)
    monkeypatch.setattr(service, "check_rate_limit", noop)

    request = Request({"type": "http", "method": "POST", "path": "/ai/chat/stream", "headers": []})
    user = SimpleNamespace(id=uuid.uuid4())

    gen = service.ask_stream(request, None, user, question="hi")  # type: ignore[arg-type]
    first = await gen.__anext__()
    assert first["type"] == "progress"

    # Client disconnect / Stop button: the ASGI layer closes the generator.
    await gen.aclose()

    # `aclose()` runs ask_stream's finally block, which cancels and awaits the
    # producer task — so cancellation must already be visible.
    assert cancelled.is_set(), "producer kept generating after the client left"
