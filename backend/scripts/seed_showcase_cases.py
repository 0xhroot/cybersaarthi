"""Seed five rich showcase cases (synthetic, no real data).

Each case mirrors the "CyberSaarthi Phase 2 demo case" shape at a larger
scale: a sized synthetic dataset (CSV call records, JSON transactions,
statement TXT, structured contacts, surveillance TXT) that the real Phase 2
pipeline turns into a large entity/relationship graph, plus a victim record
and a persisted analytics run so the graph / analytics / findings pages are
fully populated.

The data is entirely fabricated (syntactic demo values only - no real
persons, numbers or organisations). Re-running is safe and idempotent:
existing evidence for a case is skipped (SHA-256) and analytics runs are
only created once per case.

Run from inside the backend container:

    python -m scripts.seed_showcase_cases
"""

# ruff: noqa: E501 -- demo data lines are intentionally long

from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from datetime import UTC, datetime
from typing import Any

from app.analytics.findings import AnalyticsService
from app.core.config import Settings, get_settings
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.storage import Storage
from app.models import AnalyticsRun, Case, Entity, EvidenceFile, Relationship, User, Victim
from app.repositories.analytics_repository import AnalyticsDataRepository
from app.repositories.entity_repository import EntityRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.repositories.relationship_repository import RelationshipRepository
from app.repositories.victim_repository import VictimRepository
from app.services.graph_sync import GraphSyncService
from app.services.ingestion import IngestionService
from app.services.validation import fingerprint
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed_users import DEFAULT_INVESTIGATOR_USERNAME, ensure_seed_users

logger = logging.getLogger(__name__)

PERSON_COUNT = 40

SHOWCASE_SPECS: list[dict[str, Any]] = [
    {
        "seed": 2026001,
        "case_number": "SHOW-2026-001",
        "title": "Digital lending app phishing syndicate",
        "description": (
            "Synthetic showcase: fake lending-app phishing ring using a shared "
            "network of mule accounts and re-sold SIM numbers."
        ),
        "incident_type": "phishing",
        "fraud_category": "phishing",
        "amount_lost": 4820000.0,
        "currency": "INR",
        "given": [
            "Aarav",
            "Bhavna",
            "Chandan",
            "Divya",
            "Eshan",
            "Fatima",
            "Gaurav",
            "Hina",
            "Ishaan",
            "Jaya",
            "Kunal",
            "Lavanya",
            "Manish",
            "Nisha",
            "Om",
            "Prakash",
            "Qadir",
            "Ritu",
            "Sanjay",
            "Tanvi",
            "Ujjwal",
            "Veena",
            "Wasim",
            "Yash",
            "Zoya",
        ],
        "family": [
            "Agarwal",
            "Bhatia",
            "Chatterjee",
            "D'Souza",
            "Gupta",
            "Iyer",
            "Joshi",
            "Kulkarni",
            "Mehta",
            "Nair",
            "Patil",
            "Rao",
            "Sharma",
            "Tendulkar",
            "Verma",
            "Yadav",
        ],
        "orgs": ("InstaLoan Ltd", "QuickCredit", "MoneyTap", "CashKaro", "RupeeFlow"),
        "banks": ("InstaPay Bank", "QuickCash", "TrustBank", "SecureVault", "RupeeFin"),
        "cities": ("Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Pune"),
    },
    {
        "seed": 2026002,
        "case_number": "SHOW-2026-002",
        "title": "Synthetic KYC loan fraud ring",
        "description": (
            "Synthetic showcase: ghost borrowers with forged KYC documents and "
            "a document-forging hub organisation."
        ),
        "incident_type": "loan_fraud",
        "fraud_category": "loan_fraud",
        "amount_lost": 36000000.0,
        "currency": "INR",
        "given": [
            "Aditya",
            "Bina",
            "Chirag",
            "Deepa",
            "Ekta",
            "Farid",
            "Gauri",
            "Harsha",
            "Ifrah",
            "Jeet",
            "Karan",
            "Lata",
            "Manoj",
            "Neha",
            "Omvir",
            "Priya",
            "Rahul",
            "Sneha",
            "Tanya",
            "Udita",
            "Vivek",
            "Wafa",
            "Yuvraj",
            "Zubin",
        ],
        "family": [
            "Bose",
            "Dutta",
            "Fernandes",
            "Gopal",
            "Hirani",
            "Kale",
            "Lobo",
            "Mishra",
            "Naik",
            "Oza",
            "Pillai",
            "Qasmi",
            "Reddy",
            "Sahu",
            "Tiwari",
            "Upadhyay",
        ],
        "orgs": ("FinDoc Services", "KYCPro", "PaperMill", "VisaHelp", "NDA Consultants"),
        "banks": ("CityBank", "Midland Bank", "HDFin", "VaraBank", "Lakshmi Bank"),
        "cities": ("Ahmedabad", "Jaipur", "Lucknow", "Kolkata", "Kochi", "Indore"),
    },
    {
        "seed": 2026003,
        "case_number": "SHOW-2026-003",
        "title": "Insurance claim payout fraud",
        "description": (
            "Synthetic showcase: staged vehicular claims with inflated loss "
            "estimates and a claims-adjuster network."
        ),
        "incident_type": "insurance_fraud",
        "fraud_category": "insurance_fraud",
        "amount_lost": 12450000.0,
        "currency": "INR",
        "given": [
            "Ankit",
            "Bella",
            "Cyrus",
            "Disha",
            "Emanuel",
            "Firoz",
            "Garima",
            "Heman",
            "Isha",
            "Jai",
            "Kirti",
            "Lalit",
            "Mitali",
            "Nikhil",
            "Ojasvi",
            "Prerna",
            "Ritika",
            "Sameer",
            "Tabassum",
            "Utkarsh",
            "Vidhi",
            "Waleed",
            "Yashit",
            "Zara",
        ],
        "family": [
            "Awasthi",
            "Batra",
            "Chauhan",
            "Dighe",
            "Eswaran",
            "Fulwala",
            "Ganesan",
            "Halder",
            "Iqbal",
            "Jain",
            "Khanna",
            "Ladhva",
            "Morvadiya",
            "Nanda",
            "Oswal",
            "Patnaik",
        ],
        "orgs": ("InsurePro", "ClaimZeal", "Apex Surety", "CoverWell", "CareAssured"),
        "banks": ("Axis Finance", "ICORE Bank", "Vantage Bank", "Sahara Fin", "Nexus Bank"),
        "cities": ("Surat", "Nagpur", "Vadodara", "Thane", "Nashik", "Bhopal"),
    },
    {
        "seed": 2026004,
        "case_number": "SHOW-2026-004",
        "title": "E-commerce refund scam network",
        "description": (
            "Synthetic showcase: fake seller accounts, buyer refund theft and "
            "a network of parcel-forwarding drops."
        ),
        "incident_type": "refund_scam",
        "fraud_category": "refund_scam",
        "amount_lost": 8970000.0,
        "currency": "INR",
        "given": [
            "Ashok",
            "Bindu",
            "Chetan",
            "Dikshita",
            "Esha",
            "Farah",
            "Geeta",
            "Harshit",
            "Ila",
            "Jogesh",
            "Kavya",
            "Likhit",
            "Monika",
            "Nandini",
            "Omprakash",
            "Preeti",
            "Rajat",
            "Shreya",
            "Tejas",
            "Urmila",
            "Vikram",
            "Wamiq",
            "Yashoda",
            "Zahid",
        ],
        "family": [
            "Acharya",
            "Bhagat",
            "Chawla",
            "Dalvi",
            "Ekam",
            "Gokhale",
            "Hulyalkar",
            "Ingle",
            "Jadhav",
            "Kadam",
            "Lagade",
            "Mule",
            "Nimbalkar",
            "Oza",
            "Pingle",
            "Raut",
        ],
        "orgs": ("ShopRush", "MegaMart Online", "DealKart", "QuickBazaar", "SuperSaver"),
        "banks": ("PayFino", "DigiBank", "MerchantTrust", "NaPay", "WalletOne"),
        "cities": ("Coimbatore", "Mysuru", "Vijayawada", "Guwahati", "Raipur", "Ranchi"),
    },
    {
        "seed": 2026005,
        "case_number": "SHOW-2026-005",
        "title": "Ponzi investment racket",
        "description": (
            "Synthetic showcase: pyramid scheme with promised returns, cash "
            "collection hubs and cross-state references."
        ),
        "incident_type": "ponzi",
        "fraud_category": "ponzi",
        "amount_lost": 250000000.0,
        "currency": "INR",
        "given": [
            "Alok",
            "Bhavik",
            "Chirag",
            "Devansh",
            "Elan",
            "Faiyaz",
            "Gurmeet",
            "Harsha",
            "Iqbal",
            "Jaspreet",
            "Kalyani",
            "Lokesh",
            "Manav",
            "Naveen",
            "Ojas",
            "Preetam",
            "Rakesh",
            "Sana",
            "Trilok",
            "Uma",
            "Vaibhav",
            "Waman",
            "Yashwant",
            "Zoya",
        ],
        "family": [
            "Arora",
            "Bajwa",
            "Chopra",
            "Dhillon",
            "Gill",
            "Handa",
            "Jawanda",
            "Kalra",
            "Lamba",
            "Malhotra",
            "Narang",
            "Oberoi",
            "Puri",
            "Qureshi",
            "Sandhu",
            "Thakur",
        ],
        "orgs": ("GoldenReturns", "VentureNow", "WealthSphere", "CrownCoins", "CryptoVault"),
        "banks": ("Prosperity Bank", "GlobalPeaks", "Skyline Bank", "UnionVault", "MidasOne"),
        "cities": ("Amritsar", "Ludhiana", "Chandigarh", "Jalandhar", "Dehradun", "Kanpur"),
    },
]


def _make_persons(spec: dict[str, Any], rng: random.Random) -> list[str]:
    given: list[str] = spec["given"]
    family: list[str] = spec["family"]
    persons: list[str] = []
    seen: set[str] = set()
    while len(persons) < PERSON_COUNT:
        name = f"{rng.choice(given)} {rng.choice(family)}"
        if name in seen:
            continue
        seen.add(name)
        persons.append(name)
    return persons


def _build_payloads(spec: dict[str, Any], rng: random.Random) -> list[tuple[str, str, object]]:
    orgs = spec["orgs"]
    banks = spec["banks"]
    cities = spec["cities"]

    persons = _make_persons(spec, rng)
    phones = [f"+91-8{rng.randint(10000000, 99999999):07d}" for _ in persons]
    accounts = [str(rng.randint(100000000000, 999999999999)) for _ in persons]
    vehicles = [
        f"{cities[i % len(cities)][:2].upper()}01AB{rng.randint(1000, 9999)}"
        for i in range(len(persons))
    ]
    orgs_for = [rng.choice(orgs) for _ in persons]
    cities_for = [rng.choice(cities) for _ in persons]

    shared_phone = phones[0]
    for idx in (1, 5, 12):
        phones[idx] = shared_phone

    csv_rows = [
        f"{persons[i]},{phones[i]},{orgs_for[i]},{vehicles[i]},{cities_for[i]}"
        for i in range(len(persons))
    ]

    json_rows = [
        {
            "name": persons[i],
            "account_no": accounts[i],
            "bank_name": banks[i % len(banks)],
            "city": cities_for[i],
        }
        for i in range(len(persons))
    ]

    txt_lines = []
    for i in range(0, len(persons) - 1, 2):
        partner = persons[i + 1]
        txt_lines.append(
            f"{persons[i]} contacted {partner} regarding the {orgs_for[i]} consignment "
            f"to {cities_for[i]} using account {accounts[i]}."
        )
        txt_lines.append(
            f"{partner} visited {orgs_for[i + 1]} in {cities_for[i + 1]} on a weekday "
            f"and confirmed payment via {banks[i % len(banks)]}."
        )
        txt_lines.append(
            f"The {orgs_for[i]} team registered vehicle {vehicles[i]} in "
            f"{cities_for[i]} for customer {persons[i]}."
        )

    contacts = [
        {
            "name": persons[i],
            "phone": phones[i],
            "city": cities_for[i],
            "organization": orgs_for[i],
        }
        for i in range(len(persons))
    ]
    known = set(persons)
    for i in range(len(persons), len(persons) + 12):
        name = f"{rng.choice(spec['given'])} {rng.choice(spec['family'])}"
        while name in known:
            name = f"{rng.choice(spec['given'])} {rng.choice(spec['family'])}"
        known.add(name)
        contacts.append(
            {
                "name": name,
                "phone": phones[i % len(persons)],
                "city": rng.choice(cities),
            }
        )

    hub = persons[0]
    surveillance = []
    for i in range(1, 21):
        a = persons[i % len(persons)]
        b = persons[(i * 3) % len(persons)]
        surveillance.append(
            f"Surveillance log: {hub} met {a} near {rng.choice(cities)} railway station "
            f"and later {b} joined them at a hotel lobby."
        )
    for i in range(21, 26):
        a = persons[i % len(persons)]
        surveillance.append(
            f"Surveillance log: {a} dialled {shared_phone} about the "
            f"{orgs_for[i % len(persons)]} consignment to {cities_for[i % len(persons)]}."
        )

    payloads: list[tuple[str, str, object]] = [
        ("csv", "showcase_call_records.csv", "\n".join(csv_rows) + "\n"),
        ("json", "showcase_transactions.json", json_rows),
        ("txt", "showcase_statements.txt", "\n\n".join(txt_lines) + "\n"),
        ("json", "showcase_contacts.json", contacts),
        ("txt", "showcase_surveillance.txt", "\n".join(surveillance) + "\n"),
    ]
    return payloads


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
            analytics = AnalyticsService(
                data_repo=AnalyticsDataRepository(session),
                graph_store=self._graph_store,
                settings=self._settings,
            )
            victims = VictimRepository(session)

            for spec in SHOWCASE_SPECS:
                case = await self._get_or_create_case(session, spec, owner_id=investigation_lead)
                rng = random.Random(int(spec["seed"]))  # noqa: S311 - deterministic demo seeding
                payloads = _build_payloads(spec, rng)
                victim_name = _make_persons(spec, rng)[0]
                for fmt, filename, payload in payloads:
                    await self._ensure_ingested(
                        session, ingestion, case, fmt, filename, _bytes(payload)
                    )
                await self._ensure_victim(
                    session, victims, case, spec, victim_name, investigation_lead
                )
                await self._ensure_analytics_run(session, analytics, case, investigation_lead)
                await self._log_summary(session, case)

    async def _investigation_lead(self, session: AsyncSession) -> uuid.UUID | None:
        result = await session.execute(
            select(User).where(User.username == DEFAULT_INVESTIGATOR_USERNAME)
        )
        user = result.scalar_one_or_none()
        return user.id if user is not None else None

    async def _get_or_create_case(
        self, session: AsyncSession, spec: dict[str, Any], owner_id: uuid.UUID | None = None
    ) -> Case:
        case_number = str(spec["case_number"])
        result = await session.execute(select(Case).where(Case.case_number == case_number))
        case = result.scalar_one_or_none()
        if case is not None:
            if owner_id is not None and case.owner_id is None:
                case.owner_id = owner_id
                await session.commit()
            return case
        case = Case(
            case_number=case_number,
            title=str(spec["title"]),
            description=str(spec["description"]),
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
                fmt, f"{fmt.upper()} synthetic showcase evidence"
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

        job = await ingestion.ingest(
            case_id=uuid.UUID(str(evidence.case_id)),
            evidence_file_id=uuid.UUID(str(evidence.id)),
            metadata={"seed": True, "synthetic": True},
        )
        logger.info(
            "ingested %s: job=%s status=%s graph=%s",
            evidence.original_filename,
            job.id,
            job.status,
            job.graph_sync_status,
        )

    async def _ensure_victim(
        self,
        session: AsyncSession,
        repository: VictimRepository,
        case: Case,
        spec: dict[str, Any],
        name: str,
        actor: uuid.UUID | None,
    ) -> None:
        case_id = uuid.UUID(str(case.id))
        present = await session.scalar(select(func.count()).where(Victim.case_id == case_id))
        if present:
            return
        await repository.create(
            case_id=case_id,
            created_by=actor,
            name=name.lower().strip(),
            classification="individual",
            status="reported",
            incident_type=str(spec["incident_type"]),
            fraud_category=str(spec["fraud_category"]),
            reported_amount=float(spec["amount_lost"]),
            currency=str(spec["currency"]),
            description=str(spec["description"]),
            incident_date=datetime.now(UTC),
        )
        await session.commit()

    async def _ensure_analytics_run(
        self,
        session: AsyncSession,
        analytics: AnalyticsService,
        case: Case,
        actor: uuid.UUID | None,
    ) -> None:
        case_id = uuid.UUID(str(case.id))
        existing = await session.scalar(select(func.count()).where(AnalyticsRun.case_id == case_id))
        if existing:
            logger.info("skipping analytics run for %s (already recorded)", case.case_number)
            return
        run = await analytics.run_analytics(case_id, actor_id=actor)
        await session.commit()
        logger.info(
            "analytics run %s recorded for %s (status=%s)",
            run.id,
            case.case_number,
            run.status,
        )

    async def _log_summary(self, session: AsyncSession, case: Case) -> None:
        entity_count = await session.scalar(
            select(func.count()).where(Entity.case_id == str(case.id))
        )
        relationship_count = await session.scalar(
            select(func.count()).where(Relationship.case_id == str(case.id))
        )
        print(
            f"Seeded case {case.case_number} ({case.title}) with "
            f"{int(entity_count or 0)} entities / {int(relationship_count or 0)} relationships"
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(Seeder(get_settings()).run())


if __name__ == "__main__":
    main()
