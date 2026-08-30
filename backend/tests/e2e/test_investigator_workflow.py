"""End-to-end workflow test: the seeded investigator drives a real case.

Bootstraps the documented ``admin`` / ``investigator`` accounts via the
idempotent ``scripts.seed_users.ensure_seed_users`` (the same accounts the
README and Phase 4 docs reference), then drives the full product lifecycle over
the public API: register -> login -> case -> evidence -> ingest -> analytics ->
findings review/confirm -> audit trail.
"""

from __future__ import annotations

import os
import uuid

import httpx
from app.core.config import get_settings
from app.db.postgres import Database
from app.main import app
from app.models import Case, User
from scripts.seed_users import (
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    DEFAULT_INVESTIGATOR_PASSWORD,
    DEFAULT_INVESTIGATOR_USERNAME,
    ensure_seed_users,
)
from sqlalchemy import delete

CSV_BYTES = (
    b"name,phone,organization,vehicle_no,city\n"
    b"Rajesh Kumar,9876543210,TechSecure Pvt Ltd,MH12AB1234,Mumbai\n"
    b"Rajesh Kumar,9876543211,TechSecure Pvt Ltd,MH12AB1234,Mumbai\n"
).decode()


async def _seed(database: Database) -> None:
    factory = database.session_factory()
    async with factory() as session:
        await ensure_seed_users(session)
        await session.commit()


def _client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )


async def _login(username: str, password: str) -> str:
    async with _client("") as anon:
        prefix = get_settings().API_V1_PREFIX
        response = await anon.post(
            f"{prefix}/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 200, response.text
        return response.json()["access_token"]


async def _login_admin() -> str:
    return await _login(
        DEFAULT_ADMIN_USERNAME,
        os.environ.get("SEED_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD),
    )


async def test_investigator_end_to_end_workflow(
    database: Database,
) -> None:
    prefix = get_settings().API_V1_PREFIX
    await _seed(database)

    # ADMIN logs in and registers a fresh analyst over the public API.
    admin_token = await _login_admin()
    analyst_username = f"e2e-analyst-{uuid.uuid4().hex[:8]}"
    async with _client(admin_token) as admin:
        registered = await admin.post(
            f"{prefix}/auth/register",
            json={
                "username": analyst_username,
                "email": f"{analyst_username}@cybersaarthi.test",
                "password": "e2e-analyst-password!",
                "role": "ANALYST",
            },
        )
        assert registered.status_code == 201, registered.text

    # INVESTIGATOR logs in and drives the case lifecycle.
    investigator_token = await _login(DEFAULT_INVESTIGATOR_USERNAME, DEFAULT_INVESTIGATOR_PASSWORD)
    case_id: str | None = None
    evidence_id: str | None = None
    confirmed_finding: str | None = None
    try:
        async with _client(investigator_token) as inv:
            created = await inv.post(f"{prefix}/cases", json={"title": "E2E phishing ring"})
            assert created.status_code == 201, created.text
            case_id = created.json()["id"]

            uploaded = await inv.post(
                f"{prefix}/cases/{case_id}/evidence",
                files={"file": ("citizens.csv", CSV_BYTES.encode(), "text/csv")},
                data={"data_source": "police_csv"},
            )
            assert uploaded.status_code == 201, uploaded.text
            evidence_id = uploaded.json()["id"]

            ingested = await inv.post(
                f"{prefix}/cases/{case_id}/ingest",
                json={"evidence_file_id": evidence_id, "metadata": {"source": "e2e"}},
            )
            assert ingested.status_code == 200, ingested.text
            assert ingested.json()["job"]["status"] == "completed"

            ran = await inv.post(f"{prefix}/cases/{case_id}/analytics/run")
            assert ran.status_code == 201, ran.text
            assert ran.json()["status"] == "completed"

            findings = await inv.get(f"{prefix}/cases/{case_id}/findings")
            assert findings.status_code == 200
            new_findings = [f for f in findings.json()["items"] if f["status"] == "NEW"]
            assert new_findings, "analytics must produce NEW findings"

            reviewed = await inv.patch(
                f"{prefix}/cases/{case_id}/findings/{new_findings[0]['id']}/status",
                json={"status": "REVIEWED", "reason": "reviewed for E2E"},
            )
            assert reviewed.status_code == 200, reviewed.text

            confirmed_finding = new_findings[0]["id"]
            confirmed = await inv.patch(
                f"{prefix}/cases/{case_id}/findings/{confirmed_finding}/status",
                json={"status": "CONFIRMED", "reason": "confirmed for E2E"},
            )
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["status"] == "CONFIRMED"

        # Both the administrator and the investigator can read the audit trail.
        events = _client(admin_token)
        async with events:
            audit = await events.get(
                f"{prefix}/audit-logs",
                params={"case_id": case_id, "action": "finding.status_changed"},
            )
        assert audit.status_code == 200, audit.text
        statuses = {item["metadata_"]["to"] for item in audit.json()["items"]}
        assert {"REVIEWED", "CONFIRMED"} <= statuses

        # The registered analyst (ANALYST) is credited and can log in, but the
        # analyst role must not manage users.
        async with _client(await _login(analyst_username, "e2e-analyst-password!")) as analyst:
            me = await analyst.get(f"{prefix}/auth/me")
            assert me.status_code == 200
            assert "ANALYST" in me.json()["roles"]
            assert (
                await analyst.post(
                    f"{prefix}/auth/register",
                    json={
                        "username": "nope",
                        "email": "nope@cybersaarthi.test",
                        "password": "whatever123",
                    },
                )
            ).status_code == 403
    finally:
        factory = database.session_factory()
        async with factory() as session:
            if case_id is not None:
                await session.execute(delete(Case).where(Case.id == case_id))
            if analyst_username:
                await session.execute(delete(User).where(User.username == analyst_username))
            await session.commit()
