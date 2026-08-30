"""Deterministic demo seed.

Creates a single demo case and ingests synthetic evidence (CSV, JSON, TXT)
designed to exercise both the Phase 2 knowledge-graph pipeline and the Phase 3
investigation-intelligence engine:

* a central/hub entity with high influence,
* multiple communities of persons/organisations,
* a bridge entity connecting communities (cut vertex),
* shared identifiers (one phone/vehicle used by several people),
* a relationship-concentration hub,
* closed loops (person triangles),
* repeated evidence backing one relationship,
* missing links the analytics turn into hypotheses,
* multi-hop traversable paths (Neo4j).

Run from inside the backend container:

    python -m scripts.seed_demo

The data is entirely fabricated (syntactic demo values only - no real persons,
numbers or organisations). Re-running is safe and idempotent: existing evidence
for the case is skipped (SHA-256) and only missing graph projections are
re-synced.
"""

# ruff: noqa: E501 -- demo data lines are intentionally long

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from app.core.config import Settings, get_settings
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.storage import Storage
from app.models import Case, Entity, EvidenceFile, Relationship, User
from app.repositories.entity_repository import EntityRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.repositories.relationship_repository import RelationshipRepository
from app.services.graph_sync import GraphSyncService
from app.services.ingestion import IngestionService
from app.services.validation import fingerprint
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed_users import DEFAULT_INVESTIGATOR_USERNAME, ensure_seed_users

logger = logging.getLogger(__name__)

DEMO_CASE_NUMBER = "DEMO-2026-001"

CSV_DATA = (
    "name,phone,organization,vehicle_no,city\n"
    "Rajesh Kumar,+91-98765-43210,TechSecure Pvt Ltd,MH12AB1234,Mumbai\n"
    "Rajesh Kumar,09876543210,TechSecure,MH12 AB 1234,Pune\n"
    "Sunita Sharma,+91 91234 56789,SecureMart Ltd,KA01CD5678,Bengaluru\n"
    "Arjun Mehta,+91 90000 11111,Techsecure Pvt Ltd,DL01EF9012,Delhi\n"
    "Arjun Mehra,9000011112,TechSecure,UP32GH3456,Noida\n"
    "Kavita Rao,+91 98111 22233,Kavita Enterprises,MH14JK7890,Mumbai\n"
)

JSON_DATA: list[dict[str, object]] = [
    {
        "name": "Rajesh Kumar",
        "account_no": "1100220011",
        "bank_name": "TechSecure",
        "city": "Mumbai",
    },
    {
        "name": "Sunita Sharma",
        "account_no": "3300445566",
        "bank_name": "SecureMart",
        "city": "Bengaluru",
    },
    {
        "name": "Arjun Mehta",
        "account_no": "220044001122",
        "bank_name": "TechSecure",
        "city": "Delhi",
    },
    {
        "name": "Kavita Rao",
        "account_no": "9911002233",
        "bank_name": "Kavita Enterprises",
        "city": "Mumbai",
    },
]

TXT_DATA = (
    "Rajesh Kumar called 9876543210 on Tuesday evening regarding the TechSecure delivery to Mumbai.\n"
    "\n"
    "Sunita Sharma visited SecureMart in Bengaluru and used account 220044001122 for payment.\n"
    "\n"
    "The TechSecure team registered vehicle MH12AB1234 in Pune for customer Arjun Mehta.\n"
    "\n"
    "Kavita Rao reported event CyberCon 2025 held at Kavita Enterprises in Mumbai.\n"
)

# Phase 3 enrichment: structured contact records that build a hub, a shared
# identifier (one phone used by three people across cities) and repeated
# evidence for Kavita's existing phone relationship.
CONTACTS_JSON: list[dict[str, object]] = [
    {
        "name": "Vikram Jamwal",
        "phone": "+91 80000 10001",
        "city": "Mumbai",
        "organization": "TechSecure Pvt Ltd",
    },
    {
        "name": "Mukesh Rane",
        "phone": "8000010002",
        "city": "Mumbai",
        "organization": "TechSecure Pvt Ltd",
    },
    {"name": "Sonal Kulkarni", "phone": "+91 80000 10003", "city": "Mumbai"},
    {
        "name": "Priya Nair",
        "phone": "+91 80000 10004",
        "city": "Bengaluru",
        "organization": "SecureMart Ltd",
    },
    {"name": "Devraj Pillai", "phone": "8000010005", "city": "Bengaluru"},
    {
        "name": "Vishal Gaur",
        "phone": "+91 80000 10006",
        "city": "Delhi",
        "organization": "TechSecure Pvt Ltd",
    },
    {"name": "Rohit Desai", "phone": "+91 80000 10077", "city": "Mumbai"},
    {"name": "Sameer Bhat", "phone": "8000010077", "city": "Bengaluru"},
    {"name": "Farhan Shaikh", "phone": "+91-80000-10077", "city": "Noida"},
    {"name": "Kavita Rao", "phone": "9811122233", "city": "Mumbai"},
    {"name": "Kavita Rao", "phone": "+91 98111 22233", "city": "Mumbai"},
]

# Phase 3 enrichment: free-text surveillance log that creates the person hub
# cluster, closed loops (triangles), additional bridge/identifier connections
# and multi-hop chains. Names are fabricated and NER-only (person -> person
# relationships are co-occurrence inside each sentence window).
SURVEILLANCE_TXT = (
    "Surveillance log: Vikram Jamwal met Mukesh Rane at Marine Drive in Mumbai.\n"
    "\n"
    "Surveillance log: Mukesh Rane met Vikram Jamwal again near Gateway of India in Mumbai.\n"
    "\n"
    "Surveillance log: Rajesh Kumar met Mukesh Rane on Tuesday evening in Mumbai.\n"
    "\n"
    "Surveillance log: Rajesh Kumar, Vikram Jamwal and Sonal Kulkarni were seen together outside TechSecure in Mumbai.\n"
    "\n"
    "Surveillance log: Priya Nair visited SecureMart in Bengaluru and dialled number 8000010077.\n"
    "\n"
    "Surveillance log: Mr Sameer Bhat called 8000010077 from Bengaluru about the delivery to Noida.\n"
    "\n"
    "Surveillance log: Farhan Shaikh registered vehicle DL01EF9012 in Noida for the Bengaluru delivery group.\n"
)

EVIDENCE_PLAN: tuple[tuple[str, str, str | list[dict[str, object]]], ...] = (
    ("csv", "demo_call_records.csv", CSV_DATA),
    ("json", "demo_transactions.json", JSON_DATA),
    ("txt", "demo_statements.txt", TXT_DATA),
    ("json", "demo_contacts.json", CONTACTS_JSON),
    ("txt", "demo_surveillance.txt", SURVEILLANCE_TXT),
)


def _bytes(payload: str | list[dict[str, object]]) -> bytes:
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


class Seeder:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._database = Database(settings)
        self._graph_store = GraphStore(settings)
        self._storage = Storage(settings)

    async def run(self) -> None:
        factory = self._database.session_factory()
        async with factory() as session:
            await ensure_seed_users(session)
            investigation_lead = await self._investigation_lead(session)
            ingestion = IngestionService(
                session=session,
                evidence_repository=EvidenceRepository(session),
                entity_repository=EntityRepository(session),
                relationship_repository=RelationshipRepository(session),
                storage=self._storage,
                graph_sync=GraphSyncService(self._graph_store, self._settings),
                settings=self._settings,
            )
            case = await self._get_or_create_case(session, owner_id=investigation_lead)
            for fmt, filename, payload in EVIDENCE_PLAN:
                await self._ensure_ingested(
                    session, ingestion, case, fmt, filename, _bytes(payload)
                )
            await self._log_summary(session, case)

    async def _investigation_lead(self, session: AsyncSession) -> uuid.UUID | None:
        result = await session.execute(
            select(User).where(User.username == DEFAULT_INVESTIGATOR_USERNAME)
        )
        user = result.scalar_one_or_none()
        return user.id if user is not None else None

    async def _get_or_create_case(
        self, session: AsyncSession, owner_id: uuid.UUID | None = None
    ) -> Case:
        result = await session.execute(select(Case).where(Case.case_number == DEMO_CASE_NUMBER))
        case = result.scalar_one_or_none()
        if case is not None:
            if owner_id is not None and case.owner_id is None:
                case.owner_id = owner_id
                await session.commit()
            return case
        case = Case(
            case_number=DEMO_CASE_NUMBER,
            title="CyberSaarthi Phase 2 demo case",
            description="Synthetic evidence ingested by scripts.seed_demo (no real data).",
            status="in_progress",
            owner_id=owner_id,
        )
        session.add(case)
        await session.commit()
        await session.refresh(case)
        return case

    async def _ensure_ingested(
        self,
        session: AsyncSession,
        ingestion: IngestionService,
        case: Case,
        fmt: str,
        filename: str,
        payload: bytes,
    ) -> None:
        sha256 = fingerprint(payload)
        result = await session.execute(
            select(EvidenceFile).where(
                EvidenceFile.case_id == str(case.id),
                EvidenceFile.sha256 == sha256,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            source = await ingestion.ensure_data_source(
                fmt, f"{fmt.upper()} synthetic demo evidence"
            )
            object_key = f"cases/{case.id}/evidence/{uuid.uuid4()}/{filename}"
            await asyncio.to_thread(
                self._storage.upload, object_key, payload, "application/octet-stream"
            )
            evidence = EvidenceFile(
                case_id=str(case.id),
                data_source_id=str(source.id),
                original_filename=filename,
                stored_key=object_key,
                content_type="application/octet-stream",
                file_size=len(payload),
                sha256=sha256,
                metadata_json={"seed": True, "synthetic": True},
            )
            session.add(evidence)
            await session.commit()
            await session.refresh(evidence)
        else:
            evidence = existing
            logger.info("skipping %s (already ingested)", filename)

        case_id = uuid.UUID(str(evidence.case_id))
        job = await ingestion.ingest(
            case_id=case_id,
            evidence_file_id=uuid.UUID(str(evidence.id)),
            metadata={"seed": True, "synthetic": True},
        )
        logger.info(
            "ingested %s: job=%s status=%s graph=%s summary=%s",
            evidence.original_filename,
            job.id,
            job.status,
            job.graph_sync_status,
            job.summary,
        )

    async def _log_summary(self, session: AsyncSession, case: Case) -> None:
        entity_count = await session.scalar(
            select(func.count()).where(Entity.case_id == str(case.id))
        )
        relationship_count = await session.scalar(
            select(func.count()).where(Relationship.case_id == str(case.id))
        )
        print(
            f"Seeded case {DEMO_CASE_NUMBER} ({case.id}) with "
            f"{int(entity_count or 0)} entities / {int(relationship_count or 0)} relationships"
        )
        print(
            "Run the analytics pipeline: POST /api/v1/cases/<id>/analytics/run"
            " or GET /api/v1/cases/<id>/analytics/summary"
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(Seeder(get_settings()).run())


if __name__ == "__main__":
    main()
