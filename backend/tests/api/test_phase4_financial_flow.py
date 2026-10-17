"""Phase 4 feature A: deterministic financial flow analysis (backend).

Two layers, both asserted against expected values the test derives itself:

* **pure unit tests** for extraction, aggregates, the structure network and
  pattern rules — exact ``Decimal`` arithmetic, missing-field accounting, the
  refusal to compute direction-dependent totals, and the invariant that a rule
  can never fire without evidence;
* **API and runner tests** — submit → 202 with one active job per feature
  (typed 409), a reviewable ``financial_flow`` artifact whose numbers the test
  computes from the seeded records, full provenance, and authorization
  enforcement at both submit time and execution time.

Seed data deliberately mirrors what the A1 verification measured in the live
schema (``docs/ai/PHASE_4_DESIGN.md`` §2.2): amounts are JSON *strings*, a
payee exists but no payer, no record carries a transaction timestamp, and an
account-holder record has no movement at all. If an assumption such as a
fabricated direction, currency or time is reintroduced, these tests fail.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal

import httpx
from app.core.codes import (
    CODE_AI_EXPLANATION_INVALID,
    CODE_CASE_ACCESS_DENIED,
    CODE_FLOW_ACTIVE,
    CODE_INSUFFICIENT_PERMISSION,
)
from app.core.config import get_settings
from app.db.postgres import Database
from app.main import app
from app.models import (
    AnalysisJob,
    AuditLog,
    CaseMember,
    DerivedArtifact,
    EvidenceFile,
    SourceRecord,
    Victim,
)
from app.services import financial_flow as flow_svc
from app.services.financial_flow import (
    _trace_paths,
    aggregate_facts,
    build_structure_network,
    classify_status,
    evaluate_patterns,
    extract_fact,
    extract_facts,
    extract_victim_financials,
    parse_amount,
)
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from tests.api.conftest import ApiUser

PREFIX = get_settings().API_V1_PREFIX

# -- seeded records -------------------------------------------------------------
# Six records: two distinct transfers, the first transfer re-recorded under the
# same transaction reference, one amount with no reference at all, one
# account-holder record with no movement, and one record with no financial
# field whatsoever.

TXN_ONE = "TXN-SIH-001"
TXN_TWO = "TXN-SIH-002"
FLOW_RECORDS: list[dict[str, object]] = [
    {
        "city": "Mumbai",
        "name": "Ananya Sirohi",
        "phone": "+91 98200 00001",
        "amount": "4500.00",
        "device": "IPHONE-XYZ-001",
        "account": "ACC-SIH-001",
        "merchant": "PhonePe Merchant",
        "transaction_id": TXN_ONE,
    },
    {
        "city": "Pune",
        "name": "Rohan Mehta",
        "phone": "98200000002",
        "amount": "12000.00",
        "device": "ANDROID-ABC-002",
        "account": "ACC-SIH-002",
        "merchant": "Paytm Merchant",
        "transaction_id": TXN_TWO,
    },
    # The same transfer as record 1, recorded a second way (identical reference).
    {
        "city": "Mumbai",
        "amount": "4500.00",
        "account_number": "ACC-SIH-001",
        "transaction_id": TXN_ONE,
        "beneficiary_name": "Ananya Sirohi",
    },
    # An amount with a payee but no transaction reference: not groupable with 1.
    {
        "city": "Mumbai",
        "amount": "4500.00",
        "vehicle": "MH-12-AB-1234",
        "account_number": "ACC-SIH-001",
        "beneficiary_name": "Ananya Sirohi",
        "beneficiary_phone": "+91 98200 00001",
    },
    # Account holder only: no amount, no movement.
    {
        "city": "Bengaluru",
        "name": "Sunita Sharma",
        "bank_name": "SecureMart",
        "account_no": "3300445566",
    },
    # No financial field at all (only "text" and "city" style free form).
    {"text": "Rajesh Kumar called 9876543210 on Tuesday evening regarding a refund"},
]

# Expectations the test derives from FLOW_RECORDS by hand, independently of the
# implementation under test.
AMOUNTS = [Decimal("4500.00"), Decimal("12000.00"), Decimal("4500.00"), Decimal("4500.00")]
EXPECTED_TOTAL_RECORDS = "25500.00"  # 4500*3 + 12000
EXPECTED_TOTAL_DISTINCT = "21000.00"  # TXN_ONE counted once, unreferenced 4500 once, TXN_TWO once


def _rec(raw: dict[str, object], record_no: int = 1) -> SourceRecord:
    """One in-memory source record (id assigned so provenance is never ``None``)."""
    record = SourceRecord(
        evidence_file_id=str(uuid.uuid4()),
        record_no=record_no,
        raw_data=raw,
        status="parsed",
    )
    record.id = uuid.uuid4()
    return record


def _client(token: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


async def _seed_evidence_records(
    database: Database,
    case_id: uuid.UUID,
    records: list[dict[str, object]],
    *,
    label: str,
) -> uuid.UUID:
    """Insert one evidence file plus its parsed source records (no storage)."""
    payload = json.dumps(records).encode()
    factory = database.session_factory()
    async with factory() as session:
        evidence = EvidenceFile(
            case_id=str(case_id),
            original_filename=f"{label}.json",
            stored_key=f"seed/{label}.json",
            content_type="application/json",
            file_size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            format="json",
            encoding="utf-8",
            record_count=len(records),
            status="stored",
        )
        session.add(evidence)
        await session.flush()
        evidence_id = uuid.UUID(str(evidence.id))
        for index, raw in enumerate(records, start=1):
            session.add(
                SourceRecord(
                    evidence_file_id=str(evidence_id),
                    record_no=index,
                    raw_data=dict(raw),
                    status="parsed",
                )
            )
        await session.commit()
        return evidence_id


async def _artifacts(
    database: Database, case_id: uuid.UUID, *, kind: str
) -> list[DerivedArtifact]:
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(DerivedArtifact).where(
                DerivedArtifact.case_id == str(case_id),
                DerivedArtifact.kind == kind,
            )
        )
        return list(rows.scalars())


async def _job_row(database: Database, job_id: uuid.UUID) -> AnalysisJob:
    factory = database.session_factory()
    async with factory() as session:
        job = await session.get(AnalysisJob, job_id)
        assert job is not None, f"job {job_id} not found"
        return job


async def _audit_row(database: Database, *, action: str, resource_id: uuid.UUID | str):
    factory = database.session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(AuditLog).where(
                AuditLog.action == action,
                AuditLog.resource_id == str(resource_id),
            )
        )
        return rows.scalars().first()


async def _submit(
    client: httpx.AsyncClient, case_id: uuid.UUID, path: str = "financial-flow"
) -> httpx.Response:
    return await client.post(
        f"{PREFIX}/cases/{case_id}/evidence-intelligence/{path}",
        json={},
    )


async def _seed_pending_job(
    database: Database, case_id: uuid.UUID, *, actor_id: uuid.UUID
) -> uuid.UUID:
    factory = database.session_factory()
    async with factory() as session:
        job = AnalysisJob(
            case_id=str(case_id),
            feature="financial_flow",
            status="pending",
            idempotency_key=f"seed-financial_flow-{uuid.uuid4().hex[:8]}",
            attempts=1,
            timeout_seconds=300,
            actor_id=str(actor_id),
        )
        session.add(job)
        await session.commit()
        return uuid.UUID(str(job.id))


async def _run_job(database: Database, job_id: uuid.UUID, *, settings) -> AnalysisJob:
    factory = database.session_factory()
    async with factory() as session:
        await flow_svc.execute_financial_flow(session, job_id=job_id, settings=settings)
    async with factory() as session:
        job = await session.get(AnalysisJob, job_id)
        assert job is not None
        await session.refresh(job)
        return job


# -- pure extraction -----------------------------------------------------------


def test_parse_amount_is_exact_rejects_junk_and_flags_float_sources() -> None:
    parsed = parse_amount("4500.00")
    assert parsed["value"] == Decimal("4500.00")
    assert parsed["original"] == "4500.00"
    assert parsed.get("warning") is None

    # Group separators must not change the value.
    grouped = parse_amount("1,20,000.50")
    assert grouped["value"] == Decimal("120000.50")

    # Non-numeric content is rejected, never coerced.
    junk = parse_amount("b")
    assert junk.get("value") is None
    assert junk.get("warning") == "amount_invalid"
    assert junk.get("original") == "b"

    # A binary float source keeps its exact string value but is flagged.
    floated = parse_amount(12000.0)
    assert floated["value"] == Decimal("12000.0")
    assert floated.get("precision") == "float_source"

    # An explicit currency literal inside the string is honoured, not guessed.
    hinted = parse_amount("INR 4500.00")
    assert hinted["value"] == Decimal("4500.00")
    assert hinted.get("currency_hint") == "INR"


def test_status_classification_follows_the_documented_vocabulary() -> None:
    assert classify_status("completed") == "completed"
    assert classify_status("Settled") == "completed"
    assert classify_status("payment pending") == "pending"
    assert classify_status("REFUNDED") == "reversed"
    assert classify_status("declined") == "rejected"
    assert classify_status("who knows") == "unknown"
    assert classify_status(None) == "unknown"
    assert classify_status("") == "unknown"


def test_extraction_classes_records_and_marks_every_absent_field() -> None:
    fact, warning = extract_fact(
        _rec(
            {
                "amount": "4500.00",
                "transaction_id": TXN_ONE,
                "account": "ACC-SIH-001",
                "beneficiary_name": "Ananya Sirohi",
            }
        ),
        str(uuid.uuid4()),
    )
    assert fact is not None and warning is None
    assert fact.fact_class == "transaction"
    assert fact.amount == Decimal("4500.00")
    assert fact.txn_ref_normalized == TXN_ONE
    # Nothing exists to date it or name its currency: said so, not invented.
    assert "timestamp" in fact.missing
    assert "currency" in fact.missing
    assert "missing_timestamp" in fact.limitations
    assert "currency_unknown" in fact.limitations
    # No payer key exists anywhere in the ingest: direction is declared absent.
    assert "source_direction" in fact.missing
    assert "one_sided" in fact.limitations
    assert fact.occurred_at is None and fact.currency is None
    assert fact.status == "unknown"

    # Account context without an amount is context, not a movement.
    holder, _ = extract_fact(
        _rec({"name": "Sunita Sharma", "bank_name": "SecureMart", "account_no": "3300445566"}),
        str(uuid.uuid4()),
    )
    assert holder is not None
    assert holder.fact_class == "account_reference"
    assert holder.amount is None
    assert "amount" in holder.missing

    # A record with no financial field at all produces no fact.
    none_fact, _ = extract_fact(_rec({"text": "just a note"}), str(uuid.uuid4()))
    assert none_fact is None


def test_aggregates_are_exact_and_refuse_direction_dependent_totals() -> None:
    records = [
        _rec({"amount": "100.50", "account": "A-1", "transaction_id": "T1"}, 1),
        _rec({"amount": "100.50", "account": "A-1", "transaction_id": "T1"}, 2),
        _rec({"amount": "200.25", "account": "A-2"}, 3),
        _rec({"account": "A-3"}, 4),
    ]
    facts, warnings = extract_facts(records)
    # Four facts: three carry movement, the account-only record is context.
    assert len(facts) == 4
    assert sum(1 for f in facts if f.fact_class == "transaction") == 3
    assert warnings["amounts_parsed"] == 3

    agg = aggregate_facts(facts)
    bucket = agg["currency_buckets"][0]
    assert bucket["currency"] is None
    assert bucket["currency_unknown"] is True
    assert bucket["count"] == 3
    assert bucket["min"] == "100.50"
    assert bucket["max"] == "200.25"
    assert bucket["distinct_amounts"] == 2
    # 100.50 + 100.50 + 200.25 = 401.25 counted per record …
    assert bucket["total_records"] == "401.25"
    # … versus 100.50 (T1 once) + 200.25 = 300.75 counted per distinct transfer.
    assert bucket["total_distinct"] == "300.75"
    assert bucket["distinct_groups"] == 2
    assert bucket["conflicting_groups"] == []
    assert bucket["supporting_source_record_ids"] and bucket["supporting_ids_capped"] is False

    # Direction-dependent metrics are refused, never reported as zero.
    assert agg["not_computable"]["net"] == "not_computable_no_direction"
    assert agg["not_computable"]["inflow"] == "not_computable_no_direction"
    assert agg["not_computable"]["outflow"] == "not_computable_no_direction"
    assert "direction" in agg["not_computable"]["reason"]

    counts = agg["counts"]
    assert counts["facts_total"] == 4
    assert counts["fact_class_transaction"] == 3
    assert counts["with_currency"] == 0
    assert counts["without_currency"] == 3
    assert counts["with_timestamp"] == 0
    assert counts["without_timestamp"] == 3


def test_conflicting_group_amounts_are_reported_instead_of_picked() -> None:
    records = [
        _rec({"amount": "10.00", "transaction_id": "TX"}, 1),
        _rec({"amount": "20.00", "transaction_id": "TX"}, 2),
    ]
    facts, _ = extract_facts(records)
    bucket = aggregate_facts(facts)["currency_buckets"][0]
    # The two records disagree about what "TX" was worth: no number is chosen
    # for them, and no fabricated total is offered either.
    assert len(bucket["conflicting_groups"]) == 1
    assert bucket["conflicting_groups"][0]["amounts"] == ["10.00", "20.00"]
    assert bucket["total_distinct"] is None
    assert bucket["total_records"] == "30.00"


def test_structure_network_types_edges_and_never_asserts_a_transfer() -> None:
    records = [
        _rec({"amount": "4500.00", "account": "ACC-1", "merchant": "PhonePe"}, 1),
        _rec({"account_no": "ACC-2", "bank_name": "SecureMart"}, 2),
    ]
    facts, _ = extract_facts(records)
    network = build_structure_network(
        facts,
        [
            {
                "source_type": "person",
                "source_value": "Ananya Sirohi",
                "target_type": "account",
                "target_value": "ACC-1",
                "relationship_type": "owns",
                "confidence": 0.9,
                "source_record_id": None,
            }
        ],
        max_edges=50,
    )
    assert network["confirmed_transfer_edges"] == 0
    assert network["edges_bounded"] is False
    kinds = {edge["edge_kind"] for edge in network["edges"]}
    assert kinds <= {"association", "relationship"}
    assert "transfer" not in kinds
    for edge in network["edges"]:
        if edge["edge_kind"] == "association":
            assert edge["confidence"] == "suspected"
        else:
            assert edge["relationship_type"] == "owns"
    # Association edges carry their exact supporting source-record ids.
    acc_merchant = next(
        e
        for e in network["edges"]
        if e["derivation"] == "account_star" and e["edge_kind"] == "association"
    )
    assert len(acc_merchant["supporting_source_record_ids"]) == 1


def test_structure_network_is_bounded() -> None:
    records = [
        _rec({"account_no": f"ACC-{i}", "bank_name": f"Bank {i}"}, i) for i in range(1, 21)
    ]
    facts, _ = extract_facts(records)
    network = build_structure_network(facts, [], max_edges=5)
    assert network["edges_total"] <= 5
    assert network["edges_bounded"] is True
    assert network["max_edges"] == 5


# -- pure pattern rules --------------------------------------------------------


def test_pattern_rules_fire_only_on_evidence_and_declare_missing_inputs() -> None:
    records = [
        _rec({"amount": "4500.00", "account": "A-1"}, 1),
        _rec({"amount": "4500.00", "account": "A-2"}, 2),
        _rec({"amount": "12000.00", "account": "A-3"}, 3),
    ]
    facts, _ = extract_facts(records)
    patterns = evaluate_patterns(facts, [], amount_threshold=Decimal("5000"))

    firing = {p["rule"]: p for p in patterns["firing"]}
    # Same exact amount on two records.
    assert firing["duplicate_amount"]["evidence"]["amount"] == "4500.00"
    assert firing["duplicate_amount"]["evidence"]["record_count"] == 2
    assert firing["duplicate_amount"]["review_status"] == "pending_review"
    assert firing["duplicate_amount"]["pattern_not_intent"] is True
    # Only 12000.00 clears the configured threshold; 4500.00 does not.
    assert firing["amount_threshold"]["evidence"]["threshold"] == "5000"
    assert firing["amount_threshold"]["evidence"]["matched_count"] == 1
    assert firing["amount_threshold"]["evidence"]["amounts"] == ["12000.00"]
    # Coverage observations over the facts themselves.
    assert firing["missing_currency"]["evidence"]["matched_count"] == 3
    assert firing["missing_timestamp"]["evidence"]["matched_count"] == 3

    # Every rule that needs an input the ingest does not carry is declared with
    # the exact missing input instead of quietly vanishing.
    assert patterns["not_fired"] == ["victim_loss_unmatched"]
    not_evaluable = {p["rule"]: p for p in patterns["not_evaluable"]}
    assert set(not_evaluable) == {
        "rapid_succession",
        "repeated_pair",
        "circular_path",
        "amount_splitting",
        "concentration",
    }
    assert not_evaluable["rapid_succession"]["reason"] == "missing_timestamp"
    assert not_evaluable["repeated_pair"]["reason"] == "missing_direction"
    assert not_evaluable["circular_path"]["reason"] == "no_transfer_edges"
    assert not_evaluable["amount_splitting"]["reason"] == "missing_direction"
    assert not_evaluable["concentration"]["reason"] == "missing_direction"
    for entry in not_evaluable.values():
        assert entry["status"] == "not_evaluable"
        assert entry["explanation"]


def test_a_rule_never_fires_when_there_is_no_evidence() -> None:
    records = [
        _rec({"amount": "10.00", "account": "A-1"}, 1),
        _rec({"amount": "20.00", "account": "A-2"}, 2),
    ]
    facts, _ = extract_facts(records)
    patterns = evaluate_patterns(facts, [], amount_threshold=Decimal("5000"))

    firing_rules = {p["rule"] for p in patterns["firing"]}
    # Nothing repeats and nothing clears 5000 → both rules evaluated, neither fires.
    assert "duplicate_amount" not in firing_rules
    assert "amount_threshold" not in firing_rules
    assert "duplicate_amount" in patterns["not_fired"]
    assert "amount_threshold" in patterns["not_fired"]


def test_victim_amounts_are_converted_but_flagged_float_sourced() -> None:
    victim = Victim(
        id=uuid.uuid4(),
        case_id=uuid.uuid4(),
        name="Test Victim",
        classification="individual",
        status="reported",
        reported_amount=36000000.0,
        currency="INR",
    )
    (entry,) = extract_victim_financials([victim])
    # Exact string of the value the column held, with the source declared.
    assert entry["reported_amount"] == "36000000.0"
    assert entry["precision"] == "float_source"
    assert "float_source" in entry["limitations"]
    assert entry["currency"] == "INR"
    assert "currency" not in entry["missing"]
    # Absent columns are named, never defaulted to zero.
    assert "amount_lost" in entry["missing"]
    assert "recovery_amount" in entry["missing"]
    assert "incident_date" in entry["missing"]


# -- API / job lifecycle -------------------------------------------------------


async def test_financial_flow_run_stores_exact_reviewable_artifact(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user: ApiUser,
) -> None:
    await _seed_evidence_records(database, _owned_case, FLOW_RECORDS, label="flow-fixture")

    response = await _submit(http_client, _owned_case)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["duplicate"] is False
    assert body["job"]["feature"] == "financial_flow"

    job_id = uuid.UUID(body["job"]["id"])
    job = await _job_row(database, job_id)
    assert job.status == "succeeded"
    summary = dict(job.result_summary or {})
    assert summary["records_scanned"] == 6
    assert summary["records_bounded"] is False
    assert summary["facts_extracted"] == 5
    assert summary["facts_transaction"] == 4
    assert summary["facts_account_reference"] == 1
    assert summary["victim_rows_scanned"] == 0
    assert summary["network_nodes"] == 10
    assert summary["network_edges"] == 7
    assert summary["patterns_firing"] == 4
    assert summary["patterns_not_evaluable"] == 5
    assert summary["patterns_not_fired"] == 1
    assert summary["artifacts_created"] == 1

    artifacts = await _artifacts(database, _owned_case, kind="financial_finding")
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.status == "pending_review"
    assert artifact.origin == "deterministic"
    assert artifact.parser_version == "flow-rules/1.0.0"
    assert str(artifact.analysis_job_id) == str(job_id)
    assert str(artifact.created_by) == str(api_user.id)
    assert artifact.content_hash

    payload = dict(artifact.payload or {})
    assert payload["flow_rules_version"] == "flow-rules/1.0.0"
    assert payload["facts_total"] == 5
    assert payload["facts_bounded"] is False
    assert len(payload["facts"]) == 5

    # Exact totals, computed from FLOW_RECORDS above rather than by re-reading
    # the implementation's own arithmetic.
    (bucket,) = payload["aggregates"]["currency_buckets"]
    assert bucket["currency"] is None
    assert bucket["currency_unknown"] is True
    assert bucket["count"] == 4
    assert bucket["total_records"] == EXPECTED_TOTAL_RECORDS
    assert bucket["total_distinct"] == EXPECTED_TOTAL_DISTINCT
    assert bucket["distinct_groups"] == 3
    assert bucket["distinct_amounts"] == 2
    assert bucket["min"] == "4500.00"
    assert bucket["max"] == "12000.00"
    assert len(bucket["supporting_source_record_ids"]) == 4

    counts = payload["aggregates"]["counts"]
    assert counts["with_currency"] == 0
    assert counts["without_currency"] == 4
    assert counts["with_timestamp"] == 0
    assert counts["without_timestamp"] == 4
    assert counts["with_txn_ref"] == 3
    assert counts["without_txn_ref"] == 1

    # Direction-dependent numbers are refused in the delivered payload too.
    not_computable = payload["aggregates"]["not_computable"]
    assert not_computable["net"] == "not_computable_no_direction"
    assert "zero" not in str(not_computable["net"]).lower()

    # Structure: association edges only, and the honest transfer count.
    network = payload["structure_network"]
    assert network["confirmed_transfer_edges"] == 0
    assert network["nodes_total"] == 10
    assert network["edges_total"] == 7
    edge_keys = {frozenset((e["source"], e["target"])) for e in network["edges"]}
    assert edge_keys == {
        frozenset(("account:ACCSIH001", "merchant:phonepe merchant")),
        frozenset(("account:ACCSIH001", "party:ananya sirohi")),
        frozenset(("account:ACCSIH002", "merchant:paytm merchant")),
        frozenset(("account:ACCSIH002", "party:rohan mehta")),
        frozenset(("account:ACCSIH001", "beneficiary:ananya sirohi")),
        frozenset(("account:3300445566", "bank:securemart")),
        frozenset(("account:3300445566", "party:sunita sharma")),
    }
    assert all(e["edge_kind"] != "transfer" for e in network["edges"])

    # Patterns: four firing with exact evidence, one explicitly not fired.
    firing = {p["rule"]: p for p in payload["patterns"]["firing"]}
    assert set(firing) == {
        "duplicate_amount",
        "amount_threshold",
        "missing_currency",
        "missing_timestamp",
    }
    assert firing["duplicate_amount"]["evidence"]["amount"] == "4500.00"
    assert firing["duplicate_amount"]["evidence"]["record_count"] == 3
    assert firing["amount_threshold"]["evidence"]["amounts"] == ["12000.00"]
    assert payload["patterns"]["not_fired"] == ["victim_loss_unmatched"]
    assert len(payload["patterns"]["not_evaluable"]) == 5

    # Every fact is traceable to the record it came from.
    for fact in payload["facts"]:
        locator = dict(fact["source_locator"])
        assert locator["record_no"] >= 1
        assert locator["evidence_file_id"]
        assert fact["amount_precision"] in (None, "string_source", "float_source", "int_source")

    # Coverage gaps are stated as limitations, not left for the reader to infer.
    limitations = " ".join(payload["limitations"])
    assert "no transactions table exists" in limitations
    assert "no payer/sender key" in limitations
    assert "never labelled with a" in limitations
    assert payload["calculation_definitions"]["net_flow"].startswith("not computed")

    audit = await _audit_row(database, action="flow.analysis_completed", resource_id=job_id)
    assert audit is not None


async def test_financial_flow_submission_is_one_active_job_and_typed_409(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    factory = database.session_factory()
    # A financial-flow job already running for this case blocks a second one.
    async with factory() as session:
        session.add(
            AnalysisJob(
                case_id=str(_owned_case),
                feature="financial_flow",
                status="running",
                idempotency_key=f"running-financial_flow-{uuid.uuid4().hex[:8]}",
                attempts=1,
                timeout_seconds=300,
                actor_id=None,
            )
        )
        await session.commit()

    refused = await _submit(http_client, _owned_case)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == CODE_FLOW_ACTIVE

    # Once the stale/active job is cleared by the runner the same submission is
    # accepted as a new attempt.
    async with factory() as session:
        jobs = (
            await session.execute(
                select(AnalysisJob).where(
                    AnalysisJob.case_id == str(_owned_case),
                    AnalysisJob.feature == "financial_flow",
                )
            )
        ).scalars()
        for job in jobs:
            job.status = "failed"
            job.error = "cleared for the retry assertion"
        await session.commit()

    accepted = await _submit(http_client, _owned_case)
    assert accepted.status_code == 202, accepted.text
    job_id = uuid.UUID(accepted.json()["job"]["id"])
    job = await _job_row(database, job_id)
    # No evidence was seeded here: an empty case succeeds with an honest
    # empty result rather than failing.
    assert job.status == "succeeded"
    artifacts = await _artifacts(database, _owned_case, kind="financial_finding")
    assert len(artifacts) == 1
    payload = dict(artifacts[0].payload or {})
    assert payload["facts_total"] == 0
    assert payload["aggregates"]["currency_buckets"] == []
    assert payload["structure_network"]["confirmed_transfer_edges"] == 0
    assert payload["patterns"]["firing"] == []


async def test_financial_flow_requires_the_analysis_permission(
    database: Database,
    _owned_case: uuid.UUID,
    user_factory,
) -> None:
    viewer = await user_factory(role="VIEWER")
    async with _client(viewer.token) as client:
        response = await _submit(client, _owned_case)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == CODE_INSUFFICIENT_PERMISSION

    # No job, no artifact: the denial happened before any work was queued.
    factory = database.session_factory()
    async with factory() as session:
        jobs = (
            await session.execute(
                select(AnalysisJob).where(
                    AnalysisJob.case_id == str(_owned_case),
                    AnalysisJob.feature == "financial_flow",
                )
            )
        ).scalars()
        assert list(jobs) == []
    assert await _artifacts(database, _owned_case, kind="financial_finding") == []


async def test_financial_flow_denies_a_stranger_to_the_case(
    database: Database,
    _owned_case: uuid.UUID,
    user_factory,
) -> None:
    stranger = await user_factory(role="INVESTIGATOR")
    async with _client(stranger.token) as client:
        response = await _submit(client, _owned_case)
    assert response.status_code == 403, response.text
    assert await _artifacts(database, _owned_case, kind="financial_finding") == []


async def test_runner_denies_when_case_access_was_revoked(
    database: Database,
    settings,
    _owned_case: uuid.UUID,
    user_factory,
) -> None:
    """Authorization is re-checked at execution time, not trusted from submit."""
    member = await user_factory(role="INVESTIGATOR")
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            CaseMember(case_id=_owned_case, user_id=member.id, role="collaborator")
        )
        await session.commit()
    await _seed_evidence_records(database, _owned_case, FLOW_RECORDS, label="revoked")
    job_id = await _seed_pending_job(database, _owned_case, actor_id=member.id)

    # Access revoked between submission and execution.
    async with factory() as session:
        await session.execute(delete(CaseMember).where(CaseMember.user_id == member.id))
        await session.commit()

    job = await _run_job(database, job_id, settings=settings)

    assert job.status == "failed"
    assert dict(job.result_summary or {})["error_code"] == CODE_CASE_ACCESS_DENIED
    assert "revoked" in (job.error or "")
    # Denied before a single record was analyzed: no artifact, no analysis audit.
    assert await _artifacts(database, _owned_case, kind="financial_finding") == []
    denied = await _audit_row(database, action="flow.denied", resource_id=job_id)
    assert denied is not None
    assert dict(denied.metadata_ or {}).get("code") == CODE_CASE_ACCESS_DENIED


async def test_identical_rerun_reuses_the_artifact(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    """Content-hash dedupe makes a resubmission idempotent, not duplicative."""
    await _seed_evidence_records(database, _owned_case, FLOW_RECORDS, label="rerun")

    first = await _submit(http_client, _owned_case)
    assert first.status_code == 202, first.text
    first_job = await _job_row(database, uuid.UUID(first.json()["job"]["id"]))
    assert first_job.status == "succeeded"
    artifacts = await _artifacts(database, _owned_case, kind="financial_finding")
    assert len(artifacts) == 1
    original_hash = artifacts[0].content_hash

    second = await _submit(http_client, _owned_case)
    assert second.status_code == 202, second.text
    second_body = second.json()
    # A later submission is a new attempt (not a blocked duplicate) …
    assert second_body["duplicate"] is False
    second_job = await _job_row(database, uuid.UUID(second_body["job"]["id"]))
    assert second_job.id != first_job.id
    assert second_job.status == "succeeded"
    assert dict(second_job.result_summary or {})["artifacts_reused"] == 1

    # … but the identical analysis content lands on the same artifact row.
    artifacts = await _artifacts(database, _owned_case, kind="financial_finding")
    assert len(artifacts) == 1
    assert artifacts[0].content_hash == original_hash


# -- bounded trace (read-only endpoint) ----------------------------------------


async def _trace(
    client: AsyncClient, case_id: uuid.UUID, body: dict[str, object]
) -> httpx.Response:
    return await client.post(
        f"{PREFIX}/cases/{case_id}/evidence-intelligence/financial-flow/trace",
        json=body,
    )


def _trace_edge(**overrides: object) -> dict[str, object]:
    edge: dict[str, object] = {
        "edge_kind": "association",
        "derivation": "co_occurrence",
        "confidence": "suspected",
        "relationship_type": None,
        "supporting_source_record_ids": ["rec-1"],
    }
    edge.update(overrides)
    return edge


def test_trace_paths_are_bounded_deterministic_and_honest_about_ends() -> None:
    # a -> b -> c chain
    chain = {
        "a": {"b": _trace_edge()},
        "b": {"a": _trace_edge(), "c": _trace_edge()},
        "c": {"b": _trace_edge()},
    }

    # Depth 1 stops at b with more evidence beyond the bound: not a dead end.
    paths, truncated = _trace_paths("a", chain, max_depth=1, max_paths=10)
    assert truncated is False
    assert [p["nodes"] for p in paths] == [["a", "b"]]
    assert paths[0]["end_state"] == "depth_limit"
    assert paths[0]["incomplete"] is False

    # Full depth reaches c: the trail genuinely stops in the evidence.
    paths, _ = _trace_paths("a", chain, max_depth=5, max_paths=10)
    assert [p["nodes"] for p in paths] == [["a", "b", "c"]]
    assert paths[0]["end_state"] == "dead_end"
    assert paths[0]["incomplete"] is True
    assert paths[0]["depth"] == 2

    # A cycle never revisits a node.
    cyclic = {
        "a": {"b": _trace_edge()},
        "b": {"a": _trace_edge(), "c": _trace_edge()},
        "c": {"b": _trace_edge(), "a": _trace_edge()},
    }
    paths, _ = _trace_paths("a", cyclic, max_depth=5, max_paths=10)
    for path in paths:
        assert len(path["nodes"]) == len(set(path["nodes"]))

    # Path budget is enforced and the truncation is reported, not hidden.
    star = {
        "a": {"b": _trace_edge(), "c": _trace_edge(), "d": _trace_edge()},
        "b": {"a": _trace_edge()},
        "c": {"a": _trace_edge()},
        "d": {"a": _trace_edge()},
    }
    paths, truncated = _trace_paths("a", star, max_depth=4, max_paths=2)
    assert len(paths) == 2
    assert truncated is True

    # Deterministic: identical input yields byte-identical output, twice.
    first, _ = _trace_paths("a", star, max_depth=4, max_paths=10)
    second, _ = _trace_paths("a", star, max_depth=4, max_paths=10)
    assert first == second


async def test_trace_returns_association_paths_with_typed_hops(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    settings,
) -> None:
    await _seed_evidence_records(database, _owned_case, FLOW_RECORDS, label="trace")

    response = await _trace(http_client, _owned_case, {"target": "ACC-SIH-001"})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "ok"
    assert body["edge_kind"] == "association"
    assert body["start_node"] == "account:ACCSIH001"
    assert body["target_degree"] == 3
    assert body["paths_bounded"] is False
    # Honest scope: the network was really scanned, and it holds no transfers.
    assert body["network"]["nodes_total"] == 10
    assert body["network"]["edges_total"] == 7
    assert body["network"]["confirmed_transfer_edges"] == 0

    # Neighbours are visited in sorted node-id order (deterministic contract).
    assert [path["nodes"] for path in body["paths"]] == [
        ["account:ACCSIH001", "beneficiary:ananya sirohi"],
        ["account:ACCSIH001", "merchant:phonepe merchant"],
        ["account:ACCSIH001", "party:ananya sirohi"],
    ]
    for path in body["paths"]:
        assert path["depth"] == 1
        # The trail stops here in the ingested evidence — no destination guessed.
        assert path["end_state"] == "dead_end"
        assert path["incomplete"] is True
        (hop,) = path["hops"]
        assert hop["edge_kind"] == "association"
        assert hop["confidence"] == "suspected"
        assert hop["relationship_type"] is None
        assert hop["supporting_source_record_ids"]

    # Effective bounds are echoed with the result.
    assert body["bounds"]["records_scanned"] == 6
    assert body["bounds"]["max_depth"] == settings.FLOW_TRACE_MAX_DEPTH
    assert body["bounds"]["max_paths"] == settings.FLOW_TRACE_MAX_PATHS
    assert body["bounds"]["max_records"] == settings.FLOW_MAX_RECORDS
    assert any("not where money went" in lim for lim in body["limitations"])

    # Repeated calls return identical results.
    again = await _trace(http_client, _owned_case, {"target": "ACC-SIH-001"})
    assert again.json()["paths"] == body["paths"]


async def test_trace_transaction_target_resolves_via_reference(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    await _seed_evidence_records(database, _owned_case, FLOW_RECORDS, label="trace-txn")

    response = await _trace(
        http_client, _owned_case, {"target": "txn-sih-001", "target_kind": "transaction"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    # Two source records carry that reference (the transfer recorded twice).
    assert body["matched_facts"] == 2
    assert body["start_node"] == "account:ACCSIH001"
    assert len(body["paths"]) == 3

    missing = await _trace(
        http_client, _owned_case, {"target": "TXN-DOES-NOT-EXIST", "target_kind": "transaction"}
    )
    missing_body = missing.json()
    assert missing_body["status"] == "not_found"
    assert missing_body["matched_facts"] == 0
    assert missing_body["paths"] == []


async def test_trace_transfer_kind_reports_the_ingest_gap(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    """The capability exists; the answer is 'absent', never an approximation."""
    await _seed_evidence_records(database, _owned_case, FLOW_RECORDS, label="trace-transfer")

    response = await _trace(
        http_client, _owned_case, {"target": "ACC-SIH-001", "edge_kind": "transfer"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "insufficient_data"
    assert body["reason"] == "no_transfer_edges_in_ingest"
    assert body["paths"] == []
    # The real scan scope is still reported so a bare zero cannot be misread as
    # "this case has no financial structure at all".
    assert body["network"]["nodes_total"] == 10
    assert body["network"]["edges_total"] == 7
    assert body["network"]["confirmed_transfer_edges"] == 0
    assert any("no transfer path to return" in lim for lim in body["limitations"])


async def test_trace_unknown_target_reports_scope_not_a_guess(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
) -> None:
    await _seed_evidence_records(database, _owned_case, FLOW_RECORDS, label="trace-missing")

    response = await _trace(http_client, _owned_case, {"target": "ACC-NOPE-999"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "not_found"
    assert body["reason"] == "no_account_matching_that_reference_is_documented_in_this_case"
    assert body["start_node"] is None
    assert body["paths"] == []
    # The scan still happened: scope is reported alongside the miss.
    assert body["network"]["nodes_total"] == 10
    assert body["bounds"]["records_scanned"] == 6


async def test_trace_clamps_bounds_and_rejects_bad_input(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    settings,
) -> None:
    await _seed_evidence_records(database, _owned_case, FLOW_RECORDS, label="trace-bounds")

    # Requested bounds beyond the server configuration are clamped, not obeyed.
    oversized = await _trace(
        http_client, _owned_case, {"target": "ACC-SIH-001", "max_depth": 999, "max_paths": 999}
    )
    assert oversized.status_code == 200, oversized.text
    bounds = oversized.json()["bounds"]
    assert bounds["max_depth"] == settings.FLOW_TRACE_MAX_DEPTH
    assert bounds["max_paths"] == settings.FLOW_TRACE_MAX_PATHS

    # A smaller explicit bound is honoured.
    small = await _trace(http_client, _owned_case, {"target": "ACC-SIH-001", "max_depth": 1})
    assert small.json()["bounds"]["max_depth"] == 1
    assert len(small.json()["paths"]) == 3

    # Invalid values never reach the analyzer.
    for bad_body in (
        {"target": "ACC-SIH-001", "max_depth": 0},
        {"target": "ACC-SIH-001", "target_kind": "wallet"},
        {"target": "ACC-SIH-001", "edge_kind": "laundering"},
        {"target": ""},
    ):
        rejected = await _trace(http_client, _owned_case, bad_body)
        assert rejected.status_code == 422, (bad_body, rejected.text)


async def test_trace_is_read_only_and_permission_scoped(
    database: Database,
    _owned_case: uuid.UUID,
    user_factory,
    settings,
) -> None:
    await _seed_evidence_records(database, _owned_case, FLOW_RECORDS, label="trace-perm")

    # A viewer holds evidence.read (but not ingestion.run) — tracing is read-only.
    viewer = await user_factory(role="VIEWER")
    factory = database.session_factory()
    async with factory() as session:
        session.add(
            CaseMember(case_id=_owned_case, user_id=viewer.id, role="collaborator")
        )
        await session.commit()
    async with _client(viewer.token) as client:
        allowed = await _trace(client, _owned_case, {"target": "ACC-SIH-001"})
    assert allowed.status_code == 200, allowed.text

    # A stranger to the case is refused before any record is read.
    stranger = await user_factory(role="INVESTIGATOR")
    async with _client(stranger.token) as client:
        refused = await _trace(client, _owned_case, {"target": "ACC-SIH-001"})
    assert refused.status_code == 403, refused.text

    # Anonymous callers are refused with 401.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as anonymous:
        unauthenticated = await _trace(anonymous, _owned_case, {"target": "ACC-SIH-001"})
    assert unauthenticated.status_code == 401

    # Read-only: no job queued, no artifact written, nothing mutated.
    factory = database.session_factory()
    async with factory() as session:
        jobs = (
            await session.execute(
                select(AnalysisJob).where(AnalysisJob.case_id == str(_owned_case))
            )
        ).scalars()
        assert list(jobs) == []
    assert await _artifacts(database, _owned_case, kind="financial_finding") == []


# -- on-demand AI explanation (validated, flagged child artifact) ----------------


async def test_financial_explain_stores_flagged_child_artifact(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user: ApiUser,
    phase2_fake_ai,
) -> None:
    await _seed_evidence_records(database, _owned_case, FLOW_RECORDS, label="explain-fixture")
    response = await _submit(http_client, _owned_case)
    assert response.status_code == 202, response.text

    findings = await _artifacts(database, _owned_case, kind="financial_finding")
    assert len(findings) == 1
    finding = findings[0]

    explain = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{finding.id}/explain"
    )
    assert explain.status_code == 200, explain.text
    body = explain.json()
    assert body["explanation"] is not None
    assert body["text"]

    # Only the recorded deterministic facts were handed to the model.
    assert phase2_fake_ai.flow_explain_calls
    sent = phase2_fake_ai.flow_explain_calls[0]
    assert set(sent) <= {"case_id", "facts", "patterns", "aggregates", "limitations"}

    # The child is flagged ai_unverified, origin llm, parented to the finding;
    # the parent deterministic artifact is untouched.
    rows = await _artifacts(database, _owned_case, kind="financial_finding")
    child = next(a for a in rows if str(a.parent_artifact_id) == str(finding.id))
    assert child.origin == "llm"
    assert child.validation_status == "flagged"
    assert child.status == "recorded"
    assert (child.payload or {}).get("type") == "ai_explanation"
    assert "ai_unverified" in [e["code"] for e in child.validation_errors or []]

    factory = database.session_factory()
    async with factory() as session:
        parent = await session.get(DerivedArtifact, finding.id)
        assert parent is not None
        assert parent.status == "pending_review"
        assert parent.origin == "deterministic"


async def test_financial_explain_drops_a_fabricated_number(
    http_client: AsyncClient,
    database: Database,
    _owned_case: uuid.UUID,
    api_user: ApiUser,
    phase2_fake_ai,
) -> None:
    await _seed_evidence_records(database, _owned_case, FLOW_RECORDS, label="fabricated-fixture")
    response = await _submit(http_client, _owned_case)
    assert response.status_code == 202, response.text

    findings = await _artifacts(database, _owned_case, kind="financial_finding")
    finding = findings[0]
    before = len(await _artifacts(database, _owned_case, kind="financial_finding"))

    # The model quotes an amount that never appears in the deterministic result.
    phase2_fake_ai.flow_explain_replies = [
        json.dumps(
            {
                "summary": "the total moved was 999999999",
                "why_patterns_fired": ["fake: invented total"],
                "cited_transaction_ids": [],
                "alternative_explanations": ["a legitimate transfer"],
                "missing_information": ["currency"],
                "verification_steps": ["verify"],
            }
        )
    ]
    explain = await http_client.post(
        f"{PREFIX}/cases/{_owned_case}/evidence-intelligence/artifacts/{finding.id}/explain"
    )
    assert explain.status_code == 422, explain.text
    assert explain.json()["error"]["code"] == CODE_AI_EXPLANATION_INVALID
    # Dropped, not stored: no child artifact was recorded.
    assert len(await _artifacts(database, _owned_case, kind="financial_finding")) == before
