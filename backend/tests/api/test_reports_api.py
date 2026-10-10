"""Report API contract: generation, every format, downloads, validation, isolation.

Covers the PDF generation failure end to end (the bug that stored every
multi-row PDF as ``failed``) plus JSON/CSV regression, empty datasets, unicode,
invalid inputs, renderer/storage failure handling, authorization and download
semantics (MIME type, filename, non-empty body, parsed with a real PDF reader).
"""

from __future__ import annotations

import io
import re
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from app.core.config import get_settings
from app.db.postgres import Database
from app.db.storage import Storage
from app.main import app
from app.models import (
    REPORT_TYPES,
    Case,
    Entity,
    EvidenceFile,
    Finding,
    Relationship,
    TimelineEvent,
)
from app.services import reporting as rpt_svc
from pypdf import PdfReader
from sqlalchemy import delete

from tests.api.conftest import ApiUser

PREFIX = get_settings().API_V1_PREFIX

UNICODE_VALUE = "Fatima \u2019Shaikh \u2014 \u201cQueen\u201d \u20b91,000,000"
WANT_UNICODE = 'Fatima \'Shaikh - "Queen" Rs.1,000,000'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def report_case(database: Database, api_user: ApiUser, storage: Storage):
    """A case with real entities/evidence/findings/relationships/timeline rows,
    including unicode values; objects are purged on teardown."""
    case = Case(
        id=uuid.uuid4(),
        case_number=f"RPT-{uuid.uuid4().hex[:8]}",
        title="report api test case",
        owner_id=api_user.id,
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.flush()
        case_id = case.id

        values = [
            "Rajesh Kumar",
            "TechSecure Pvt Ltd",
            "MH12AB1234",
            UNICODE_VALUE,
            "na\u00efve caf\u00e9 \u2192 verified",
            "\u65e5\u672c\u8a9e\u306e\u8a3c\u62e0 \U0001f614",
        ]
        entities = [
            Entity(
                case_id=str(case_id),
                entity_type="person" if i % 2 == 0 else "organization",
                canonical_value=value.lower(),
                blocking_key=f"person|{i}",
                display_value=value,
                status="active",
            )
            for i, value in enumerate(values)
        ]
        session.add_all(entities)
        await session.flush()
        entity_ids = [str(entity.id) for entity in entities]

        for i in range(2):
            session.add(
                EvidenceFile(
                    case_id=str(case_id),
                    original_filename=f"evidence-{i}.txt",
                    stored_key=f"cases/{case_id}/evidence/evidence-{i}.txt",
                    content_type="text/plain",
                    file_size=12,
                    sha256=f"{i:02x}" * 32,
                )
            )
        for i in range(3):
            session.add(
                Finding(
                    case_id=str(case_id),
                    finding_type="pattern",
                    title=f"Finding {i}",
                    summary=f"summary {i}",
                    severity="HIGH",
                    score=0.9,
                    explanation={"note": "test"},
                )
            )
        for i in range(len(entity_ids) - 1):
            session.add(
                Relationship(
                    case_id=str(case_id),
                    source_entity_id=entity_ids[i],
                    target_entity_id=entity_ids[i + 1],
                    relationship_type="associated_with",
                    confidence=0.8,
                )
            )
        for i in range(4):
            session.add(
                TimelineEvent(
                    case_id=str(case_id),
                    occurred_at=datetime.now(UTC),
                    kind="collection_created",
                    title=f"Event {i}",
                    description=f"timeline event {i}",
                )
            )
        await session.commit()

    yield case_id, database

    keys = storage.list_keys(f"reports/{case_id}/")
    if keys:
        storage.delete_objects(keys)
    async with factory() as session:
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()


# ---------------------------------------------------------------------------
# Happy path: every report type in every format
# ---------------------------------------------------------------------------


async def _generate(http_client, case_id, body, headers=None):
    return await http_client.post(f"{PREFIX}/cases/{case_id}/reports", json=body, headers=headers)


def _pdf_text_of(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    assert not reader.is_encrypted
    assert len(reader.pages) >= 1
    return "\n".join(page.extract_text() or "" for page in reader.pages)


@pytest.mark.parametrize("report_type", REPORT_TYPES)
async def test_pdf_report_generates_and_downloads(http_client, report_case, report_type) -> None:
    case_id, _ = report_case
    resp = await _generate(
        http_client,
        case_id,
        {
            "report_type": report_type,
            "format": "pdf",
            "title": f"{report_type.replace('_', ' ')} PDF",
        },
    )
    assert resp.status_code == 201, resp.text
    report = resp.json()
    assert report["status"] == "ready", report.get("failure_reason")
    assert report["format"] == "pdf"
    assert (report["byte_size"] or 0) > 1_000
    assert report["failure_reason"] is None

    listed = await http_client.get(f"{PREFIX}/cases/{case_id}/reports")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    download = await http_client.get(f"{PREFIX}/cases/{case_id}/reports/{report['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    disposition = download.headers["content-disposition"]
    assert disposition.startswith("attachment; filename=")
    assert disposition.endswith('.pdf"')
    assert len(download.content) > 1_000

    # real parser, not leading bytes
    text = _pdf_text_of(download.content)
    compact = "".join(text.split())
    assert str(case_id) in compact  # cover block carries the case identifier
    assert report_type.replace("_", " ").lower() in text.lower()
    if report_type == "timeline":
        # timeline reports contain event rows, not entity rows
        assert "Event 0" in text.replace("\n", " ")
        assert "timeline event 3" in text.replace("\n", " ")
    else:
        assert "Rajesh" in text and "Kumar" in text  # entity rows reach the document
        assert WANT_UNICODE in text.replace("\n", " ")  # unicode rendered, not dropped
        assert "na\u00efve caf\u00e9" in text.replace("\n", " ")


@pytest.mark.parametrize("report_type", REPORT_TYPES)
async def test_json_report_generates_and_downloads(http_client, report_case, report_type) -> None:
    case_id, _ = report_case
    resp = await _generate(http_client, case_id, {"report_type": report_type, "format": "json"})
    assert resp.status_code == 201, resp.text
    report = resp.json()
    assert report["status"] == "ready"
    assert (report["byte_size"] or 0) > 0

    download = await http_client.get(f"{PREFIX}/cases/{case_id}/reports/{report['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/json"
    assert download.headers["content-disposition"].endswith('.json"')
    payload = download.json()
    if report_type == "timeline":
        assert isinstance(payload, list) and payload
        assert {"occurred_at", "kind", "title", "description"} <= set(payload[0])
    else:
        assert payload["case_id"] == str(case_id)
        assert len(payload["entities"]) == 6


@pytest.mark.parametrize("report_type", REPORT_TYPES)
async def test_csv_report_generates_and_downloads(http_client, report_case, report_type) -> None:
    case_id, _ = report_case
    resp = await _generate(http_client, case_id, {"report_type": report_type, "format": "csv"})
    assert resp.status_code == 201, resp.text
    report = resp.json()
    assert report["status"] == "ready"

    download = await http_client.get(f"{PREFIX}/cases/{case_id}/reports/{report['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    body = download.content.decode("utf-8")
    if report_type == "timeline":
        assert body.splitlines()[0] == "occurred_at,kind,title,description"
    else:
        assert body.splitlines()[0] == "kind,id,type,value,status"


async def test_pdf_report_for_empty_case(
    http_client, api_user, database: Database, storage: Storage
) -> None:
    """A case with no entities/evidence still yields a downloadable PDF."""
    case = Case(
        id=uuid.uuid4(),
        case_number=f"RPTEM-{uuid.uuid4().hex[:8]}",
        title="empty case for reports",
        owner_id=api_user.id,
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.commit()
        case_id = case.id
    try:
        resp = await _generate(
            http_client, case_id, {"report_type": "case_summary", "format": "pdf"}
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "ready"
        download = await http_client.get(
            f"{PREFIX}/cases/{case_id}/reports/{resp.json()['id']}/download"
        )
        assert download.status_code == 200
        text = _pdf_text_of(download.content)
        assert "No records." in text
        assert str(case_id) in "".join(text.split())
    finally:
        keys = storage.list_keys(f"reports/{case_id}/")
        if keys:
            storage.delete_objects(keys)
        async with factory() as session:
            await session.execute(delete(Case).where(Case.id == case_id))
            await session.commit()


# ---------------------------------------------------------------------------
# Validation: unknown inputs must be rejected before a row is created
# ---------------------------------------------------------------------------


async def test_unknown_report_type_returns_422(http_client, report_case) -> None:
    case_id, _ = report_case
    before = (await http_client.get(f"{PREFIX}/cases/{case_id}/reports")).json()["total"]
    resp = await _generate(http_client, case_id, {"report_type": "diagnostic", "format": "json"})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    after = (await http_client.get(f"{PREFIX}/cases/{case_id}/reports")).json()["total"]
    assert after == before  # no orphaned failed row


async def test_unknown_format_returns_422(http_client, report_case) -> None:
    case_id, _ = report_case
    resp = await _generate(http_client, case_id, {"report_type": "case_summary", "format": "xlsx"})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_oversized_title_returns_422(http_client, report_case) -> None:
    case_id, _ = report_case
    resp = await _generate(
        http_client,
        case_id,
        {"report_type": "case_summary", "format": "pdf", "title": "x" * 256},
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Failure handling: concise reason in the API, stack trace in the log
# ---------------------------------------------------------------------------


async def test_renderer_failure_stores_concise_reason_and_logs_traceback(
    http_client, report_case, monkeypatch, caplog
) -> None:
    case_id, _ = report_case

    def _boom(*_args, **_kwargs) -> bytes:
        raise RuntimeError("simulated renderer crash at /srv/internal/path.py:42")

    monkeypatch.setattr(rpt_svc, "_build_pdf", _boom)
    with caplog.at_level("ERROR", logger="app.services.reporting"):
        resp = await _generate(
            http_client,
            case_id,
            {"report_type": "case_summary", "format": "pdf"},
            headers={"X-Request-Id": "pdf-fail-req-1"},
        )
    assert resp.status_code == 201, resp.text
    report = resp.json()
    assert report["status"] == "failed"
    reason = report["failure_reason"]
    assert reason is not None
    # concise category + correlation id; no stack trace / raw message / paths
    assert reason.startswith("generation_failed:RuntimeError")
    assert "request_id=pdf-fail-req-1" in reason
    assert "Traceback" not in reason
    assert "/srv/internal" not in reason
    # full detail lives in the server log
    assert any("report generation failed" in rec.getMessage() for rec in caplog.records)
    assert any(rec.exc_info for rec in caplog.records)

    # failed reports are not downloadable
    download = await http_client.get(f"{PREFIX}/cases/{case_id}/reports/{report['id']}/download")
    assert download.status_code == 409


async def test_storage_failure_marks_report_failed(http_client, report_case, monkeypatch) -> None:
    case_id, _ = report_case

    class _BoomClient:
        def put_object(self, **_kwargs):
            raise TimeoutError("object store unavailable")

    monkeypatch.setattr(app.state.storage, "_client", _BoomClient())
    resp = await _generate(http_client, case_id, {"report_type": "case_summary", "format": "json"})
    assert resp.status_code == 201, resp.text
    report = resp.json()
    assert report["status"] == "failed"
    assert report["failure_reason"].startswith("generation_failed:TimeoutError")
    assert report["byte_size"] is None
    assert report["id"]  # row is kept, but never claims success
    download = await http_client.get(f"{PREFIX}/cases/{case_id}/reports/{report['id']}/download")
    assert download.status_code == 409


# ---------------------------------------------------------------------------
# Authorization, case isolation, download binding
# ---------------------------------------------------------------------------


async def test_report_endpoints_require_authentication(http_client, report_case) -> None:
    case_id, _ = report_case
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as anon:
        assert (await anon.get(f"{PREFIX}/cases/{case_id}/reports")).status_code == 401
        resp = await anon.post(
            f"{PREFIX}/cases/{case_id}/reports",
            json={"report_type": "case_summary", "format": "json"},
        )
        assert resp.status_code == 401


async def test_reports_are_denied_for_non_member_case(
    http_client, user_factory, database: Database
) -> None:
    """A case owned by another user is 403 for report generate/list."""
    other = await user_factory(role="INVESTIGATOR")
    case = Case(
        id=uuid.uuid4(),
        case_number=f"RPTX-{uuid.uuid4().hex[:8]}",
        title="someone elses case",
        owner_id=other.id,
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.commit()
        case_id = case.id
    try:
        resp = await _generate(http_client, case_id, {"report_type": "case_summary"})
        assert resp.status_code == 403, resp.text
        assert (await http_client.get(f"{PREFIX}/cases/{case_id}/reports")).status_code == 403
    finally:
        async with factory() as session:
            await session.execute(delete(Case).where(Case.id == case_id))
            await session.commit()


async def test_download_rejects_report_from_another_case(
    http_client, report_case, api_user: ApiUser
) -> None:
    """A report id must be presented under its own case path."""
    case_id, database = report_case
    resp = await _generate(http_client, case_id, {"report_type": "case_summary", "format": "json"})
    report = resp.json()

    # second case owned by the same user: accessible, but not this report's case
    other_case = Case(
        id=uuid.uuid4(),
        case_number=f"RPTB-{uuid.uuid4().hex[:8]}",
        title="second case for binding test",
        owner_id=api_user.id,
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(other_case)
        await session.commit()
        other_id = other_case.id
    try:
        wrong = await http_client.get(f"{PREFIX}/cases/{other_id}/reports/{report['id']}/download")
        assert wrong.status_code == 404
        meta = await http_client.get(f"{PREFIX}/cases/{other_id}/reports/{report['id']}")
        assert meta.status_code == 404
        # under its own case the report is still reachable
        ok = await http_client.get(f"{PREFIX}/cases/{case_id}/reports/{report['id']}/download")
        assert ok.status_code == 200
    finally:
        async with factory() as session:
            await session.execute(delete(Case).where(Case.id == other_id))
            await session.commit()


# ---------------------------------------------------------------------------
# Filename sanitisation
# ---------------------------------------------------------------------------


async def test_download_filename_is_sanitised(http_client, report_case) -> None:
    case_id, _ = report_case
    hostile_title = 'Quarterly "review" / 2026\treport'
    resp = await _generate(
        http_client,
        case_id,
        {"report_type": "case_summary", "format": "json", "title": hostile_title},
    )
    assert resp.status_code == 201, resp.text
    download = await http_client.get(
        f"{PREFIX}/cases/{case_id}/reports/{resp.json()['id']}/download"
    )
    assert download.status_code == 200
    disposition = download.headers["content-disposition"]
    match = re.search(r'filename="([^"]+)"', disposition)
    assert match is not None
    filename = match.group(1)
    assert "/" not in filename
    assert '"' not in filename
    assert "\t" not in filename
    assert filename.endswith(".json")
