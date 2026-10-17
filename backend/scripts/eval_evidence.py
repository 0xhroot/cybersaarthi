"""Live evaluation harness for evidence intelligence (phase 2, features 1+9).

Extends the Phase-1 harness conventions (``scripts/eval_model.py``: real HTTP,
real auth, real local inference, independent verification against PostgreSQL
and MinIO - never the server's self-report) to the ingestion copilot and the
chain-of-custody auditor:

* **claim recall** (reported, model quality) - frozen verbatim claims per
  synthetic evidence file must reappear in some artifact's extracted fields
  (compared with the same deterministic comparator the pipeline uses).
* **extraction precision** (reported, model quality) - extracted fields that
  traced back to the source record, over all extracted fields, recomputed by
  the harness from artifact payloads + validation errors.
* **field-level validation rate** (reported) - fields with no validation error
  over the 12 schema fields, per artifact.
* **unsupported-claim rate** (reported) - fields flagged ``value_not_in_source``
  over extracted fields.
* **locator accuracy** (hard gate) - for every pending artifact the harness
  re-reads the cited source record from the database and re-verifies each
  non-empty claim against that record's ``raw_data``; a claim not present in
  the cited record is an ungrounded locator (a pipeline bug, not model noise).
* **hash verification correctness** (hard gate) - three real object states
  (intact / overwritten / deleted) must map to match / mismatch /
  missing_source exactly, with the calculated digest re-hashed by the harness
  from MinIO directly.
* **custody rule agreement** (hard gate) - replayed custody events must yield
  exactly the deterministic rule set (unacknowledged transfer), and clean
  evidence must yield ZERO findings (custody false-positive gate).

Model-quality metrics are reported, never gated; deterministic properties are
gated. Everything the harness creates (one synthetic case, its evidence and
objects) is deleted before exit.

Run via the entry point (loads the environment, checks both servers):

    ./scripts/ai/eval_evidence.sh

or directly from ``backend/``:

    .venv/bin/python -m scripts.eval_evidence_intelligence --report /tmp/ei.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from app.core.config import get_settings
from app.db.postgres import Database
from app.db.storage import Storage
from app.services.structured_extraction import value_matches_source

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DEFAULT = (
    REPO_ROOT
    / "backend"
    / "tests"
    / "fixtures"
    / "evidence_intelligence"
    / "ingestion_live_checks.json"
)
REPORT_DEFAULT = REPO_ROOT / "ai_runtime" / "eval_evidence_report.json"
API_BASE_DEFAULT = "http://localhost:8000/api/v1"

REQUEST_TIMEOUT_SECONDS = 240.0
JOB_POLL_TIMEOUT_SECONDS = 420.0
TERMINAL_JOB_STATES = {"succeeded", "partial", "failed", "canceled"}

LIMITATIONS = [
    "n is small and the evidence is synthetic TXT written to contain verbatim "
    "claims; recall/precision measure the local model on this set only.",
    "PDF parsing, OCR-required refusal, encryption and page caps are covered "
    "by the deterministic fixture suite (tests/fixtures/evidence_intelligence) "
    "and are not re-exercised live here.",
    "Extraction claims are verified against the source record the pipeline "
    "fed to the model (cited locator), which is the honest comparison point "
    "for locator accuracy; broader world-knowledge accuracy is out of scope.",
    "Custody rules are deterministic by design: the live section replays "
    "recorded events through the API and gates on exact rule agreement and "
    "zero false positives, not on model judgement.",
]


def _norm(value: Any) -> str:
    return " ".join(str(value).lower().split())


class EvidenceEvalRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.api = httpx.AsyncClient(
            base_url=args.api_base, timeout=REQUEST_TIMEOUT_SECONDS
        )
        self.token: str | None = None
        self.settings = get_settings()
        self.database = Database(self.settings)
        self.storage = Storage(self.settings)
        self.case_id: str | None = None
        self.gates: dict[str, bool] = {}
        self.report: dict[str, Any] = {}

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def login(self, username: str, password: str) -> None:
        response = await self.api.post(
            "/auth/login", json={"username": username, "password": password}
        )
        response.raise_for_status()
        self.token = response.json()["access_token"]

    async def ai_ready(self) -> bool:
        response = await self.api.get("/ai/status", headers=self._headers())
        if response.status_code != 200:
            return False
        return bool(response.json().get("ready"))

    # -- shared helpers ------------------------------------------------------

    async def _upload(self, name: str, text: str) -> dict[str, Any]:
        response = await self.api.post(
            f"/cases/{self.case_id}/evidence",
            files={"file": (name, text.encode(), "text/plain")},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    async def _poll_job(self, job_id: str, *, feature: str) -> dict[str, Any]:
        deadline = time.monotonic() + JOB_POLL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            response = await self.api.get(
                f"/cases/{self.case_id}/evidence-intelligence/jobs",
                params={"feature": feature},
                headers=self._headers(),
            )
            response.raise_for_status()
            for item in response.json()["items"]:
                if item["id"] == job_id and item["status"] in TERMINAL_JOB_STATES:
                    return item
            await asyncio.sleep(1.0)
        raise TimeoutError(f"{feature} job {job_id} did not reach a terminal state")

    async def _artifacts(self, kind: str) -> list[dict[str, Any]]:
        response = await self.api.get(
            f"/cases/{self.case_id}/evidence-intelligence/artifacts",
            params={"kind": kind},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()["items"]

    # -- ingestion section ----------------------------------------------------

    async def _eval_ingestion(self, fixtures: dict[str, Any]) -> dict[str, Any]:
        per_case: list[dict[str, Any]] = []
        totals = {
            "claims_expected": 0,
            "claims_recovered": 0,
            "fields_claimed": 0,
            "fields_verified": 0,
            "fields_unsupported": 0,
            "fields_schema_total": 0,
            "locator_violations": 0,
            "schema_invalid_artifacts": 0,
        }
        for case in fixtures["cases"]:
            print(f"  ingestion: {case['id']}", flush=True)
            evidence = await self._upload(case["filename"], case["text"])
            submitted = await self.api.post(
                f"/cases/{self.case_id}/evidence-intelligence/extract",
                json={"evidence_file_id": evidence["id"]},
                headers=self._headers(),
            )
            assert submitted.status_code == 202, submitted.text
            started = time.monotonic()
            job = await self._poll_job(
                submitted.json()["job"]["id"], feature="ingestion"
            )
            job_latency_ms = int((time.monotonic() - started) * 1000)

            artifacts = [
                a
                for a in await self._artifacts("extraction")
                if a["evidence_file_id"] == evidence["id"]
            ]
            claimed_values: dict[str, list[str]] = {}
            recovered = 0
            fields_claimed = fields_unsupported = schema_invalid = 0
            locator_violations: list[dict[str, Any]] = []
            factory = self.database.session_factory()
            for artifact in artifacts:
                payload = artifact["payload"] or {}
                if payload.get("extraction_failed"):
                    schema_invalid += 1
                    continue
                fields = payload.get("fields") or {}
                errors = {
                    str(e.get("field")): str(e.get("code"))
                    for e in (artifact.get("validation_errors") or [])
                }
                for name, values in fields.items():
                    values = [str(v) for v in values]
                    if not values:
                        continue
                    fields_claimed += 1
                    claimed_values.setdefault(name, []).extend(values)
                    unsupported = errors.get(name) == "value_not_in_source"
                    if unsupported:
                        fields_unsupported += 1
                    # Independent locator check: re-read the cited source
                    # record and re-verify every *verified* claim against ITS
                    # raw_data. Claims the pipeline already disclosed as
                    # unsupported are excluded - they are pending-review
                    # noise, not presented as verified facts.
                    record_id = artifact.get("source_record_id")
                    if record_id is None:
                        locator_violations.append(
                            {"artifact": artifact["id"], "reason": "no source_record_id"}
                        )
                        continue
                    async with factory() as session:
                        from app.models import SourceRecord

                        record = await session.get(SourceRecord, uuid.UUID(str(record_id)))
                        assert record is not None, f"source record {record_id} missing"
                        raw = dict(record.raw_data)
                        locator = artifact.get("source_locator") or {}
                        if locator.get("record_no") != record.record_no:
                            locator_violations.append(
                                {"artifact": artifact["id"], "reason": "record_no mismatch"}
                            )
                        if not unsupported and not value_matches_source(
                            values, list(raw.values())
                        ):
                            locator_violations.append(
                                {
                                    "artifact": artifact["id"],
                                    "field": name,
                                    "reason": "verified claim not in cited record",
                                }
                            )
            for field_name, expected in case["expected_claims"].items():
                for value in expected:
                    candidates = claimed_values.get(field_name, [])
                    if value_matches_source(value, candidates) or any(
                        _norm(value) == _norm(c) for c in candidates
                    ):
                        recovered += 1
                    totals["claims_expected"] += 1
            per_case.append(
                {
                    "id": case["id"],
                    "job_status": job["status"],
                    "job_latency_ms": job_latency_ms,
                    "artifacts": len(artifacts),
                    "schema_invalid_artifacts": schema_invalid,
                    "claims_expected": sum(len(v) for v in case["expected_claims"].values()),
                    "claims_recovered": recovered,
                    "locator_violations": locator_violations,
                }
            )
            totals["claims_recovered"] += recovered
            totals["fields_claimed"] += fields_claimed
            totals["fields_unsupported"] += fields_unsupported
            totals["fields_schema_total"] += 12 * len(artifacts)
            totals["locator_violations"] += len(locator_violations)
            totals["schema_invalid_artifacts"] += schema_invalid

        claimed = totals["fields_claimed"]
        totals["fields_verified"] = claimed - totals["fields_unsupported"]
        expected = totals["claims_expected"]
        return {
            "n_cases": len(fixtures["cases"]),
            "claim_recall": (
                f"{totals['claims_recovered']}/{expected}"
                + (f" ({totals['claims_recovered'] / expected:.0%})" if expected else "")
            ),
            "extraction_precision": (
                f"{totals['fields_verified']}/{claimed}"
                + (f" ({totals['fields_verified'] / claimed:.0%})" if claimed else "")
            ),
            "field_level_validation_rate": (
                f"{totals['fields_schema_total'] - totals['fields_unsupported']}"
                f"/{totals['fields_schema_total']}"
                if totals["fields_schema_total"]
                else "n/a"
            ),
            "unsupported_claim_rate": (
                f"{totals['fields_unsupported']}/{claimed}"
                + (
                    f" ({totals['fields_unsupported'] / claimed:.0%})"
                    if claimed
                    else ""
                )
            ),
            "schema_invalid_artifacts": totals["schema_invalid_artifacts"],
            "locator_violations": totals["locator_violations"],
            "per_case": per_case,
        }

    # -- integrity section -----------------------------------------------------

    async def _eval_integrity(self) -> dict[str, Any]:
        print("  integrity: match / mismatch / missing_source", flush=True)
        text = (
            "Integrity probe file for the phase-2 evaluation harness; "
            "its bytes are hashed and re-hashed independently."
        )
        evidence = await self._upload("integrity-probe.txt", text)
        factory = self.database.session_factory()
        async with factory() as session:
            from app.models import EvidenceFile

            row = await session.get(EvidenceFile, uuid.UUID(evidence["id"]))
            assert row is not None
            key = row.stored_key
        digest = evidence["sha256"]
        states: list[dict[str, Any]] = []

        async def verify() -> dict[str, Any]:
            response = await self.api.post(
                f"/cases/{self.case_id}/evidence-integrity/verify",
                json={"evidence_file_id": evidence["id"]},
                headers=self._headers(),
            )
            assert response.status_code == 200, response.text
            return response.json()

        async def harness_hash() -> str | None:
            import asyncio as aio

            try:
                raw = await aio.to_thread(self.storage.download, key)
            except Exception:  # noqa: BLE001 - absent object is the point
                return None
            import hashlib

            return hashlib.sha256(raw).hexdigest()

        intact = await verify()
        states.append(
            {
                "state": "intact",
                "expected": "match",
                "actual": intact["status"],
                "recorded_sha_matches_upload": intact["expected_sha256"] == digest,
                "harness_hash_matches": (await harness_hash()) == intact["calculated_sha256"],
            }
        )
        import asyncio as aio

        original = text.encode()
        await aio.to_thread(
            self.storage.upload, key, b"swapped by the eval harness", "text/plain"
        )
        try:
            tampered = await verify()
            states.append(
                {
                    "state": "overwritten",
                    "expected": "mismatch",
                    "actual": tampered["status"],
                    "harness_hash_matches": (
                        (await harness_hash()) == tampered["calculated_sha256"]
                    ),
                }
            )
        finally:
            await aio.to_thread(self.storage.upload, key, original, "text/plain")
        await aio.to_thread(self.storage.delete, key)
        try:
            gone = await verify()
            states.append(
                {
                    "state": "deleted",
                    "expected": "missing_source",
                    "actual": gone["status"],
                    "harness_hash_matches": gone["calculated_sha256"] is None,
                }
            )
        finally:
            await aio.to_thread(self.storage.upload, key, original, "text/plain")
        correct = sum(
            1
            for s in states
            if s["actual"] == s["expected"] and s["harness_hash_matches"]
        )
        return {"n_states": len(states), "correct": correct, "states": states}

    # -- custody section --------------------------------------------------------

    async def _submit_audit(self) -> dict[str, Any]:
        response = await self.api.post(
            f"/cases/{self.case_id}/evidence-integrity/custody-audit",
            json={},
            headers=self._headers(),
        )
        assert response.status_code == 202, response.text
        return await self._poll_job(response.json()["job"]["id"], feature="custody")

    async def _eval_custody(self) -> dict[str, Any]:
        print("  custody: rule agreement + zero false positives", flush=True)
        flagged_evidence = await self._upload(
            "custody-gap.txt", "sealed device handover log for lab analysis"
        )
        created = await self.api.post(
            f"/cases/{self.case_id}/evidence/{flagged_evidence['id']}/custody-events",
            json={
                "event_type": "transferred",
                "occurred_at": "2026-01-05T10:00:00+00:00",
                "transferor": "Officer A",
                "recipient": "Forensics Lab B",
            },
            headers=self._headers(),
        )
        assert created.status_code == 201, created.text
        gap_job = await self._submit_audit()
        gap_rules = sorted(
            {
                str((a["payload"] or {}).get("rule"))
                for a in await self._artifacts("custody_finding")
                if a["evidence_file_id"] == flagged_evidence["id"]
                and (a["payload"] or {}).get("type") == "custody_finding"
            }
        )

        clean_evidence = await self._upload(
            "custody-clean.txt", "access register copy kept with the duty officer"
        )
        clean_job = await self._submit_audit()
        clean_findings = [
            a
            for a in await self._artifacts("custody_finding")
            if a["evidence_file_id"] == clean_evidence["id"]
        ]
        return {
            "n_cases": 2,
            "gap_job_status": gap_job["status"],
            "clean_job_status": clean_job["status"],
            "gap_rules": gap_rules,
            "clean_findings": len(clean_findings),
        }

    # -- lifecycle -----------------------------------------------------------------

    async def run(self) -> int:
        fixtures = json.loads(self.args.fixtures.read_text(encoding="utf-8"))
        try:
            await self.database.ping()
            await self.login(self.args.username, self.args.password)
        except Exception as exc:  # noqa: BLE001 - setup failure
            print(f"setup failure: {exc}", file=sys.stderr)
            return 2
        if not await self.ai_ready():
            print(
                "AI runtime is not ready (see /api/v1/ai/status); start the "
                "model server per docs/ai/LOCAL_MODEL_SETUP.md",
                file=sys.stderr,
            )
            return 2

        created = await self.api.post(
            "/cases",
            json={
                "title": "phase-2 evidence intelligence eval (synthetic)",
                "description": "created and deleted by scripts/eval_evidence.py",
            },
            headers=self._headers(),
        )
        created.raise_for_status()
        self.case_id = created.json()["id"]
        print(f"synthetic case {self.case_id}", flush=True)

        try:
            self.report["ingestion"] = await self._eval_ingestion(fixtures)
            self.report["integrity"] = await self._eval_integrity()
            self.report["custody"] = await self._eval_custody()
        finally:
            await self._cleanup_case()
            await self.api.aclose()
            await self.database.close()
            self.storage.close()

        ingestion_ok = self.report["ingestion"]["locator_violations"] == 0
        integrity_ok = (
            self.report["integrity"]["correct"] == self.report["integrity"]["n_states"]
        )
        custody_ok = (
            self.report["custody"]["gap_rules"] == ["custody.unacknowledged_transfer"]
            and self.report["custody"]["clean_findings"] == 0
            and self.report["custody"]["gap_job_status"] == "succeeded"
            and self.report["custody"]["clean_job_status"] == "succeeded"
        )
        self.gates = {
            "locator_accuracy_100": ingestion_ok,
            "hash_verification_correct": integrity_ok,
            "custody_rule_agreement_and_no_false_positives": custody_ok,
        }
        self.report["gates"] = self.gates
        self.report["limitations"] = LIMITATIONS

        self.args.report.parent.mkdir(parents=True, exist_ok=True)
        self.args.report.write_text(json.dumps(self.report, indent=2), encoding="utf-8")
        print(json.dumps(self.report, indent=2), flush=True)
        print(f"report written to {self.args.report}", flush=True)
        return 0 if all(self.gates.values()) else 1

    async def _cleanup_case(self) -> None:
        """Remove everything this run created: MinIO objects, then rows.

        Cases have no public delete endpoint (``archived`` is terminal), so the
        synthetic eval case is removed the way the API test hygiene does -
        directly in the database (audit rows first: their FK is SET NULL) -
        plus every object under its storage prefix. Best-effort: a failure is
        printed and reported, never silent.
        """
        if self.case_id is None:
            return
        case_uuid = uuid.UUID(self.case_id)
        outcome: dict[str, Any] = {}
        try:
            outcome["objects_removed"] = await asyncio.to_thread(
                self.storage.delete_case_objects, case_uuid
            )
            from app.models import AIConversation, AuditLog, Case, CaseMember
            from sqlalchemy import delete as sa_delete

            factory = self.database.session_factory()
            async with factory() as session:
                await session.execute(
                    sa_delete(AuditLog).where(AuditLog.case_id == case_uuid)
                )
                await session.execute(
                    sa_delete(CaseMember).where(CaseMember.case_id == case_uuid)
                )
                await session.execute(
                    sa_delete(AIConversation).where(AIConversation.case_id == case_uuid)
                )
                await session.execute(sa_delete(Case).where(Case.id == case_uuid))
                await session.commit()
            outcome["case_deleted"] = True
        except Exception as exc:  # noqa: BLE001 - cleanup is best-effort
            outcome["case_deleted"] = False
            outcome["error"] = str(exc)
            print(f"cleanup warning: {exc}", file=sys.stderr)
        self.report["cleanup"] = outcome


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--fixtures", type=Path, default=FIXTURE_DEFAULT)
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    parser.add_argument("--api-base", default=API_BASE_DEFAULT)
    parser.add_argument("--username", default="investigator")
    parser.add_argument("--password", default="investigator-dev-password")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(EvidenceEvalRunner(_parse_args(argv)).run())


if __name__ == "__main__":
    sys.exit(main())
