"""Phase 2 tests: analysis mode — context, prompt contract, claim validation.

The analysis mode is the backend of the Analysis-page AI panel: the model
interprets deterministic analytics results, never computes them, and every id
or metric number it cites is machine-checked against what was actually
retrieved for the authorized case (``validate_cited_claims``).

Security properties asserted here: analysis mode never bypasses case
authorization, and a failed/invented claim is reported as-is — never silently
converted into a passing check.
"""

from __future__ import annotations

import json
import uuid

from app.core.config import get_settings
from app.db.postgres import Database
from app.models import Case, Entity, MetricResult
from sqlalchemy import delete, func, select

from tests.api.conftest import ApiUser
from tests.api.test_ai_api import _stub_chat

# -- fixtures --------------------------------------------------------------


async def _seed_entity_with_metric(database: Database, case_id: uuid.UUID) -> uuid.UUID:
    """One entity carrying one degree metric (raw 4.0, normalized 1.0)."""
    factory = database.session_factory()
    async with factory() as session:
        entity = Entity(
            case_id=str(case_id),
            entity_type="person",
            canonical_value=f"analysis-person-{uuid.uuid4().hex[:8]}",
            blocking_key=f"bk-{case_id}-analysis-{uuid.uuid4().hex[:8]}",
            display_value="Analysis Person",
            status="active",
        )
        session.add(entity)
        await session.flush()
        session.add(
            MetricResult(
                case_id=str(case_id),
                entity_id=str(entity.id),
                metric_name="degree",
                raw_value=4.0,
                normalized_score=1.0,
                rank=1,
            )
        )
        await session.commit()
        return entity.id


# -- acceptance and prompt contract ----------------------------------------


async def test_analysis_mode_is_accepted_without_a_case(
    http_client, ai_service, monkeypatch
) -> None:
    prefix = get_settings().API_V1_PREFIX
    _stub_chat(ai_service, monkeypatch, ["ok"])
    resp = await http_client.post(
        f"{prefix}/ai/chat", json={"question": "interpret this", "mode": "analysis"}
    )
    assert resp.status_code == 200, resp.text
    # No bound case → nothing to validate claims against → no check, not a
    # fabricated pass.
    assert resp.json()["citation_check"] is None


async def test_analysis_mode_denies_a_foreign_case(
    http_client, ai_service, monkeypatch, _stranger_case
) -> None:
    """Analysis mode must never become a side channel around case access."""
    prefix = get_settings().API_V1_PREFIX
    _stub_chat(ai_service, monkeypatch, ["should never be reached"])
    resp = await http_client.post(
        f"{prefix}/ai/chat",
        json={"question": "analyze", "mode": "analysis", "case_id": str(_stranger_case)},
    )
    # Existing contract: unauthorized case access is a 403 that names the id
    # only — never the title, owner or existence details.
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "CASE_ACCESS_DENIED"
    assert "ai api foreign case" not in resp.text


async def test_analysis_context_contains_evidence_and_analytics_blocks(
    http_client, ai_service, monkeypatch, _owned_case, database: Database
) -> None:
    """analysis mode must feed the model evidence + graph + analytics digests."""
    prefix = get_settings().API_V1_PREFIX
    entity_id = await _seed_entity_with_metric(database, _owned_case)
    seen, _ = _stub_chat(ai_service, monkeypatch, ["interpreted"])
    resp = await http_client.post(
        f"{prefix}/ai/chat",
        json={"question": "analyze", "mode": "analysis", "case_id": str(_owned_case)},
    )
    assert resp.status_code == 200, resp.text

    data_msgs = [m["content"] for m in seen[-1] if "BEGIN DATA:" in m["content"]]
    joined = "\n".join(data_msgs)
    assert "BEGIN DATA: evidence metadata" in joined
    assert "BEGIN DATA: analytics" in joined
    assert "BEGIN DATA: graph" in joined
    assert "metric=degree" in joined
    assert str(entity_id) in joined


async def test_analysis_system_prompt_carries_the_bucket_contract(
    http_client, ai_service, monkeypatch, _owned_case
) -> None:
    prefix = get_settings().API_V1_PREFIX
    seen, _ = _stub_chat(ai_service, monkeypatch, ["interpreted"])
    await http_client.post(
        f"{prefix}/ai/chat",
        json={"question": "analyze", "mode": "analysis", "case_id": str(_owned_case)},
    )
    system_prompt = seen[-1][0]["content"]
    for section in (
        "Observed facts",
        "Deterministically computed metrics",
        "AI interpretations",
        "Hypotheses and uncertainty",
        "Missing evidence and next verification steps",
    ):
        assert section in system_prompt, section
    assert "you never compute them yourself" in system_prompt
    assert "`metric=<name> entity_id=<entity_id> value=<value>`" in system_prompt


# -- claim validation -------------------------------------------------------


async def test_analysis_verifies_cited_ids_and_metric_claims(
    http_client, ai_service, monkeypatch, _owned_case, database: Database
) -> None:
    prefix = get_settings().API_V1_PREFIX
    entity_id = await _seed_entity_with_metric(database, _owned_case)
    answer = (
        f"Observed facts cite case {_owned_case} and entity {entity_id}. "
        f"Metric: metric:degree@{entity_id} = 4.0"
    )
    _stub_chat(ai_service, monkeypatch, [answer])

    resp = await http_client.post(
        f"{prefix}/ai/chat",
        json={"question": "analyze", "mode": "analysis", "case_id": str(_owned_case)},
    )
    assert resp.status_code == 200, resp.text
    check = resp.json()["citation_check"]
    assert check is not None
    assert check["cited_ids"] == 2
    assert check["verified_ids"] == 2
    assert check["unverified_ids"] == []
    assert check["metric_claims_checked"] == 1
    assert check["metric_claims_mismatched"] == []


async def test_analysis_validates_data_echo_metric_claims(
    http_client, ai_service, monkeypatch, _owned_case, database: Database
) -> None:
    """Models naturally quote metrics as a verbatim DATA-line echo
    (`metric=... entity_id=... value=...`) — that shape must be checked too;
    live runs otherwise reported 0 checked claims."""
    prefix = get_settings().API_V1_PREFIX
    entity_id = await _seed_entity_with_metric(database, _owned_case)
    answer = (
        f"Correct: `metric=degree entity_id={entity_id} value=4.0 score=1.0 rank=1` "
        f"Wrong: `metric=degree entity_id={entity_id} value=7.7`"
    )
    _stub_chat(ai_service, monkeypatch, [answer])

    resp = await http_client.post(
        f"{prefix}/ai/chat",
        json={"question": "analyze", "mode": "analysis", "case_id": str(_owned_case)},
    )
    assert resp.status_code == 200, resp.text
    check = resp.json()["citation_check"]
    assert check is not None
    assert check["metric_claims_checked"] == 2
    assert len(check["metric_claims_mismatched"]) == 1
    assert "data says 4.0000" in check["metric_claims_mismatched"][0]


async def test_analysis_flags_an_invented_id(
    http_client, ai_service, monkeypatch, _owned_case
) -> None:
    prefix = get_settings().API_V1_PREFIX
    ghost = str(uuid.uuid4())
    _stub_chat(ai_service, monkeypatch, [f"See evidence {ghost} for details."])

    resp = await http_client.post(
        f"{prefix}/ai/chat",
        json={"question": "analyze", "mode": "analysis", "case_id": str(_owned_case)},
    )
    check = resp.json()["citation_check"]
    assert check is not None
    assert ghost in check["unverified_ids"]
    assert check["verified_ids"] == 0


async def test_analysis_flags_a_wrong_metric_value(
    http_client, ai_service, monkeypatch, _owned_case, database: Database
) -> None:
    """A number that does not match metric_results is reported, not accepted."""
    prefix = get_settings().API_V1_PREFIX
    entity_id = await _seed_entity_with_metric(database, _owned_case)
    _stub_chat(ai_service, monkeypatch, [f"Score: metric:degree@{entity_id} = 99.0"])

    resp = await http_client.post(
        f"{prefix}/ai/chat",
        json={"question": "analyze", "mode": "analysis", "case_id": str(_owned_case)},
    )
    check = resp.json()["citation_check"]
    assert check is not None
    assert check["metric_claims_checked"] == 1
    assert len(check["metric_claims_mismatched"]) == 1
    assert "data says" in check["metric_claims_mismatched"][0]


async def test_analysis_flags_a_metric_for_an_unknown_entity(
    http_client, ai_service, monkeypatch, _owned_case
) -> None:
    prefix = get_settings().API_V1_PREFIX
    ghost_entity = str(uuid.uuid4())
    _stub_chat(
        ai_service, monkeypatch, [f"Score: metric:degree@{ghost_entity} = 1.0"]
    )

    resp = await http_client.post(
        f"{prefix}/ai/chat",
        json={"question": "analyze", "mode": "analysis", "case_id": str(_owned_case)},
    )
    check = resp.json()["citation_check"]
    assert check is not None
    assert len(check["metric_claims_mismatched"]) == 1
    assert "no such metric" in check["metric_claims_mismatched"][0]


async def test_non_analysis_modes_do_not_run_a_claim_check(
    http_client, ai_service, monkeypatch, _owned_case
) -> None:
    prefix = get_settings().API_V1_PREFIX
    _stub_chat(ai_service, monkeypatch, [f"See {uuid.uuid4()}."])
    resp = await http_client.post(
        f"{prefix}/ai/chat",
        json={"question": "summarize", "mode": "case", "case_id": str(_owned_case)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["citation_check"] is None


# -- streaming --------------------------------------------------------------


async def test_analysis_output_budget_is_floored_but_others_are_not(
    http_client, ai_service, monkeypatch, _owned_case
) -> None:
    """deep's 768 tokens truncated live analysis runs after section 3 of 5, so
    analysis floors the OUTPUT allowance — and only for analysis (context
    size, parallelism and other modes stay exactly at their profile budget)."""
    prefix = get_settings().API_V1_PREFIX
    settings = get_settings()

    _, analysis_tokens = _stub_chat(ai_service, monkeypatch, ["ok"])
    await http_client.post(
        f"{prefix}/ai/chat",
        json={
            "question": "analyze",
            "mode": "analysis",
            "case_id": str(_owned_case),
            "profile": "think",
        },
    )
    assert max(analysis_tokens) >= 1024

    _, case_tokens = _stub_chat(ai_service, monkeypatch, ["ok"])
    await http_client.post(
        f"{prefix}/ai/chat",
        json={
            "question": "summarize",
            "mode": "case",
            "case_id": str(_owned_case),
            "profile": "standard",
        },
    )
    assert case_tokens[-1] == settings.AI_PROFILE_STANDARD_MAX_TOKENS


async def test_stream_done_carries_the_citation_check(
    http_client, ai_service, monkeypatch, _owned_case, database: Database
) -> None:
    prefix = get_settings().API_V1_PREFIX
    entity_id = await _seed_entity_with_metric(database, _owned_case)
    answer = (
        f"Cited {_owned_case} and {entity_id}. "
        f"metric:degree@{entity_id} = 4.0"
    )
    _stub_chat(ai_service, monkeypatch, [answer])

    events = []
    async with http_client.stream(
        "POST",
        f"{prefix}/ai/chat/stream",
        json={"question": "analyze", "mode": "analysis", "case_id": str(_owned_case)},
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

    done = events[-1]
    assert done["type"] == "done"
    check = done.get("citation_check")
    assert check is not None
    assert check["unverified_ids"] == []
    assert check["metric_claims_checked"] == 1


# -- hygiene ----------------------------------------------------------------


async def test_seeded_rows_cascade_with_their_case(
    database: Database, api_user: ApiUser
) -> None:
    """The metric/entity seeds above must not outlive their case."""
    case_id = uuid.uuid4()
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            Case(
                id=case_id,
                case_number=f"ANLY-{uuid.uuid4().hex[:8]}",
                title="cascade check",
                status="open",
                owner_id=api_user.id,
            )
        )
        await session.flush()
        entity = Entity(
            case_id=str(case_id),
            entity_type="person",
            canonical_value=f"cascade-{uuid.uuid4().hex[:8]}",
            blocking_key=f"bk-{case_id}-cascade",
            display_value="Cascade Person",
            status="active",
        )
        session.add(entity)
        await session.flush()
        session.add(
            MetricResult(
                case_id=str(case_id),
                entity_id=str(entity.id),
                metric_name="degree",
                raw_value=1.0,
                normalized_score=1.0,
                rank=1,
            )
        )
        await session.commit()
    async with factory() as session:
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()
        remaining = (
            await session.execute(
                select(func.count(MetricResult.id)).where(
                    MetricResult.case_id == str(case_id)
                )
            )
        ).scalar_one()
        assert remaining == 0  # ON DELETE CASCADE removed the metric row
