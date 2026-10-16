"""Phase 3 tests: hypothesize mode — honest AI hypothesis drafts.

Security/semantics properties pinned here: drafts are parsed strictly and
never stored automatically (the DB stays untouched by a suggestion run), cited
ids are verified against retrieved data, unparseable output is reported
instead of papered over, and case authorization is identical to every other
mode. No numeric confidence is produced anywhere.
"""

from __future__ import annotations

import json
import uuid

from app.core.config import get_settings
from app.db.postgres import Database
from app.models import Hypothesis
from sqlalchemy import func, select

from tests.api.test_ai_api import _stub_chat


def _draft_block(obj: dict) -> str:
    return f"```hypothesis\n{json.dumps(obj)}\n```"


# -- acceptance and conversation storage ------------------------------------


async def test_hypothesize_mode_is_accepted_and_stored(
    http_client, ai_service, monkeypatch
) -> None:
    """The mode must survive the DB check constraint (conversation storage)."""
    prefix = get_settings().API_V1_PREFIX
    _stub_chat(
        ai_service,
        monkeypatch,
        [_draft_block({"title": "T", "statement": "S", "evidence_ids": []})],
    )
    resp = await http_client.post(
        f"{prefix}/ai/chat", json={"question": "suggest", "mode": "hypothesize"}
    )
    assert resp.status_code == 200, resp.text

    listing = await http_client.get(f"{prefix}/ai/conversations", params={"limit": 1})
    assert listing.status_code == 200, listing.text
    newest = listing.json()["items"][0]
    assert newest["mode"] == "hypothesize"


async def test_hypothesize_prompt_contract(
    http_client, ai_service, monkeypatch, _owned_case
) -> None:
    prefix = get_settings().API_V1_PREFIX
    seen, _ = _stub_chat(ai_service, monkeypatch, ["ok"])
    await http_client.post(
        f"{prefix}/ai/chat",
        json={
            "question": "suggest",
            "mode": "hypothesize",
            "case_id": str(_owned_case),
        },
    )
    prompt = seen[-1][0]["content"]
    assert "```hypothesis" in prompt
    assert "You never confirm anything" in prompt
    assert "Never output numeric confidence" in prompt
    assert "candidate to test, not an accusation" in prompt


# -- draft quality and verification -----------------------------------------


async def test_drafts_are_returned_with_verified_and_unverified_ids(
    http_client, ai_service, monkeypatch, _owned_case
) -> None:
    prefix = get_settings().API_V1_PREFIX
    ghost = str(uuid.uuid4())
    answer = "\n".join(
        [
            _draft_block(
                {
                    "title": "Grounded candidate",
                    "statement": "Case record X shows a shared device.",
                    "evidence_ids": [str(_owned_case)],
                    "refutation": "Device logs showing distinct users.",
                    "missing": "Device session records.",
                }
            ),
            _draft_block(
                {
                    "title": "Candidate citing an unknown id",
                    "statement": "Entity Y was reused.",
                    "evidence_ids": [ghost],
                }
            ),
        ]
    )
    _stub_chat(ai_service, monkeypatch, [answer])

    resp = await http_client.post(
        f"{prefix}/ai/chat",
        json={
            "question": "suggest",
            "mode": "hypothesize",
            "case_id": str(_owned_case),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hypothesis_draft_errors"] == 0
    assert len(body["hypothesis_drafts"]) == 2
    first, second = body["hypothesis_drafts"]
    assert first["title"] == "Grounded candidate"
    assert first["unverified_ids"] == []
    assert second["unverified_ids"] == [ghost.lower()]
    # Draft mode also runs the id claim check.
    assert body["citation_check"] is not None
    assert ghost.lower() in body["citation_check"]["unverified_ids"]


async def test_unparseable_output_is_reported_not_faked(
    http_client, ai_service, monkeypatch, _owned_case
) -> None:
    prefix = get_settings().API_V1_PREFIX
    _stub_chat(
        ai_service,
        monkeypatch,
        ["```hypothesis\n{broken json}\n```"],
    )
    resp = await http_client.post(
        f"{prefix}/ai/chat",
        json={
            "question": "suggest",
            "mode": "hypothesize",
            "case_id": str(_owned_case),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hypothesis_drafts"] == []
    assert body["hypothesis_draft_errors"] == 1


async def test_suggestion_runs_never_write_to_the_database(
    http_client, ai_service, monkeypatch, _owned_case, database: Database
) -> None:
    """A suggestion run must leave zero rows behind: only a human recording
    through the hypothesis API creates one (status 'proposed')."""
    prefix = get_settings().API_V1_PREFIX
    answer = _draft_block(
        {
            "title": "T",
            "statement": "S",
            "evidence_ids": [str(_owned_case)],
        }
    )
    _stub_chat(ai_service, monkeypatch, [answer])
    resp = await http_client.post(
        f"{prefix}/ai/chat",
        json={
            "question": "suggest",
            "mode": "hypothesize",
            "case_id": str(_owned_case),
        },
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["hypothesis_drafts"]) == 1

    factory = database.session_factory()
    async with factory() as session:
        count = (
            await session.execute(
                select(func.count(Hypothesis.id)).where(
                    Hypothesis.case_id == str(_owned_case)
                )
            )
        ).scalar_one()
    assert count == 0


# -- authorization and context ----------------------------------------------


async def test_hypothesize_denies_a_foreign_case(
    http_client, ai_service, monkeypatch, _stranger_case
) -> None:
    prefix = get_settings().API_V1_PREFIX
    _stub_chat(ai_service, monkeypatch, ["should never be reached"])
    resp = await http_client.post(
        f"{prefix}/ai/chat",
        json={
            "question": "suggest",
            "mode": "hypothesize",
            "case_id": str(_stranger_case),
        },
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "CASE_ACCESS_DENIED"


async def test_hypothesize_context_has_records_but_no_analytics_scores(
    http_client, ai_service, monkeypatch, _owned_case
) -> None:
    """Hypotheses are grounded in records — analytics scores stay out of the
    context so they can never be laundered into 'confidence'."""
    prefix = get_settings().API_V1_PREFIX
    seen, _ = _stub_chat(ai_service, monkeypatch, ["ok"])
    await http_client.post(
        f"{prefix}/ai/chat",
        json={
            "question": "suggest",
            "mode": "hypothesize",
            "case_id": str(_owned_case),
        },
    )
    joined = "\n".join(
        m["content"] for m in seen[-1] if "BEGIN DATA:" in m["content"]
    )
    assert "BEGIN DATA: evidence metadata" in joined
    assert "BEGIN DATA: graph" in joined
    assert "BEGIN DATA: victims" in joined
    assert "BEGIN DATA: analytics" not in joined


# -- streaming ---------------------------------------------------------------


async def test_stream_done_carries_drafts_and_errors(
    http_client, ai_service, monkeypatch, _owned_case
) -> None:
    prefix = get_settings().API_V1_PREFIX
    answer = "\n".join(
        [
            _draft_block({"title": "T1", "statement": "S1", "evidence_ids": []}),
            "```hypothesis\nbroken\n```",
        ]
    )
    _stub_chat(ai_service, monkeypatch, [answer])

    events: list[dict] = []
    async with http_client.stream(
        "POST",
        f"{prefix}/ai/chat/stream",
        json={
            "question": "suggest",
            "mode": "hypothesize",
            "case_id": str(_owned_case),
        },
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

    done = events[-1]
    assert done["type"] == "done"
    assert [d["title"] for d in done["hypothesis_drafts"]] == ["T1"]
    assert done["hypothesis_draft_errors"] == 1
