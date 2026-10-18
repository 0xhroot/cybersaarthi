"""Regression tests: AI case retrieval by UUID / case number / name.

These pin the production bug where the chatbot claimed a case "does not exist"
when asked to summarize it by case number or name. Root causes fixed here:
(1) ``search_cases`` read only ``query`` while the model emitted ``case_id`` so
the filter was silently dropped; (2) case lookup was UUID-only; (3) the summary
tool was disabled without a route-bound case; (4) tool results could not
distinguish not-found / empty / error.

Every test uses isolated synthetic fixtures. Security properties (tenant
isolation, authorization-before-disclosure, no fabricated summaries) are
asserted, never weakened.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai import retrieval
from app.ai.schemas import (
    CASE_AMBIGUOUS,
    CASE_FOUND_BUT_EMPTY,
    CASE_FOUND_WITH_DATA,
    CASE_NOT_FOUND_OR_NOT_ACCESSIBLE,
    LOOKUP_ERROR,
)
from app.ai.tools import ToolContext, execute_tool
from app.core.config import get_settings
from app.db.postgres import Database
from app.models import Case, EvidenceFile, User
from sqlalchemy import delete
from starlette.requests import Request

from tests.api.conftest import ApiUser

# -- helpers ---------------------------------------------------------------


def _request() -> Request:
    """Minimal ASGI request so assert_case_access can consult request.state."""
    return Request(scope={"type": "http", "method": "POST", "path": "/ai/chat", "headers": []})


async def _tool_ctx(database: Database, user_id: uuid.UUID) -> tuple[ToolContext, object]:
    """A ToolContext bound to a real session and the real User row."""
    factory = database.session_factory()
    session = factory()  # AsyncSession
    await session.__aenter__()
    user = await session.get(User, user_id)
    assert user is not None
    ctx = ToolContext(request=_request(), session=session, user=user, case=None)
    return ctx, session


# -- fixtures --------------------------------------------------------------


@pytest.fixture
async def cases(database: Database, api_user: ApiUser, user_factory):
    """Synthetic cases covering every resolution outcome.

    - ``with_data``: owned, has evidence (found_with_data)
    - ``empty``: owned, no records (found_but_empty)
    - ``stranger``: owned by another user (must never be disclosed)
    - ``amb1`` / ``amb2``: two owned cases sharing one exact name (ambiguous)
    """
    stranger = await user_factory(role="INVESTIGATOR")
    ids = {
        "with_data": uuid.uuid4(),
        "empty": uuid.uuid4(),
        "stranger": uuid.uuid4(),
        "amb1": uuid.uuid4(),
        "amb2": uuid.uuid4(),
    }
    nums = {
        "with_data": f"RSLV-{uuid.uuid4().hex[:6]}",
        "empty": f"RSLV-{uuid.uuid4().hex[:6]}",
        "stranger": f"RSLV-{uuid.uuid4().hex[:6]}",
        "amb1": f"RSLV-{uuid.uuid4().hex[:6]}",
        "amb2": f"RSLV-{uuid.uuid4().hex[:6]}",
    }
    factory = database.session_factory()
    async with factory() as session:
        session.add_all(
            [
                Case(
                    id=ids["with_data"],
                    case_number=nums["with_data"],
                    title="Alpha phishing ring",
                    status="open",
                    owner_id=api_user.id,
                ),
                Case(
                    id=ids["empty"],
                    case_number=nums["empty"],
                    title="Beta empty shell",
                    status="open",
                    owner_id=api_user.id,
                ),
                Case(
                    id=ids["stranger"],
                    case_number=nums["stranger"],
                    title="Gamma foreign operation",
                    status="open",
                    owner_id=stranger.id,
                ),
                Case(
                    id=ids["amb1"],
                    case_number=nums["amb1"],
                    title="Duplicate Title Case",
                    status="open",
                    owner_id=api_user.id,
                ),
                Case(
                    id=ids["amb2"],
                    case_number=nums["amb2"],
                    title="Duplicate Title Case",
                    status="open",
                    owner_id=api_user.id,
                ),
            ]
        )
        for i in range(2):
            session.add(
                EvidenceFile(
                    case_id=str(ids["with_data"]),
                    original_filename=f"evidence-{i}.txt",
                    stored_key=f"cases/{ids['with_data']}/ev/{i}.txt",
                    content_type="text/plain",
                    file_size=12,
                    sha256=f"{i:02x}" * 32,
                )
            )
        await session.commit()

    yield {"ids": ids, "nums": nums, "stranger": stranger, "owner": api_user}

    async with factory() as session:
        for cid in ids.values():
            await session.execute(delete(EvidenceFile).where(EvidenceFile.case_id == str(cid)))
            await session.execute(delete(Case).where(Case.id == cid))
        await session.commit()


# -- 1, 2, 3: resolve by UUID, case number, and name -----------------------


async def test_resolves_owned_case_by_uuid(database, api_user, cases):
    ctx, session = await _tool_ctx(database, api_user.id)
    try:
        result = await execute_tool(
            ctx, "get_case_summary", {"case_id": str(cases["ids"]["with_data"])}
        )
    finally:
        await session.close()
    assert result.ok is True
    assert result.status == CASE_FOUND_WITH_DATA
    assert str(cases["ids"]["with_data"]) in result.payload["text"]


async def test_resolves_owned_case_by_public_case_number(database, api_user, cases):
    ctx, session = await _tool_ctx(database, api_user.id)
    try:
        result = await execute_tool(
            ctx, "get_case_summary", {"case_id": cases["nums"]["with_data"]}
        )
    finally:
        await session.close()
    assert result.ok is True, result.error
    assert result.status == CASE_FOUND_WITH_DATA
    assert cases["nums"]["with_data"] in result.payload["text"]


async def test_resolves_owned_case_by_exact_name(database, api_user, cases):
    ctx, session = await _tool_ctx(database, api_user.id)
    try:
        # "Beta empty shell" is unique and the case has no records.
        result = await execute_tool(ctx, "get_case_summary", {"case_id": "Beta empty shell"})
    finally:
        await session.close()
    assert result.ok is True, result.error
    assert result.status == CASE_FOUND_BUT_EMPTY


async def test_ambiguous_name_returns_candidates_not_a_guess(database, api_user, cases):
    ctx, session = await _tool_ctx(database, api_user.id)
    try:
        result = await execute_tool(ctx, "get_case_summary", {"case_id": "Duplicate Title Case"})
    finally:
        await session.close()
    # Ambiguity is surfaced as an actionable, structured outcome — never a
    # silent pick and never "the case does not exist".
    assert result.status == CASE_AMBIGUOUS
    cands = {c["case_id"] for c in result.payload.get("candidates", [])}
    assert cands == {str(cases["ids"]["amb1"]), str(cases["ids"]["amb2"])}


# -- 4: case with evidence returns evidence references ---------------------


async def test_case_with_evidence_returns_evidence_sources(database, api_user, cases):
    ctx, session = await _tool_ctx(database, api_user.id)
    try:
        result = await execute_tool(ctx, "list_evidence", {"case_id": cases["nums"]["with_data"]})
    finally:
        await session.close()
    assert result.ok is True
    assert result.status == CASE_FOUND_WITH_DATA
    ev_types = {s.type for s in result.sources}
    assert "evidence" in ev_types
    assert "evidence-0.txt" in result.payload["text"]


# -- 5: empty case is distinguished from a nonexistent case ----------------


async def test_empty_case_is_distinct_from_missing_case(database, api_user, cases):
    ctx, session = await _tool_ctx(database, api_user.id)
    try:
        empty = await execute_tool(ctx, "get_case_summary", {"case_id": cases["nums"]["empty"]})
        missing = await execute_tool(ctx, "get_case_summary", {"case_id": str(uuid.uuid4())})
    finally:
        await session.close()
    assert empty.ok is True
    assert empty.status == CASE_FOUND_BUT_EMPTY
    # A UUID that resolves to no accessible case is NOT reported as empty.
    assert missing.ok is False
    assert missing.status == CASE_NOT_FOUND_OR_NOT_ACCESSIBLE


# -- 6, 7: a case owned by another user is never disclosed / no bypass -----


async def test_stranger_case_is_never_disclosed(database, api_user, cases):
    stranger_case = str(cases["ids"]["stranger"])
    for reference in (
        stranger_case,  # by UUID
        cases["nums"]["stranger"],  # by case number
        "Gamma foreign operation",  # by name
    ):
        ctx, session = await _tool_ctx(database, api_user.id)
        try:
            result = await execute_tool(ctx, "get_case_summary", {"case_id": reference})
        finally:
            await session.close()
        assert result.ok is False, f"leaked for {reference}"
        assert result.status == CASE_NOT_FOUND_OR_NOT_ACCESSIBLE
        # No payload content, no sources, and no mention of the foreign case.
        assert "text" not in result.payload
        assert result.sources == []
        assert stranger_case not in (result.error or "")


async def test_stranger_case_search_returns_no_match(database, api_user, cases):
    ctx, session = await _tool_ctx(database, api_user.id)
    try:
        result = await execute_tool(ctx, "search_cases", {"case_id": cases["nums"]["stranger"]})
    finally:
        await session.close()
    assert result.status == CASE_NOT_FOUND_OR_NOT_ACCESSIBLE
    assert result.payload["match_count"] == 0
    assert result.sources == []


# -- core defect: search filter is never silently dropped ------------------


async def test_search_cases_honours_case_id_alias(database, api_user, cases):
    """The model sends `case_id`; the handler must not read only `query`."""
    ctx, session = await _tool_ctx(database, api_user.id)
    try:
        by_case_id = await execute_tool(
            ctx, "search_cases", {"case_id": cases["nums"]["with_data"]}
        )
        by_query = await execute_tool(ctx, "search_cases", {"query": cases["nums"]["with_data"]})
    finally:
        await session.close()
    assert by_case_id.status == CASE_FOUND_WITH_DATA
    assert by_case_id.payload["match_count"] == 1
    assert by_query.payload["match_count"] == 1
    assert by_case_id.payload["cases"] == by_query.payload["cases"]


# -- 8: tool results agree with the normal case API ------------------------


async def test_tool_search_agrees_with_case_api(database, api_user, http_client, cases):
    prefix = get_settings().API_V1_PREFIX
    resp = await http_client.get(f"{prefix}/cases?limit=200")
    assert resp.status_code == 200, resp.text
    api_ids = {item["id"] for item in resp.json()["items"]}

    ctx, session = await _tool_ctx(database, api_user.id)
    try:
        found = await retrieval.accessible_cases(session, ctx.user, query=None)
    finally:
        await session.close()
    tool_ids = {str(c.id) for c in found}
    assert tool_ids == api_ids


# -- 9: database failures are not reported as missing cases ----------------


async def test_db_failure_is_lookup_error_not_missing(database, api_user, cases, monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated database outage")

    monkeypatch.setattr(retrieval, "resolve_case_reference", _boom)
    ctx, session = await _tool_ctx(database, api_user.id)
    try:
        result = await execute_tool(
            ctx, "get_case_summary", {"case_id": cases["nums"]["with_data"]}
        )
    finally:
        await session.close()
    # A hard failure surfaces as lookup_error, never as "the case does not exist".
    assert result.ok is False
    assert result.status == LOOKUP_ERROR
    assert "lookup" in (result.error or "").lower() or "failed" in (result.error or "").lower()


async def test_db_failure_inside_resolver_is_lookup_error(database, api_user, cases):
    """The resolver's own exception guard maps a DB error to `error` status."""
    factory = database.session_factory()
    async with factory() as session:
        user = await session.get(User, api_user.id)
        # Patch the visibility query to explode after connection is open.
        from app.ai import retrieval as _r

        original = _r._visibility_condition

        async def _raise(*a, **k):
            raise RuntimeError("connection reset")

        monkeypatched = _raise
        _r._visibility_condition = monkeypatched  # type: ignore[assignment]
        try:
            res = await _r.resolve_case_reference(session, user, cases["nums"]["empty"])
        finally:
            _r._visibility_condition = original  # type: ignore[assignment]
    assert res.status == "error"
    assert res.case is None


# -- 10: the chatbot only reports records from authorized tools ------------


async def test_general_chat_summarizes_by_number_end_to_end(
    database, api_user, http_client, ai_service, cases, monkeypatch
):
    """Full path: general-mode chat resolves a case by number and summarizes it.

    The stubbed model emits the exact tool call that used to fail; the response
    must carry grounded sources pointing only at the authorized case.
    """
    from tests.api.test_ai_api import _stub_chat

    number = cases["nums"]["with_data"]
    tool_call = (
        f'```tool_call\n{{"tool": "get_case_summary", "arguments": {{"case_id": "{number}"}}}}\n```'
    )
    _stub_chat(ai_service, monkeypatch, [tool_call, f"Summarizing case {number}."])

    prefix = get_settings().API_V1_PREFIX
    resp = await http_client.post(f"{prefix}/ai/chat", json={"question": f"Summarize {number}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    event = body["tool_events"][0]
    assert event["tool"] == "get_case_summary"
    assert event["ok"] is True
    # Only the authorized case is cited.
    authorized = str(cases["ids"]["with_data"])
    case_sources = [s for s in body["sources"] if s["type"] == "case"]
    assert case_sources, "expected a grounded case citation"
    assert all(s["id"] == authorized for s in case_sources)


async def test_general_chat_reports_missing_case_honestly(
    api_user, http_client, ai_service, monkeypatch
):
    """A bogus number yields a structured miss, not an invented summary."""
    from tests.api.test_ai_api import _stub_chat

    bogus = f"NOSUCH-{uuid.uuid4().hex[:8]}"
    tool_call = (
        f'```tool_call\n{{"tool": "get_case_summary", "arguments": {{"case_id": "{bogus}"}}}}\n```'
    )
    _stub_chat(ai_service, monkeypatch, [tool_call, "No such case to my knowledge."])

    prefix = get_settings().API_V1_PREFIX
    resp = await http_client.post(f"{prefix}/ai/chat", json={"question": f"Summarize {bogus}"})
    assert resp.status_code == 200, resp.text
    event = resp.json()["tool_events"][0]
    assert event["ok"] is False
    assert event["status"] == CASE_NOT_FOUND_OR_NOT_ACCESSIBLE
