"""Live + golden-fixture evaluation harness for case intelligence (phase 3).

Extends the Phase-1/2 harness conventions (``scripts/eval_model.py``,
``scripts/eval_evidence.py``: real HTTP, real auth, real local inference,
independent verification against PostgreSQL - never the server's self-report)
to the three phase-3 features.

The harness has two independent sections:

* **Deterministic golden-fixture metrics** (no stack required) - replays the
  frozen golden sets (``entity_resolution_checks.json``,
  ``timeline_checks.json``, ``contradiction_checks.json``) through the *pure*
  rule services and recomputes, from the returned values:

  - entity-match precision / recall / false positives, and the
    **false-merge rate** (negative pairs that were proposed anyway), which is
    gated at exactly zero - a false merge silently fuses two people;
  - timeline parse precision / recall, **timestamp correctness** (the UTC
    instant, zone, granularity and the documented naive->UTC assumption all
    match), and **locator validity** (every proposal cites a field that is
    actually present in the source record);
  - contradiction field-classifier accuracy, anchored-comparison precision /
    recall, and the **entity-anchor false-positive rate** (two different
    transactions of one account must never yield a contradiction), gated at
    zero.

  An **anti-vacuous** gate fails the run when a feature reports no findings for
  every case: a detector that never proposes anything is not "100% precise",
  it is broken.

* **Live end-to-end** (requires the running stack + local model) - ingests
  synthetic JSON evidence through the real API, runs all three features, then
  independently re-reads PostgreSQL to verify: full provenance on every
  proposal, that approving an entity candidate adds audited additive aliases
  and **never merges**, that committing an approved timeline proposal yields
  exactly one event (idempotent), and that resolving a contradiction appends a
  child artifact without rewriting the candidate. Per-feature job latency is
  measured.

Model-quality numbers are reported, never gated; deterministic safety
properties are gated. Everything the harness creates (one synthetic case, its
evidence and objects) is deleted before exit.

Run via the entry point (loads the environment, checks both servers):

    ./scripts/ai/eval_phase3.sh

or directly from ``backend/``:

    .venv/bin/python -m scripts.eval_phase3 --report /tmp/p3.json
    .venv/bin/python -m scripts.eval_phase3 --skip-live   # golden metrics only
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
from app.services.contradiction_detection import (
    RecordFacts as ContradictionRecord,
)
from app.services.contradiction_detection import (
    classify_field,
    generate_conflicts,
)
from app.services.entity_matching import EntityFacts, build_candidate_pairs
from app.services.normalization import blocking_key
from app.services.timeline_reconstruction import drafts_from_record, parse_timestamp

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "evidence_intelligence"
RESOLUTION_FIXTURE = FIXTURE_DIR / "entity_resolution_checks.json"
TIMELINE_FIXTURE = FIXTURE_DIR / "timeline_checks.json"
CONTRADICTION_FIXTURE = FIXTURE_DIR / "contradiction_checks.json"
LIVE_FIXTURE = FIXTURE_DIR / "phase3_live_checks.json"
REPORT_DEFAULT = REPO_ROOT / "ai_runtime" / "eval_phase3_report.json"
API_BASE_DEFAULT = "http://localhost:8000/api/v1"

REQUEST_TIMEOUT_SECONDS = 240.0
JOB_POLL_TIMEOUT_SECONDS = 420.0
TERMINAL_JOB_STATES = {"succeeded", "partial", "failed", "canceled"}

# Feature path -> (submit path segment, job feature name, artifact kind).
FEATURES: dict[str, tuple[str, str, str]] = {
    "resolution": ("entity-resolution", "entity_resolution", "entity_resolution"),
    "reconstruction": (
        "timeline-reconstruction",
        "timeline",
        "timeline_proposal",
    ),
    "contradiction": (
        "contradiction-detection",
        "contradiction",
        "contradiction",
    ),
}

LIMITATIONS = [
    "Golden sets are small and hand-authored to exercise every decision class; "
    "precision/recall are measured on these n cases only, not on field data.",
    "Golden metrics replay the pure deterministic rules, so they do not measure "
    "the local model's advisory verdicts; those are advisory, always flagged "
    "ai_unverified, and reported (never gated) in the live section.",
    "The live section uses synthetic JSON evidence whose entity mentions come "
    "from the deterministic field-alias table, so entity resolution there is "
    "reproducible; LLM-only paths are covered by the API suite and golden sets.",
    "Timeline locator validity is verified against the cited source record's "
    "raw_data (the honest comparison point); broader world-knowledge accuracy "
    "is out of scope.",
]


def _rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{numerator}/{denominator} ({numerator / denominator:.0%})"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class Phase3EvalRunner:
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

    # -- deterministic golden-fixture metrics (no stack) --------------------

    @staticmethod
    def _entity_facts(entity: dict[str, Any]) -> EntityFacts:
        canonical = entity["canonical_value"]
        entity_type = entity["entity_type"]
        return EntityFacts(
            id=entity["id"],
            entity_type=entity_type,
            canonical_value=canonical,
            display_value=entity.get("display_value", canonical),
            blocking_key=blocking_key(entity_type, canonical),
            status="active",
            signals=tuple(entity.get("signals", ())),
            source_record_ids=tuple(entity.get("source_record_ids", ())),
        )

    def _eval_resolution_golden(self) -> dict[str, Any]:
        fixture = _load(RESOLUTION_FIXTURE)
        thresholds = fixture.get("thresholds", {})
        auto = float(thresholds.get("auto", 92.0))
        review = float(thresholds.get("review", 78.0))

        tp = fp = fn = tn = 0
        attr_total = attr_ok = 0
        per_case: list[dict[str, Any]] = []
        for case in fixture["cases"]:
            entities = [self._entity_facts(e) for e in case["entities"]]
            aliases = {k: tuple(v) for k, v in case.get("aliases", {}).items()}
            pairs, _counts = build_candidate_pairs(
                entities,
                aliases,
                auto_threshold=auto,
                review_threshold=review,
                max_per_bucket=25,
                max_pairs=150,
            )
            key = frozenset(case["pair"])
            match = next(
                (
                    p
                    for p in pairs
                    if frozenset((p.entity_a.id, p.entity_b.id)) == key
                ),
                None,
            )
            expect = case["expect"]
            expected = bool(expect["proposed"])
            actual = match is not None
            if expected and actual:
                tp += 1
            elif not expected and actual:
                fp += 1  # a false merge candidate
            elif expected and not actual:
                fn += 1
            else:
                tn += 1

            attrs_match = True
            if expected and actual and match is not None:
                attr_total += 1
                if "method" in expect and match.method != expect["method"]:
                    attrs_match = False
                if "score_band" in expect and match.score_band != expect["score_band"]:
                    attrs_match = False
                if "validation_codes" in expect and sorted(
                    match.validation_codes
                ) != sorted(expect["validation_codes"]):
                    attrs_match = False
                if attrs_match:
                    attr_ok += 1
            per_case.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "expected_proposed": expected,
                    "actual_proposed": actual,
                    "attributes_match": attrs_match if (expected and actual) else None,
                }
            )

        proposed = tp + fp
        expected_positives = tp + fn
        return {
            "n_cases": len(fixture["cases"]),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": tn,
            "precision": _rate(tp, proposed),
            "recall": _rate(tp, expected_positives),
            "false_merge_rate": _rate(fp, fp + tn),
            "false_merges": fp,
            "attribute_agreement": _rate(attr_ok, attr_total),
            "per_case": per_case,
        }

    def _eval_timeline_golden(self) -> dict[str, Any]:
        fixture = _load(TIMELINE_FIXTURE)

        # -- parse cases: precision/recall + exact timestamp correctness ----
        tp = fp = fn = tn = 0
        correct = 0
        parse_mismatches: list[dict[str, Any]] = []
        for case in fixture["parse_cases"]:
            parsed = parse_timestamp(case["value"])
            expect = case["expect"]
            expected = bool(expect["parseable"])
            actual = parsed is not None
            if expected and actual:
                tp += 1
            elif not expected and actual:
                fp += 1  # an invented timestamp
            elif expected and not actual:
                fn += 1
            else:
                tn += 1
            if expected and actual and parsed is not None:
                matches = (
                    parsed.occurred_at is not None
                    and parsed.occurred_at.isoformat() == expect["utc"]
                    and parsed.tz == expect["tz"]
                    and parsed.granularity == expect["granularity"]
                    and parsed.tz_assumed == expect["tz_assumed"]
                )
                if matches:
                    correct += 1
                else:
                    parse_mismatches.append(
                        {
                            "id": case["id"],
                            "value": case["value"],
                            "got_utc": (
                                parsed.occurred_at.isoformat()
                                if parsed.occurred_at
                                else None
                            ),
                            "expected_utc": expect["utc"],
                            "got_tz": parsed.tz,
                            "expected_tz": expect["tz"],
                            "got_granularity": parsed.granularity,
                            "expected_granularity": expect["granularity"],
                            "got_tz_assumed": parsed.tz_assumed,
                            "expected_tz_assumed": expect["tz_assumed"],
                        }
                    )

        # -- record cases: draft/missing/ambiguous counts + locator validity -
        record_ok = 0
        locator_violations: list[dict[str, Any]] = []
        record_mismatches: list[dict[str, Any]] = []
        for case in fixture["record_cases"]:
            drafts, _skipped = drafts_from_record(
                record_id="r1",
                evidence_file_id="ev1",
                record_no=1,
                raw_data=case["raw_data"],
                filename="golden.json",
            )
            expect = case["expect"]
            missing = sum(1 for d in drafts if d.missing_timestamp)
            ambiguous = sum(1 for d in drafts if d.tz_assumed)
            counts_match = (
                len(drafts) == expect["drafts"]
                and missing == expect["missing"]
                and ambiguous == expect["ambiguous"]
            )
            if counts_match:
                record_ok += 1
            else:
                record_mismatches.append(
                    {
                        "id": case["id"],
                        "expected": expect,
                        "got": {
                            "drafts": len(drafts),
                            "missing": missing,
                            "ambiguous": ambiguous,
                        },
                    }
                )
            # Locator validity: every proposal must cite a field that is
            # genuinely present in the source record it came from.
            for draft in drafts:
                if draft.locator_field not in case["raw_data"]:
                    locator_violations.append(
                        {
                            "case": case["id"],
                            "field": draft.locator_field,
                            "reason": "cited field absent from source record",
                        }
                    )
                if draft.record_no != 1:
                    locator_violations.append(
                        {
                            "case": case["id"],
                            "field": draft.locator_field,
                            "reason": "cited record_no does not match the record",
                        }
                    )

        parseable = tp + fn
        record_total = len(fixture["record_cases"])
        return {
            "n_parse_cases": len(fixture["parse_cases"]),
            "parse_precision": _rate(tp, tp + fp),
            "parse_recall": _rate(tp, parseable),
            "timestamp_correctness": _rate(correct, parseable),
            "invented_timestamps": fp,
            "parse_mismatches": parse_mismatches,
            "n_record_cases": record_total,
            "record_case_correctness": _rate(record_ok, record_total),
            "record_mismatches": record_mismatches,
            "locator_violations": locator_violations,
        }

    def _eval_contradiction_golden(self) -> dict[str, Any]:
        fixture = _load(CONTRADICTION_FIXTURE)
        settings = self.settings

        # -- classifier accuracy ---------------------------------------------
        clf_total = clf_ok = 0
        clf_mismatches: list[dict[str, Any]] = []
        for case in fixture["classify_cases"]:
            clf_total += 1
            got = classify_field(case["field"], case["value"])
            if got == case["expect"]:
                clf_ok += 1
            else:
                clf_mismatches.append(
                    {
                        "field": case["field"],
                        "value": case["value"],
                        "expected": case["expect"],
                        "got": got,
                    }
                )

        # -- anchored comparison precision/recall ----------------------------
        cat_tp = cat_fp = cat_fn = 0
        entity_anchor_fp = 0
        priority_ok = priority_total = 0
        per_case: list[dict[str, Any]] = []
        for case in fixture["pair_cases"]:
            records = [
                ContradictionRecord(
                    id=r["id"],
                    evidence_file_id=r["evidence_file_id"],
                    record_no=r["record_no"],
                    raw_data=r["raw_data"],
                )
                for r in case["records"]
            ]
            conflicts, _counts = generate_conflicts(
                records,
                max_records_per_anchor=settings.CONTRADICTION_MAX_RECORDS_PER_ANCHOR,
                max_pair_evals=settings.CONTRADICTION_MAX_PAIR_EVALS,
            )
            got_categories = sorted({conflict.category for conflict, _, _ in conflicts})
            expect = case["expect"]
            expected_categories = sorted(expect.get("categories", []))

            got_set = set(got_categories)
            want_set = set(expected_categories)
            cat_tp += len(got_set & want_set)
            cat_fp += len(got_set - want_set)
            cat_fn += len(want_set - got_set)

            is_entity_anchor = any(
                "account_no" in r["raw_data"] for r in case["records"]
            )
            false_positive_here = bool(got_set - want_set)
            if is_entity_anchor and false_positive_here:
                entity_anchor_fp += 1

            priority_match: bool | None = None
            priority_of = expect.get("priority_of")
            if priority_of:
                priority_total += 1
                by_category = {c.category: c.priority for c, _, _ in conflicts}
                priority_match = all(
                    by_category.get(cat) == pri for cat, pri in priority_of.items()
                )
                if priority_match:
                    priority_ok += 1

            alternatives_ok: bool | None = None
            if "alternative_any" in expect:
                needle = expect["alternative_any"]
                alternatives_ok = any(
                    any(needle in alt for alt in conflict.alternatives)
                    for conflict, _, _ in conflicts
                )
            missing_ok: bool | None = None
            if "missing_any" in expect:
                needle = expect["missing_any"]
                missing_ok = any(
                    any(needle in m for m in conflict.missing)
                    for conflict, _, _ in conflicts
                )
            count_ok: bool | None = None
            if "conflict_count" in expect:
                count_ok = len(conflicts) == expect["conflict_count"]

            per_case.append(
                {
                    "id": case["id"],
                    "expected_categories": expected_categories,
                    "actual_categories": got_categories,
                    "priority_match": priority_match,
                    "alternatives_match": alternatives_ok,
                    "missing_match": missing_ok,
                    "conflict_count_match": count_ok,
                }
            )

        expected_positives = cat_tp + cat_fn
        predicted_positives = cat_tp + cat_fp
        return {
            "n_classify_cases": clf_total,
            "classifier_accuracy": _rate(clf_ok, clf_total),
            "classifier_mismatches": clf_mismatches,
            "n_pair_cases": len(fixture["pair_cases"]),
            "category_precision": _rate(cat_tp, predicted_positives),
            "category_recall": _rate(cat_tp, expected_positives),
            "category_false_positives": cat_fp,
            "entity_anchor_false_positives": entity_anchor_fp,
            "priority_agreement": _rate(priority_ok, priority_total),
            "per_case": per_case,
        }

    def _golden_section(self) -> dict[str, Any]:
        print("  golden: entity resolution", flush=True)
        resolution = self._eval_resolution_golden()
        print("  golden: timeline reconstruction", flush=True)
        timeline = self._eval_timeline_golden()
        print("  golden: contradiction detection", flush=True)
        contradiction = self._eval_contradiction_golden()
        return {
            "entity_resolution": resolution,
            "timeline_reconstruction": timeline,
            "contradiction_detection": contradiction,
        }

    # -- live end-to-end section ---------------------------------------------

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

    async def _upload_json(self, name: str, records: list[dict[str, Any]]) -> str:
        payload = json.dumps(records).encode()
        response = await self.api.post(
            f"/cases/{self.case_id}/evidence",
            files={"file": (name, payload, "application/json")},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()["id"]

    async def _ingest(self, evidence_id: str) -> dict[str, Any]:
        response = await self.api.post(
            f"/cases/{self.case_id}/ingest",
            json={"evidence_file_id": evidence_id},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    async def _submit_feature(self, path_segment: str) -> dict[str, Any]:
        response = await self.api.post(
            f"/cases/{self.case_id}/evidence-intelligence/{path_segment}",
            json={},
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

    async def _run_feature(self, key: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        path_segment, job_feature, kind = FEATURES[key]
        submitted = await self._submit_feature(path_segment)
        started = time.monotonic()
        job = await self._poll_job(submitted["job"]["id"], feature=job_feature)
        latency_ms = int((time.monotonic() - started) * 1000)
        artifacts = await self._artifacts(kind)
        return (
            {
                "status": job["status"],
                "latency_ms": latency_ms,
                "kind": kind,
                "summary": job.get("result_summary"),
            },
            artifacts,
        )

    @staticmethod
    def _provenance_complete(artifact: dict[str, Any]) -> list[str]:
        """Missing provenance elements on one proposal (empty == complete)."""
        problems: list[str] = []
        if not artifact.get("analysis_job_id"):
            problems.append("missing analysis_job_id")
        if not artifact.get("content_hash"):
            problems.append("missing content_hash")
        if not artifact.get("parser_version"):
            problems.append("missing parser_version")
        if artifact.get("source_locator") is None:
            problems.append("missing source_locator")
        return problems

    async def _live_resolution(
        self, artifacts: list[dict[str, Any]], expect: dict[str, Any]
    ) -> dict[str, Any]:
        candidates = [
            a for a in artifacts if (a.get("payload") or {}).get("type") == "entity_candidate"
        ]
        if not candidates:
            return {"candidates": 0, "note": "no entity candidate proposed"}
        candidate = candidates[0]
        payload = candidate["payload"]
        band = payload.get("score_band")

        # Independently verify both cited entities exist and are unmerged.
        locator = candidate.get("source_locator") or {}
        entity_ids = [locator.get("entity_a"), locator.get("entity_b")]
        factory = self.database.session_factory()
        statuses: list[str] = []
        merged_flags: list[bool] = []
        async with factory() as session:
            from app.models import Entity

            for eid in entity_ids:
                if not eid:
                    continue
                row = await session.get(Entity, uuid.UUID(str(eid)))
                assert row is not None, f"cited entity {eid} missing from the database"
                statuses.append(row.status)
                merged_flags.append(bool(row.merged_into_id))

        # Approve via the real review route, then re-read: aliases must appear
        # and the entities must NOT be merged (false-merge rate zero).
        approve = await self.api.post(
            f"/cases/{self.case_id}/evidence-intelligence/artifacts/{candidate['id']}/review",
            json={"decision": "approved", "note": "eval harness cross-check"},
            headers=self._headers(),
        )
        approve.raise_for_status()

        resolution_alias_count = 0
        pre_existing_alias_count = 0
        still_active = True
        still_unmerged = True
        async with factory() as session:
            from app.models import Entity, EntityAlias

            rows = await session.execute(
                EntityAlias.__table__.select().where(
                    EntityAlias.entity_id.in_([str(e) for e in entity_ids if e])
                )
            )
            for alias_row in rows.all():
                # Only alias_type="resolution" cross-aliases are added by approval;
                # ingest may already have recorded self-aliases of type "value".
                if alias_row.alias_type == "resolution":
                    resolution_alias_count += 1
                else:
                    pre_existing_alias_count += 1
            for eid in entity_ids:
                if not eid:
                    continue
                row = await session.get(Entity, uuid.UUID(str(eid)))
                assert row is not None
                if row.status != "active":
                    still_active = False
                if row.merged_into_id is not None:
                    still_unmerged = False

        return {
            "candidates": len(candidates),
            "score_band": band,
            "expected_score_band": expect.get("resolution_score_band"),
            "band_matches": band == expect.get("resolution_score_band"),
            "origin": candidate.get("origin"),
            "validation_status": candidate.get("validation_status"),
            "pre_approval_entities_active": all(s == "active" for s in statuses),
            "pre_approval_entities_unmerged": not any(merged_flags),
            "aliases_added": resolution_alias_count,
            "pre_existing_aliases": pre_existing_alias_count,
            "expected_aliases": expect.get("resolution_aliases_on_approval"),
            "entities_still_active_after_approval": still_active,
            "entities_unmerged_after_approval": still_unmerged,
        }

    async def _live_reconstruction(
        self, artifacts: list[dict[str, Any]], expect: dict[str, Any]
    ) -> dict[str, Any]:
        proposals = [
            a for a in artifacts if (a.get("payload") or {}).get("type") == "timeline_proposal"
        ]
        if not proposals:
            return {"proposals": 0, "note": "no timeline proposal generated"}

        granularities = sorted(
            {
                str((a.get("payload") or {}).get("time_granularity"))
                for a in proposals
            }
        )
        ambiguous = sum(
            1 for a in proposals if (a.get("payload") or {}).get("tz_assumed")
        )

        # Locator validity: re-read each cited source record and confirm the
        # cited field is genuinely present.
        factory = self.database.session_factory()
        locator_violations: list[dict[str, Any]] = []
        async with factory() as session:
            from app.models import SourceRecord

            for proposal in proposals:
                locator = proposal.get("source_locator") or {}
                record_id = proposal.get("source_record_id")
                field = locator.get("field")
                record_no = locator.get("record_no")
                if not record_id or not field:
                    locator_violations.append(
                        {"artifact": proposal["id"], "reason": "incomplete locator"}
                    )
                    continue
                record = await session.get(SourceRecord, uuid.UUID(str(record_id)))
                if record is None:
                    locator_violations.append(
                        {"artifact": proposal["id"], "reason": "cited record missing"}
                    )
                    continue
                if field not in dict(record.raw_data):
                    locator_violations.append(
                        {
                            "artifact": proposal["id"],
                            "reason": "cited field absent from cited record",
                        }
                    )
                if record_no is not None and int(record.record_no) != int(record_no):
                    locator_violations.append(
                        {
                            "artifact": proposal["id"],
                            "reason": "cited record_no does not match the record",
                        }
                    )

        # Commit the first approved proposal and confirm idempotency.
        target = proposals[0]
        approve = await self.api.post(
            f"/cases/{self.case_id}/evidence-intelligence/artifacts/{target['id']}/review",
            json={"decision": "approved", "note": "eval harness commit"},
            headers=self._headers(),
        )
        approve.raise_for_status()
        first_commit = await self.api.post(
            f"/cases/{self.case_id}/evidence-intelligence/timeline-proposals/{target['id']}/commit",
            headers=self._headers(),
        )
        first_commit.raise_for_status()
        first_body = first_commit.json()
        second_commit = await self.api.post(
            f"/cases/{self.case_id}/evidence-intelligence/timeline-proposals/{target['id']}/commit",
            headers=self._headers(),
        )
        second_commit.raise_for_status()
        second_body = second_commit.json()

        return {
            "proposals": len(proposals),
            "granularities": granularities,
            "expected_granularities": expect.get("timeline_granularities"),
            "granularities_match": set(granularities)
            == set(expect.get("timeline_granularities", [])),
            "ambiguous_tz": ambiguous,
            "ambiguous_tz_meets_min": ambiguous >= expect.get("timeline_ambiguous_tz_min", 0),
            "locator_violations": locator_violations,
            "first_commit_duplicate": first_body.get("duplicate"),
            "second_commit_duplicate": second_body.get("duplicate"),
            "commit_idempotent": (
                first_body.get("duplicate") is False
                and second_body.get("duplicate") is True
                and first_body["event"]["id"] == second_body["event"]["id"]
            ),
        }

    async def _live_contradiction(
        self, artifacts: list[dict[str, Any]], expect: dict[str, Any]
    ) -> dict[str, Any]:
        candidates = [
            a
            for a in artifacts
            if (a.get("payload") or {}).get("type") == "contradiction"
        ]
        if not candidates:
            return {"candidates": 0, "note": "no contradiction candidate generated"}
        # The semantic category depends on a model verdict and may or may not
        # appear; anchor every exact assertion on a deterministic category so
        # the advisory extra never skews priority/anchor checks.
        expected_categories = sorted(expect.get("contradiction_categories", []))
        candidate = next(
            (
                c
                for c in candidates
                if (c.get("payload") or {}).get("category") in expected_categories
            ),
            candidates[0],
        )
        payload = candidate["payload"]
        category_values = {(c.get("payload") or {}).get("category") for c in candidates}
        categories = sorted(c for c in category_values if c is not None)

        # Resolve via the real route and confirm a child artifact is appended
        # while the candidate itself is never rewritten.
        before_hash = candidate.get("content_hash")
        resolve = await self.api.post(
            f"/cases/{self.case_id}/evidence-intelligence/contradictions/{candidate['id']}/resolve",
            json={"state": "explained", "note": "eval harness resolution"},
            headers=self._headers(),
        )
        resolve.raise_for_status()
        child = resolve.json()

        after = await self.api.get(
            f"/cases/{self.case_id}/evidence-intelligence/artifacts",
            params={"kind": "contradiction"},
            headers=self._headers(),
        )
        after.raise_for_status()
        still_present = any(
            a["id"] == candidate["id"] for a in after.json()["items"]
        )
        after_row = next(
            (a for a in after.json()["items"] if a["id"] == candidate["id"]), None
        )
        candidate_unrewritten = (
            after_row is not None and after_row.get("content_hash") == before_hash
        )

        return {
            "candidates": len(candidates),
            "categories": categories,
            "expected_categories": expect.get("contradiction_categories"),
            "categories_match": all(c in categories for c in expected_categories),
            "categories_exact": categories == expected_categories,
            "priority": payload.get("priority"),
            "expected_priority": expect.get("contradiction_priority"),
            "priority_matches": payload.get("priority") == expect.get("contradiction_priority"),
            "alternatives_present": len(payload.get("alternatives") or []) >= 1,
            "child_kind": child.get("kind"),
            "child_status": child.get("status"),
            "child_appended": (
                child.get("kind") == "contradiction" and child.get("status") == "recorded"
            ),
            "candidate_still_present": still_present,
            "candidate_unrewritten": candidate_unrewritten,
        }

    async def _live_section(self) -> dict[str, Any]:
        fixture = _load(LIVE_FIXTURE)
        section: dict[str, Any] = {"evidence": []}
        resolution_expect: dict[str, Any] = {}
        reconstruction_expect: dict[str, Any] = {}
        contradiction_expect: dict[str, Any] = {}

        for item in fixture["evidence"]:
            print(f"  live: ingest {item['id']}", flush=True)
            evidence_id = await self._upload_json(item["filename"], item["records"])
            ingest = await self._ingest(evidence_id)
            section["evidence"].append(
                {
                    "id": item["id"],
                    "ingest_status": (ingest.get("job") or {}).get("status"),
                }
            )
            resolution_expect = item["expect"]
            reconstruction_expect = item["expect"]
            contradiction_expect = item["expect"]

        print("  live: entity resolution", flush=True)
        res_summary, res_artifacts = await self._run_feature("resolution")
        section["resolution"] = {
            **res_summary,
            **await self._live_resolution(res_artifacts, resolution_expect),
        }

        print("  live: timeline reconstruction", flush=True)
        recon_summary, recon_artifacts = await self._run_feature("reconstruction")
        section["reconstruction"] = {
            **recon_summary,
            **await self._live_reconstruction(recon_artifacts, reconstruction_expect),
        }

        print("  live: contradiction detection", flush=True)
        contra_summary, contra_artifacts = await self._run_feature("contradiction")
        section["contradiction"] = {
            **contra_summary,
            **await self._live_contradiction(contra_artifacts, contradiction_expect),
        }

        # Provenance completeness across every proposal of every feature.
        violations: list[dict[str, Any]] = []
        for kind, artifacts in (
            ("entity_resolution", res_artifacts),
            ("timeline_proposal", recon_artifacts),
            ("contradiction", contra_artifacts),
        ):
            for artifact in artifacts:
                for problem in self._provenance_complete(artifact):
                    violations.append(
                        {"kind": kind, "artifact": artifact["id"], "problem": problem}
                    )
        section["provenance_violations"] = violations
        return section

    # -- lifecycle ------------------------------------------------------------

    async def run(self) -> int:
        try:
            await self.database.ping()
        except Exception as exc:  # noqa: BLE001 - setup failure
            print(f"database setup failure: {exc}", file=sys.stderr)
            return 2

        # The deterministic golden section never needs the stack's HTTP layer.
        self.report["golden"] = self._golden_section()

        if not self.args.skip_live:
            try:
                await self.login(self.args.username, self.args.password)
            except Exception as exc:  # noqa: BLE001 - setup failure
                print(f"login failure: {exc}", file=sys.stderr)
                return 2
            if not await self.ai_ready():
                print(
                    "AI runtime is not ready (see /api/v1/ai/status); start the "
                    "model server per docs/ai/LOCAL_MODEL_SETUP.md, or pass "
                    "--skip-live to run golden metrics only.",
                    file=sys.stderr,
                )
                return 2
            created = await self.api.post(
                "/cases",
                json={
                    "title": "phase-3 intelligence eval (synthetic)",
                    "description": "created and deleted by scripts/eval_phase3.py",
                },
                headers=self._headers(),
            )
            created.raise_for_status()
            self.case_id = created.json()["id"]
            print(f"synthetic case {self.case_id}", flush=True)
            try:
                self.report["live"] = await self._live_section()
            finally:
                await self._cleanup_case()
                await self.api.aclose()
        else:
            await self.api.aclose()
            await self.database.close()
            self.storage.close()

        self.gates = self._compute_gates()
        self.report["gates"] = self.gates
        self.report["limitations"] = LIMITATIONS

        self.args.report.parent.mkdir(parents=True, exist_ok=True)
        self.args.report.write_text(json.dumps(self.report, indent=2), encoding="utf-8")
        print(json.dumps(self.report, indent=2), flush=True)
        print(f"report written to {self.args.report}", flush=True)
        return 0 if all(self.gates.values()) else 1

    def _compute_gates(self) -> dict[str, bool]:
        golden = self.report["golden"]
        res = golden["entity_resolution"]
        timeline = golden["timeline_reconstruction"]
        contra = golden["contradiction_detection"]
        gates: dict[str, bool] = {
            # A detector that never proposes anything must not pass as "precise".
            "resolution_not_vacuous": res["true_positives"] > 0,
            "resolution_zero_false_merges": res["false_merges"] == 0,
            "resolution_attributes_agree": res["false_positives"] == 0
            and res["attribute_agreement"].startswith(
                f"{res['true_positives']}/{res['true_positives']}",
            ),
            "timeline_not_vacuous": timeline["timestamp_correctness"] != "n/a"
            and not timeline["timestamp_correctness"].startswith("0/"),
            "timeline_zero_invented_timestamps": timeline["invented_timestamps"] == 0,
            "timeline_timestamps_correct": timeline["timestamp_correctness"].endswith("(100%)"),
            "timeline_locators_valid": not timeline["locator_violations"],
            "timeline_record_cases_correct": timeline["record_case_correctness"].endswith(
                "(100%)"
            ),
            "contradiction_classifier_exact": contra["classifier_accuracy"].endswith("(100%)"),
            "contradiction_not_vacuous": contra["category_recall"] != "n/a"
            and not contra["category_recall"].startswith("0/"),
            "contradiction_entity_anchor_zero_false_positives": (
                contra["entity_anchor_false_positives"] == 0
            ),
        }
        if "live" in self.report:
            live = self.report["live"]
            gates["live_provenance_complete"] = not live.get("provenance_violations")
            resolution = live.get("resolution", {})
            gates["live_resolution_no_merge"] = (
                resolution.get("entities_unmerged_after_approval") is True
                and resolution.get("entities_still_active_after_approval") is True
                and resolution.get("aliases_added")
                == resolution.get("expected_aliases")
            )
            reconstruction = live.get("reconstruction", {})
            gates["live_reconstruction_locators_valid"] = not reconstruction.get(
                "locator_violations"
            )
            gates["live_reconstruction_commit_idempotent"] = (
                reconstruction.get("commit_idempotent") is True
            )
            contradiction = live.get("contradiction", {})
            gates["live_contradiction_child_appended"] = (
                contradiction.get("child_appended") is True
                and contradiction.get("candidate_unrewritten") is True
            )
        return gates

    async def _cleanup_case(self) -> None:
        """Remove everything this run created: MinIO objects, then rows."""
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
        finally:
            await self.database.close()
            self.storage.close()
        self.report["cleanup"] = outcome


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    parser.add_argument("--api-base", default=API_BASE_DEFAULT)
    parser.add_argument("--username", default="investigator")
    parser.add_argument("--password", default="investigator-dev-password")
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="run only the deterministic golden-fixture metrics (no stack needed)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(Phase3EvalRunner(_parse_args(argv)).run())


if __name__ == "__main__":
    sys.exit(main())
