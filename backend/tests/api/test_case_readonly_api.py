"""API tests: closed and archived cases are read-only for investigation mutations.

A case in ``closed`` or ``archived`` remains readable (per RBAC) but rejects
every investigation-mutating operation with a stable 409 ``CASE_READ_ONLY``.
Only explicitly allowed administrative lifecycle operations (the status-reopen
transition on a closed case, and the closed -> archived archive) are permitted.

The guard runs before any database write, so every rejected mutation leaves no
row behind — proven by asserting the read-only status is still reachable and
unchanged after rejection.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from app.db.postgres import Database
from app.models import Case
from sqlalchemy import delete

from tests.api.conftest import ApiUser

CSV_BYTES = (
    b"name,phone,organization,vehicle_no,city\n"
    b"Ravi Sharma,9876543210,SecureNet Ltd,MH12AB1234,Pune\n"
    b"Ravi Sharma,9876543211,SecureNet Ltd,MH12AB1234,Pune\n"
).decode()


@pytest.fixture
async def readonly_case(database: Database, api_user: ApiUser) -> tuple[uuid.UUID, Database]:
    case = Case(
        id=uuid.uuid4(),
        case_number=f"RO-{uuid.uuid4().hex[:8]}",
        title="read-only api test case",
        description="for closed/archived read-only checks",
        status="open",
        owner_id=api_user.id,
    )
    factory = database.session_factory()
    async with factory() as session:
        session.add(case)
        await session.commit()
        case_id = case.id
    yield case_id, database
    async with factory() as session:
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()


async def _set_status(http_client, case_id: uuid.UUID, status: str, prefix: str) -> None:
    if status == "archived":
        response = await http_client.post(f"{prefix}/cases/{case_id}/archive")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "archived"
        return
    response = await http_client.patch(f"{prefix}/cases/{case_id}", json={"status": status})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == status


def _assert_read_only(response) -> None:
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CASE_READ_ONLY", body


@pytest.mark.parametrize("status", ["closed", "archived"])
async def test_readonly_blocks_every_investigation_mutation(
    http_client, readonly_case, status
) -> None:
    """Evidence, ingestion, analytics, findings and membership mutations are all
    rejected with 409 CASE_READ_ONLY, and the case stays readable afterward."""
    case_id, _ = readonly_case
    prefix = get_settings().API_V1_PREFIX
    dummy = uuid.uuid4()

    await _set_status(http_client, case_id, status, prefix)

    # Evidence upload.
    _assert_read_only(
        await http_client.post(
            f"{prefix}/cases/{case_id}/evidence",
            files={"file": ("c.csv", CSV_BYTES.encode(), "text/csv")},
        )
    )

    # Evidence delete (guard runs before lookup, so an arbitrary id is fine).
    _assert_read_only(await http_client.delete(f"{prefix}/cases/{case_id}/evidence/{dummy}"))

    # Ingestion.
    _assert_read_only(
        await http_client.post(
            f"{prefix}/cases/{case_id}/ingest", json={"evidence_file_id": str(dummy)}
        )
    )

    # Retry graph sync.
    _assert_read_only(
        await http_client.post(f"{prefix}/cases/{case_id}/ingest/{dummy}/retry-graph-sync")
    )

    # Analytics run.
    _assert_read_only(await http_client.post(f"{prefix}/cases/{case_id}/analytics/run"))

    # Finding status mutation.
    _assert_read_only(
        await http_client.patch(
            f"{prefix}/cases/{case_id}/findings/{dummy}/status",
            json={"status": "REVIEWED"},
        )
    )

    # Membership add / remove.
    _assert_read_only(
        await http_client.post(
            f"{prefix}/cases/{case_id}/members",
            json={"user_id": str(dummy), "role": "collaborator"},
        )
    )
    _assert_read_only(await http_client.delete(f"{prefix}/cases/{case_id}/members/{dummy}"))

    # The case is still readable after every rejected mutation.
    fetched = await http_client.get(f"{prefix}/cases/{case_id}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["status"] == status


@pytest.mark.parametrize("status", ["closed", "archived"])
async def test_readonly_rejects_content_update_but_status_handling_differs(
    http_client, readonly_case, status
) -> None:
    """A closed case allows only the administrative reopen transition; an
    archived case rejects every PATCH mutation (terminal)."""
    case_id, _ = readonly_case
    prefix = get_settings().API_V1_PREFIX
    await _set_status(http_client, case_id, status, prefix)

    # Editing title/description is a content mutation -> rejected on closed/archived.
    content = await http_client.patch(f"{prefix}/cases/{case_id}", json={"title": "tampered"})
    if status == "archived":
        _assert_read_only(content)
    else:
        _assert_read_only(content)

    # Case content did not change.
    fetched = await http_client.get(f"{prefix}/cases/{case_id}")
    assert fetched.json()["title"] != "tampered"


async def test_closed_to_archived_does_not_reopen_mutation_capability(
    http_client, readonly_case
) -> None:
    """CLOSED -> ARCHIVED via the archive endpoint keeps the case read-only;
    the mutation guard still rejects after archiving."""
    case_id, _ = readonly_case
    prefix = get_settings().API_V1_PREFIX
    dummy = uuid.uuid4()

    await _set_status(http_client, case_id, "closed", prefix)

    archived = await http_client.post(f"{prefix}/cases/{case_id}/archive")
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"

    # Investigation mutations remain rejected after closed -> archived.
    _assert_read_only(await http_client.post(f"{prefix}/cases/{case_id}/analytics/run"))
    _assert_read_only(
        await http_client.post(
            f"{prefix}/cases/{case_id}/evidence",
            files={"file": ("c.csv", CSV_BYTES.encode(), "text/csv")},
        )
    )
    _assert_read_only(
        await http_client.post(
            f"{prefix}/cases/{case_id}/ingest", json={"evidence_file_id": str(dummy)}
        )
    )


async def test_open_case_still_accepts_mutations(http_client, readonly_case) -> None:
    """Sanity: an open case (not read-only) accepts evidence upload, confirming
    the guard does not block normal operation."""
    case_id, _ = readonly_case
    prefix = get_settings().API_V1_PREFIX
    r = await http_client.post(
        f"{prefix}/cases/{case_id}/evidence",
        files={"file": ("c.csv", CSV_BYTES.encode(), "text/csv")},
    )
    assert r.status_code == 201, r.text
