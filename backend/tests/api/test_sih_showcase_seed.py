"""SIH showcase seed integration tests.

The seed is exercised through the public HTTP API against the in-process app
(``ASGITransport``), exactly as ``make demo-seed`` drives a live stack: no
step bypasses authentication, case access control, ingestion, or review
workflows. The stable showcase case numbers are monkeypatched to a test-only
pair (``SIH-2026-901/902``) so the suite can never collide with - or delete -
a real showcase dataset; teardown reuses the seed's own guarded reset, which
only ever targets the currently patched numbers.
"""

from __future__ import annotations

import io
import uuid

import httpx
import pytest
from app.core.config import Settings
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.redis import Cache
from app.db.storage import Storage
from app.main import app
from app.models import Case, CaseMember
from scripts import showcase_seed
from sqlalchemy import delete, select

from tests.api.phase2_fakes import FakeAI

TEST_PRIMARY = "SIH-2026-901"
TEST_SUPPORT = "SIH-2026-902"
TEST_NUMBERS = (TEST_PRIMARY, TEST_SUPPORT)


@pytest.fixture
def seed_env(monkeypatch):
    """Point the seed's stable ids at a test-only pair (isolation guard)."""
    monkeypatch.setattr(
        showcase_seed,
        "PRIMARY_CASE",
        {**showcase_seed.PRIMARY_CASE, "case_number": TEST_PRIMARY},
    )
    monkeypatch.setattr(
        showcase_seed,
        "SUPPORT_CASE",
        {**showcase_seed.SUPPORT_CASE, "case_number": TEST_SUPPORT},
    )
    monkeypatch.setattr(showcase_seed, "SHOWCASE_CASE_NUMBERS", TEST_NUMBERS)
    monkeypatch.setattr(
        showcase_seed,
        "PRIMARY_FILES",
        [
            (name, source, ctype, TEST_PRIMARY)
            for name, source, ctype, _ in showcase_seed.PRIMARY_FILES
        ],
    )
    monkeypatch.setattr(
        showcase_seed,
        "SUPPORT_FILES",
        [
            (name, source, ctype, TEST_SUPPORT)
            for name, source, ctype, _ in showcase_seed.SUPPORT_FILES
        ],
    )


@pytest.fixture
async def admin_client(database: Database, settings: Settings, user_factory):
    admin = await user_factory(role="ADMIN")
    app.state.database = database
    app.state.graph_store = GraphStore(settings)
    app.state.cache = Cache(settings)
    app.state.storage = Storage(settings)
    app.state.settings = settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver/api/v1",
        headers={"Authorization": f"Bearer {admin.token}"},
    ) as client:
        yield client


@pytest.fixture
def fake_ai(monkeypatch):
    """Deterministic stand-in so the full seed reaches every capability."""
    fake = FakeAI()
    monkeypatch.setattr(app.state, "ai_service", fake, raising=False)
    return fake


async def _cases_by_number(client: httpx.AsyncClient, numbers: tuple[str, ...]) -> dict[str, dict]:
    items = await showcase_seed._list_all(client, "/cases", limit=200)
    return {c["case_number"]: c for c in items if c["case_number"] in numbers}


async def _evidence_by_name(client: httpx.AsyncClient, case_id: str) -> dict[str, dict]:
    items = await showcase_seed._case_evidence(client, case_id)
    return {e["original_filename"]: e for e in items}


async def _counts(client: httpx.AsyncClient, case_id: str) -> dict[str, int]:
    """Row counts that must never grow on a re-run."""
    evidence = await _evidence_by_name(client, case_id)
    statement = evidence["merchant_statement.csv"]
    custody = await showcase_seed._get(
        client, f"/cases/{case_id}/evidence/{statement['id']}/custody"
    )
    timeline = await showcase_seed._get(client, f"/cases/{case_id}/timeline", limit=1)
    findings = await showcase_seed._get(client, f"/cases/{case_id}/findings", limit=1)
    audits = await showcase_seed._get(client, f"/cases/{case_id}/report-audits", limit=1)
    kinds: dict[str, int] = {}
    for kind in (
        "contradiction",
        "financial_finding",
        "triage_observation",
        "translation",
        "report_claim_review",
    ):
        data = await showcase_seed._get(
            client,
            f"/cases/{case_id}/evidence-intelligence/artifacts",
            kind=kind,
            limit=1,
        )
        kinds[kind] = data["total"]
    return {
        "evidence": len(evidence),
        "custody_events": custody["event_count"],
        "timeline": timeline["total"],
        "findings": findings["total"],
        "audits": audits["total"],
        **{f"artifacts:{kind}": total for kind, total in kinds.items()},
    }


async def _create_unrelated_case(client: httpx.AsyncClient) -> tuple[str, str]:
    """A real-world case owned by this admin, with one uploaded exhibit."""
    number = f"UNRELATED-{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/cases",
        json={"case_number": number, "title": "genuine unrelated work", "status": "in_progress"},
    )
    assert resp.status_code == 201, resp.text
    case_id = resp.json()["id"]
    upload = await client.post(
        f"/cases/{case_id}/evidence",
        files={"file": ("notes.txt", b"unrelated real notes\n", "text/plain")},
        data={"data_source": "txt"},
    )
    assert upload.status_code == 201, upload.text
    return case_id, number


@pytest.fixture
async def showcase_cleanup(seed_env):
    """Always remove the test showcase pair, even when a test dies midway.

    Depends on ``seed_env`` so the monkeypatch is still active during teardown
    (dependent fixtures finalize first): the reset can only ever target the
    patched test numbers.
    """
    yield
    await showcase_seed.run_reset("development", "sih-showcase", io.StringIO())


@pytest.fixture
async def unrelated_rows(database: Database):
    """Collects unrelated-case ids for teardown hygiene (no case DELETE API)."""
    created: list[str] = []
    yield created
    factory = database.session_factory()
    async with factory() as session:
        for case_id in created:
            await session.execute(
                delete(CaseMember).where(CaseMember.case_id == uuid.UUID(case_id))
            )
            await session.execute(delete(Case).where(Case.id == uuid.UUID(case_id)))
        await session.commit()


async def test_seed_is_idempotent_keeps_unrelated_cases_and_resets_safely(
    admin_client, seed_env, fake_ai, showcase_cleanup, unrelated_rows
):
    unrelated_id, unrelated_number = await _create_unrelated_case(admin_client)
    unrelated_rows.append(unrelated_id)

    # --- run 1: everything is created through real API workflows ------------
    report1 = await showcase_seed.run_seed(admin_client, member_user_id=None, job_timeout=120)
    assert not report1.failed, report1.render()
    created1 = {s.name for s in report1.steps if s.action == "created"}
    assert f"case {TEST_PRIMARY}" in created1
    assert f"case {TEST_SUPPORT}" in created1

    cases = await _cases_by_number(admin_client, TEST_NUMBERS)
    assert set(cases) == set(TEST_NUMBERS)
    primary_id = cases[TEST_PRIMARY]["id"]

    # every capability produced its artifact through the public API
    evidence = await _evidence_by_name(admin_client, primary_id)
    assert len(evidence) == 6
    assert all(ev["status"] == "parsed" for ev in evidence.values())

    statement = evidence["merchant_statement.csv"]
    custody = await showcase_seed._get(
        admin_client, f"/cases/{primary_id}/evidence/{statement['id']}/custody"
    )
    assert custody["event_count"] == 4

    artifacts = await showcase_seed._get(
        admin_client,
        f"/cases/{primary_id}/evidence-intelligence/artifacts",
        kind="contradiction",
        limit=10,
    )
    assert artifacts["total"] == 1
    conflicts = artifacts["items"][0]["payload"].get("conflicting_values") or []
    assert conflicts and conflicts[0]["field"] == "amount"

    review = await showcase_seed._get(
        admin_client, f"/cases/{primary_id}/resolution/review", limit=50
    )
    assert review["total"] >= 1  # matches exist and stay pending human review
    assert all(m["decision"] in ("review", "pending_review") for m in review["items"])

    candidates = await showcase_seed._get(
        admin_client, "/cross-case/candidates", anchor_case_id=primary_id, limit=50
    )
    assert candidates["total"] >= 1

    timeline = await showcase_seed._get(admin_client, f"/cases/{primary_id}/timeline", limit=1)
    assert timeline["total"] >= 13  # committed proposals + curated events

    findings = await showcase_seed._get(admin_client, f"/cases/{primary_id}/findings", limit=1)
    assert findings["total"] >= 1  # analytics run persisted findings

    audits = await showcase_seed._get(admin_client, f"/cases/{primary_id}/report-audits", limit=20)
    assert any(a["status"] == "succeeded" for a in audits["items"])
    translations = await showcase_seed._get(
        admin_client,
        f"/cases/{primary_id}/evidence-intelligence/artifacts",
        kind="translation",
        limit=10,
    )
    assert translations["total"] >= 1

    before = await _counts(admin_client, primary_id)

    # --- run 2: pure idempotency, nothing new, nothing re-created -----------
    report2 = await showcase_seed.run_seed(admin_client, member_user_id=None, job_timeout=120)
    assert not report2.failed, report2.render()
    assert not [s for s in report2.steps if s.action == "created"], [
        s.name for s in report2.steps if s.action == "created"
    ]
    assert await _counts(admin_client, primary_id) == before

    # --- unrelated case: untouched by seed and rerun ------------------------
    unrelated = await showcase_seed._get(admin_client, "/cases", limit=200)
    by_number = {c["case_number"]: c for c in unrelated["items"]}
    assert by_number[unrelated_number]["title"] == "genuine unrelated work"
    unrelated_evidence = await _evidence_by_name(admin_client, unrelated_id)
    assert list(unrelated_evidence) == ["notes.txt"]

    # --- reset: guarded, and scoped strictly to the showcase pair -----------
    out = io.StringIO()
    assert await showcase_seed.run_reset("production", "sih-showcase", out) == 2
    assert "REFUSED" in out.getvalue()
    assert set(await _cases_by_number(admin_client, TEST_NUMBERS)) == set(TEST_NUMBERS)

    out = io.StringIO()
    assert await showcase_seed.run_reset("development", None, out) == 2
    assert "DEMO_RESET_CONFIRM" in out.getvalue()
    assert set(await _cases_by_number(admin_client, TEST_NUMBERS)) == set(TEST_NUMBERS)

    out = io.StringIO()
    assert await showcase_seed.run_reset("development", "sih-showcase", out) == 0
    assert not await _cases_by_number(admin_client, TEST_NUMBERS)
    survivor = await _cases_by_number(admin_client, (unrelated_number,))
    assert survivor[unrelated_number]["title"] == "genuine unrelated work"
    assert list(await _evidence_by_name(admin_client, unrelated_id)) == ["notes.txt"]


async def test_seed_requires_an_authorized_client(seed_env, database: Database):
    """No auth header: the seed dies on the API's 401 and writes nothing."""
    factory = database.session_factory()
    async with factory() as session:
        await session.execute(delete(Case).where(Case.case_number.in_(TEST_NUMBERS)))
        await session.commit()

    app.state.database = database
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver/api/v1") as anon:
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            await showcase_seed.run_seed(anon, member_user_id=None, job_timeout=30)
        assert "401" in str(excinfo.value)

    async with factory() as session:
        rows = (
            await session.execute(select(Case.id).where(Case.case_number.in_(TEST_NUMBERS)))
        ).all()
    assert rows == []  # the aborted run created no showcase cases at all
