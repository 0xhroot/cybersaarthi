"""API tests: evidence intelligence foundation endpoints.

Covers the authorization matrix (anonymous 401, non-member 403, member 200),
filter validation, provenance payload shape, the human-review decision flow
including its audit record, and the read-only-case guard.
"""

from __future__ import annotations

import uuid

import httpx
from app.core.codes import CODE_ARTIFACT_NOT_REVIEWABLE, CODE_CASE_READ_ONLY, CODE_INVALID_FILTER
from app.core.config import get_settings
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.redis import Cache
from app.db.storage import Storage
from app.main import app
from app.models import AnalysisJob, AuditLog, Case, DerivedArtifact
from app.services.structured_extraction import canonical_hash
from sqlalchemy import select


def _wire_app() -> None:
    """Attach infrastructure clients for requests built outside http_client."""
    settings = get_settings()
    app.state.database = Database(settings)
    app.state.graph_store = GraphStore(settings)
    app.state.cache = Cache(settings)
    app.state.storage = Storage(settings)
    app.state.settings = settings


async def _seed_artifact(
    database: Database,
    case_id: uuid.UUID,
    *,
    kind: str = "extraction",
    status: str = "pending_review",
    payload: dict | None = None,
) -> uuid.UUID:
    body = payload or {"person_name": "Rahul Patil", "amount": "1000.00"}
    factory = database.session_factory()
    async with factory() as session:
        artifact = DerivedArtifact(
            case_id=str(case_id),
            kind=kind,
            origin="llm",
            status=status,
            validation_status="valid",
            payload=body,
            content_hash=canonical_hash(body),
            parser_version="deterministic:1",
        )
        session.add(artifact)
        await session.commit()
        return artifact.id


async def _seed_job(
    database: Database,
    case_id: uuid.UUID,
    *,
    feature: str = "ingestion",
    status: str = "running",
) -> uuid.UUID:
    factory = database.session_factory()
    async with factory() as session:
        job = AnalysisJob(
            case_id=str(case_id),
            feature=feature,
            status=status,
            idempotency_key=f"seed-{uuid.uuid4().hex[:12]}",
            progress=40,
            total_records=10,
            processed_records=4,
            attempts=1,
            timeout_seconds=600,
            cancel_requested=False,
        )
        session.add(job)
        await session.commit()
        return job.id


async def test_artifacts_require_authentication(_owned_case: uuid.UUID) -> None:
    _wire_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(
            f"/api/v1/cases/{_owned_case}/evidence-intelligence/artifacts"
        )
    assert resp.status_code == 401


async def test_owner_lists_seeded_artifact_with_provenance(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    artifact_id = await _seed_artifact(database, _owned_case)
    resp = await http_client.get(f"/api/v1/cases/{_owned_case}/evidence-intelligence/artifacts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    item = next(i for i in body["items"] if i["id"] == str(artifact_id))
    assert item["kind"] == "extraction"
    assert item["origin"] == "llm"
    assert item["status"] == "pending_review"
    expected_hash = canonical_hash({"person_name": "Rahul Patil", "amount": "1000.00"})
    assert item["content_hash"] == expected_hash
    assert item["payload"] == {"person_name": "Rahul Patil", "amount": "1000.00"}
    assert item["case_id"] == str(_owned_case)


async def test_artifact_filters_and_invalid_filter_rejected(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    await _seed_artifact(database, _owned_case, kind="extraction")
    await _seed_artifact(
        database, _owned_case, kind="contradiction", payload={"claim": "amount differs"}
    )
    base = f"/api/v1/cases/{_owned_case}/evidence-intelligence/artifacts"

    matching = (await http_client.get(f"{base}?kind=extraction")).json()
    assert {i["kind"] for i in matching["items"]} <= {"extraction"}
    assert matching["total"] >= 1

    by_status = (await http_client.get(f"{base}?status=approved")).json()
    assert by_status["total"] == 0

    invalid = await http_client.get(f"{base}?kind=telepathy")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == CODE_INVALID_FILTER


async def test_non_member_gets_403_on_stranger_case(
    http_client: httpx.AsyncClient,
    database: Database,
    _stranger_case: uuid.UUID,
) -> None:
    await _seed_artifact(database, _stranger_case)
    resp = await http_client.get(
        f"/api/v1/cases/{_stranger_case}/evidence-intelligence/artifacts"
    )
    assert resp.status_code == 403


async def test_owner_lists_analysis_jobs_with_filters(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    job_id = await _seed_job(database, _owned_case, feature="ingestion", status="running")
    base = f"/api/v1/cases/{_owned_case}/evidence-intelligence/jobs"

    resp = await http_client.get(base)
    assert resp.status_code == 200
    body = resp.json()
    item = next(i for i in body["items"] if i["id"] == str(job_id))
    assert item["feature"] == "ingestion"
    assert item["status"] == "running"
    assert item["progress"] == 40
    assert item["idempotency_key"].startswith("seed-")

    filtered = (await http_client.get(f"{base}?feature=report_audit")).json()
    assert all(i["feature"] == "report_audit" for i in filtered["items"])

    invalid = await http_client.get(f"{base}?status=telepathy")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == CODE_INVALID_FILTER


async def test_non_member_gets_403_on_stranger_jobs(
    http_client: httpx.AsyncClient,
    _stranger_case: uuid.UUID,
) -> None:
    resp = await http_client.get(
        f"/api/v1/cases/{_stranger_case}/evidence-intelligence/jobs"
    )
    assert resp.status_code == 403


async def test_review_approval_records_reviewer_and_audit(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user,
) -> None:
    artifact_id = await _seed_artifact(database, _owned_case)
    resp = await http_client.post(
        f"/api/v1/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact_id}/review",
        json={"decision": "approved", "note": "matches source record 3"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == str(api_user.id)
    assert body["review_note"] == "matches source record 3"
    assert body["reviewed_at"] is not None

    factory = database.session_factory()
    async with factory() as session:
        audit = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "derived_artifact.approved",
                    AuditLog.resource_id == str(artifact_id),
                )
            )
        ).scalar_one_or_none()
    assert audit is not None
    assert str(audit.case_id) == str(_owned_case)


async def test_review_is_one_shot(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    artifact_id = await _seed_artifact(database, _owned_case)
    url = f"/api/v1/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact_id}/review"
    first = await http_client.post(url, json={"decision": "rejected", "note": "wrong source"})
    assert first.status_code == 200
    second = await http_client.post(url, json={"decision": "approved"})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == CODE_ARTIFACT_NOT_REVIEWABLE


async def test_review_rejects_unknown_artifact(
    http_client: httpx.AsyncClient,
    _owned_case: uuid.UUID,
) -> None:
    resp = await http_client.post(
        f"/api/v1/cases/{_owned_case}/evidence-intelligence/artifacts/{uuid.uuid4()}/review",
        json={"decision": "approved"},
    )
    assert resp.status_code == 404


async def test_review_rejects_invalid_decision_payload(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    artifact_id = await _seed_artifact(database, _owned_case)
    resp = await http_client.post(
        f"/api/v1/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact_id}/review",
        json={"decision": "auto_approved"},
    )
    assert resp.status_code == 422


async def test_viewer_role_cannot_review(
    database: Database,
    user_factory,
    _owned_case: uuid.UUID,
) -> None:
    viewer = await user_factory(role="VIEWER")
    artifact_id = await _seed_artifact(database, _owned_case)
    _wire_app()
    headers = {"Authorization": f"Bearer {viewer.token}"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", headers=headers
    ) as client:
        resp = await client.post(
            f"/api/v1/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact_id}/review",
            json={"decision": "approved"},
        )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSION"


async def test_review_blocked_on_read_only_case(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    factory = database.session_factory()
    async with factory() as session:
        case = await session.get(Case, _owned_case)
        assert case is not None
        case.status = "closed"
        await session.commit()

    artifact_id = await _seed_artifact(database, _owned_case)
    resp = await http_client.post(
        f"/api/v1/cases/{_owned_case}/evidence-intelligence/artifacts/{artifact_id}/review",
        json={"decision": "approved"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == CODE_CASE_READ_ONLY


async def test_filters_and_paging_are_bounded(
    http_client: httpx.AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    await _seed_artifact(database, _owned_case)
    base = f"/api/v1/cases/{_owned_case}/evidence-intelligence/artifacts"
    assert (await http_client.get(f"{base}?limit=0")).status_code == 422
    assert (await http_client.get(f"{base}?limit=501")).status_code == 422
    page = (await http_client.get(f"{base}?limit=1&offset=0")).json()
    assert page["limit"] == 1
    assert len(page["items"]) <= 1
