"""Deterministic demo seed for Phase 2.

Creates a single demo case and ingests three synthetic evidence files
(CSV, JSON, TXT). Run from inside the backend container:

    python -m scripts.seed_demo

The data is entirely fabricated (syntactic demo values only - no real
persons, numbers or organisations). Re-running is safe and idempotent:
existing evidence for the case is skipped and only missing graph
projections are re-synced.
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
from app.models import Case, Entity, EvidenceFile
from app.repositories.entity_repository import EntityRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.repositories.relationship_repository import RelationshipRepository
from app.services.graph_sync import GraphSyncService
from app.services.ingestion import IngestionService
from app.services.validation import fingerprint
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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

EVIDENCE_PLAN: tuple[tuple[str, str, str | list[dict[str, object]]], ...] = (
    ("csv", "demo_call_records.csv", CSV_DATA),
    ("json", "demo_transactions.json", JSON_DATA),
    ("txt", "demo_statements.txt", TXT_DATA),
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
            ingestion = IngestionService(
                session=session,
                evidence_repository=EvidenceRepository(session),
                entity_repository=EntityRepository(session),
                relationship_repository=RelationshipRepository(session),
                storage=self._storage,
                graph_sync=GraphSyncService(self._graph_store, self._settings),
                settings=self._settings,
            )
            case = await self._get_or_create_case(session)
            for fmt, filename, payload in EVIDENCE_PLAN:
                await self._ensure_ingested(
                    session, ingestion, case, fmt, filename, _bytes(payload)
                )
            await self._log_summary(session, case)

    async def _get_or_create_case(self, session: AsyncSession) -> Case:
        result = await session.execute(select(Case).where(Case.case_number == DEMO_CASE_NUMBER))
        case = result.scalar_one_or_none()
        if case is not None:
            return case
        case = Case(
            case_number=DEMO_CASE_NUMBER,
            title="CyberSaarthi Phase 2 demo case",
            description="Synthetic evidence ingested by scripts.seed_demo (no real data).",
            status="in_progress",
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
        print(f"Seeded case {DEMO_CASE_NUMBER} ({case.id}) with {int(entity_count or 0)} entities")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(Seeder(get_settings()).run())


if __name__ == "__main__":
    main()
