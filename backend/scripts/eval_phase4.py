"""Live + golden-fixture evaluation harness for phase 4 (financial flow + cross-case).

Extends the Phase-1/2/3 harness conventions (``scripts/eval_model.py``,
``scripts/eval_evidence.py``, ``scripts/eval_phase3.py``: real HTTP, real auth,
real local inference, independent verification against PostgreSQL - never the
server's self-report) to the two phase-4 features.

The harness has two independent sections:

* **Deterministic golden-fixture metrics** (no stack required) - replays the
  frozen golden sets (``financial_flow_checks.json``,
  ``cross_case_checks.json``) through the *pure* rule services and recomputes,
  from the returned values:

  - financial aggregation exactness (counts, per-currency bucket totals with
    exact Decimal arithmetic, per-status separation, per-account / per-bank
    splits), pattern precision/recall including honest ``not_evaluable`` and
    ``not_fired`` reporting, structure-network exactness, and **path
    correctness** (the deterministic trace returns exactly the documented
    bounded maximal simple paths, never a transfer);
  - the documented blockers are *reported*, not papered over: amounts without
    currency stay in a ``currency_unknown`` bucket that is never labelled,
    direction-dependent metrics are ``not_computable_no_direction``,
    timestamp-dependent rules stay ``not_evaluable``, and an unparseable
    amount is counted and dropped from totals rather than coerced;
  - cross-case candidate precision/recall and **classification exactness**
    (exact vs normalized identifier, reviewed alias, name-similarity-only
    which must never be reviewable), conflict-flag exactness, evidence-hash
    candidate construction, per-side provenance, candidate/indicator/support
    bounds, and the guarantee that single-case groups never emit candidates.

  An **anti-vacuous** gate fails the run when a feature reports no findings:
  a detector that never proposes anything is not "precise", it is broken.

* **Live end-to-end** (requires the running stack + local model) - ingests
  synthetic JSON evidence through the real API, runs both features, then
  independently re-reads PostgreSQL to verify the artifact's aggregates match
  a fresh recomputation, probes the read-only trace (association path,
  transfer -> ``insufficient_data``, unknown account -> ``not_found``),
  exercises the cancellation branch on a real job, runs cross-case discovery
  over two investigator-owned cases plus one admin-owned case to verify
  read-time omission and no-leak refusals, approves a candidate and verifies
  the recorded child artifact, and probes anonymous / VIEWER / scope-denied
  access. Per-feature job latency is measured.

Deterministic safety properties are gated; model-dependent explain outcomes
are reported, never gated. Everything the harness creates (four synthetic
cases, their evidence and objects, one temporary VIEWER account) is deleted
or suspended before exit.

Run via the entry point (loads the environment, checks both servers):

    ./scripts/ai/eval_phase4.sh

or directly from ``backend/``:

    .venv/bin/python -m scripts.eval_phase4 --report /tmp/p4.json
    .venv/bin/python -m scripts.eval_phase4 --skip-live   # golden metrics only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from app.core.config import get_settings
from app.db.postgres import Database
from app.db.storage import Storage
from app.models import Entity, EntityAlias, EvidenceFile, SourceRecord, Victim
from app.services.cross_case import (
    _scope_hash,
    build_candidates,
    collect_case_indicators,
)
from app.services.financial_flow import (
    _trace_paths,
    aggregate_facts,
    build_payload,
    build_structure_network,
    evaluate_patterns,
    extract_facts,
    extract_victim_financials,
)
from app.services.normalization import blocking_key

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "evidence_intelligence"
FLOW_FIXTURE = FIXTURE_DIR / "financial_flow_checks.json"
CROSS_FIXTURE = FIXTURE_DIR / "cross_case_checks.json"
LIVE_FIXTURE = FIXTURE_DIR / "phase4_live_checks.json"
REPORT_DEFAULT = REPO_ROOT / "ai_runtime" / "eval_phase4_report.json"
API_BASE_DEFAULT = "http://localhost:8000/api/v1"

REQUEST_TIMEOUT_SECONDS = 240.0
JOB_POLL_TIMEOUT_SECONDS = 420.0
TERMINAL_JOB_STATES = {"succeeded", "partial", "failed", "canceled"}
INGEST_TERMINAL_STATES = {"completed", "failed", "partial"}

LIMITATIONS = [
    "Golden sets are small, synthetic and hand-computed (documented n= inside "
    "each fixture); exactness and precision/recall are measured on these "
    "records only, not on field data.",
    "The financial golden fixture mirrors the real corpus's missing inputs on "
    "purpose: no parseable transaction timestamps and no payer/direction key, "
    "so time-windowed rules stay not_evaluable and direction-dependent "
    "metrics stay not_computable - never approximated.",
    "Amounts are unlabelled currency unless a currency field or '$' hint "
    "exists; totals are bucketed per currency value and a null bucket is "
    "flagged currency_unknown, never labelled with a default currency.",
    "Victim loss matching compares exact Decimal string forms; a float "
    "victim column that happens to share a string form with a transaction "
    "amount matches only by that coincidence (documented float_source "
    "limitation, not a claim of identity).",
    "The golden cross-case section replays pure extraction and candidate "
    "construction; authorization, scope rechecks and read-time omission are "
    "gated in the live section and covered by the API test suite.",
    "The cross-case score is a 0-100 signal-strength band within one rules "
    "version; it is not a probability, and every candidate stays "
    "pending_review - approval records an audited child artifact and never "
    "merges cases or writes to the graph.",
    "Live explain outcomes depend on the local model's reply passing "
    "deterministic citation validation (200 flagged ai_unverified, or 422 "
    "AI_EXPLANATION_INVALID); both paths are correct behavior, so the "
    "outcome is reported and both are covered by API tests, never gated.",
]


def _rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{numerator}/{denominator} ({numerator / denominator:.0%})"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonable(value: Any) -> Any:
    """Recursive normalizer: Decimal/UUID/datetime -> str, tuple -> list."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _record_no(record_id: str) -> int:
    """Golden fixtures assign record n the id ending in hex(n); decode it."""
    return int(uuid.UUID(str(record_id)).hex[-3:], 16)


def _nos(ids: Any) -> list[int]:
    return sorted(_record_no(item) for item in (ids or []))


class Phase4EvalRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.api = httpx.AsyncClient(base_url=args.api_base, timeout=REQUEST_TIMEOUT_SECONDS)
        self.token: str | None = None
        self.admin_token: str | None = None
        self.settings = get_settings()
        self.database = Database(self.settings)
        self.storage = Storage(self.settings)
        self.case_ids: dict[str, str] = {}  # label -> case uuid (flow/x/y/z)
        self.gates: dict[str, bool] = {}
        self.report: dict[str, Any] = {}
        self._viewer_id: str | None = None

    def _headers(self, token: str | None = None) -> dict[str, str]:
        effective = token if token is not None else self.token
        return {"Authorization": f"Bearer {effective}"} if effective else {}

    # -- deterministic golden-fixture metrics (no stack) --------------------

    @staticmethod
    def _flow_rows(fixture: dict[str, Any]) -> list[SourceRecord]:
        rows: list[SourceRecord] = []
        for n, raw in enumerate(fixture["records"], start=1):
            row = SourceRecord(
                evidence_file_id=fixture["evidence_file_id"],
                record_no=n,
                raw_data=raw,
                status="parsed",
            )
            row.id = uuid.UUID(f"00000000-0000-4000-8000-{n:012x}")
            rows.append(row)
        return rows

    @staticmethod
    def _flow_victims(fixture: dict[str, Any]) -> list[Victim]:
        victims: list[Victim] = []
        for spec in fixture["victims"]:
            row = Victim(
                case_id=fixture["case_id"],
                name=spec["name"],
                reported_amount=spec["reported_amount"],
                currency=spec["currency"],
            )
            row.id = uuid.UUID(spec["id"])
            victims.append(row)
        return victims

    @staticmethod
    def _check_aggregates(
        got: dict[str, Any], expect: dict[str, Any], *, check_ids: bool = True
    ) -> list[str]:
        """Compare aggregates (JSON-normalized) against the golden expectation.

        ``check_ids=False`` (live section only) skips supporting-record-id
        equality: golden record ids are the fixture's deterministic hex scheme
        while live ids are real PostgreSQL uuids, so id-level equality across
        the two is meaningless there - it is gated instead by the live
        independent-recompute check (payload vs fresh recomputation over the
        same rows, identical ids on both sides).
        """
        problems: list[str] = []
        if got.get("counts") != expect["counts"]:
            problems.append(f"counts mismatch: got {got.get('counts')} want {expect['counts']}")

        buckets = {b["currency"]: b for b in got.get("currency_buckets", [])}
        want_keys = sorted(
            (w["currency"] if w["currency"] is not None else "\x00")
            for w in expect["currency_buckets"]
        )
        got_keys = sorted(k if k is not None else "\x00" for k in buckets)
        if got_keys != want_keys:
            problems.append(f"bucket currencies {got_keys} != {want_keys}")
        for want in expect["currency_buckets"]:
            bucket = buckets.get(want["currency"])
            if bucket is None:
                problems.append(f"missing currency bucket {want['currency']!r}")
                continue
            for field in (
                "count",
                "distinct_groups",
                "distinct_amounts",
                "total_records",
                "total_distinct",
                "currency_unknown",
            ):
                if str(bucket.get(field)) != str(want[field]):
                    problems.append(
                        f"bucket {want['currency']!r} {field}: "
                        f"{bucket.get(field)!r} != {want[field]!r}"
                    )
            for field in ("min", "max"):
                if str(bucket.get(field)) != str(want[field]):
                    problems.append(
                        f"bucket {want['currency']!r} {field}: "
                        f"{bucket.get(field)!r} != {want[field]!r}"
                    )
            if len(bucket.get("conflicting_groups") or []) != want["conflicting_groups"]:
                problems.append(f"bucket {want['currency']!r} conflicting_groups mismatch")
            if check_ids and _nos(bucket.get("supporting_source_record_ids")) != want["record_nos"]:
                problems.append(
                    f"bucket {want['currency']!r} supporting ids "
                    f"{_nos(bucket.get('supporting_source_record_ids'))} != {want['record_nos']}"
                )

        def _check_grouped(
            label: str, rows: Any, got_key: str, want_key: str | None = None
        ) -> None:
            fixture_key = want_key or got_key
            by_key = {row[got_key]: row for row in rows}
            want_rows = expect[label]
            if sorted(by_key) != sorted(w[fixture_key] for w in want_rows):
                problems.append(
                    f"{label} keys {sorted(by_key)} != {sorted(w[fixture_key] for w in want_rows)}"
                )
                return
            for want in want_rows:
                row = by_key[want[fixture_key]]
                if row["count"] != want["count"]:
                    problems.append(f"{label} {want[fixture_key]} count mismatch")
                if str(row["total_records"]) != str(want["total_records"]):
                    problems.append(
                        f"{label} {want[fixture_key]} total_records "
                        f"{row['total_records']!r} != {want['total_records']!r}"
                    )
                if (
                    check_ids
                    and _nos(row.get("supporting_source_record_ids")) != want["record_nos"]
                ):
                    problems.append(f"{label} {want[fixture_key]} supporting ids mismatch")

        _check_grouped("by_status", got.get("by_status", []), "status")
        _check_grouped("by_account", got.get("by_account", []), "account_normalized", "account")
        _check_grouped("by_bank", got.get("by_bank", []), "bank")
        if got.get("by_merchant") != expect["by_merchant"]:
            problems.append(f"by_merchant {got.get('by_merchant')!r} != []")

        not_computable = got.get("not_computable", {})
        for key, want in expect["not_computable"].items():
            if not_computable.get(key) != want:
                problems.append(f"not_computable.{key}: {not_computable.get(key)!r} != {want!r}")
        return problems

    @staticmethod
    def _check_patterns(got: dict[str, Any], expect: dict[str, Any]) -> list[str]:
        problems: list[str] = []
        firing = got.get("firing", [])
        want_firing = expect["firing"]
        if len(firing) != len(want_firing):
            problems.append(f"firing count {len(firing)} != {len(want_firing)}")
        for want, row in zip(want_firing, firing, strict=False):
            if row["rule"] != want["rule"]:
                problems.append(f"firing order/rule {row['rule']} != {want['rule']}")
                continue
            evidence = row.get("evidence", {})
            for key, value in want["evidence"].items():
                if key == "transaction_amounts_in_case_count":
                    actual = len(evidence.get("transaction_amounts_in_case") or [])
                    if actual != value:
                        problems.append(
                            f"{row['rule']} transaction_amounts_in_case {actual} != {value}"
                        )
                    continue
                if str(evidence.get(key)) != str(value):
                    problems.append(
                        f"{row['rule']} evidence.{key}: {evidence.get(key)!r} != {value!r}"
                    )
            if _nos(row.get("supporting_source_record_ids")) != want["record_nos"]:
                problems.append(f"{row['rule']} supporting record ids mismatch")
            if "supporting_victim_ids" in want:
                if (row.get("supporting_victim_ids") or []) != want["supporting_victim_ids"]:
                    problems.append(f"{row['rule']} supporting_victim_ids mismatch")
        if got.get("not_fired") != expect["not_fired"]:
            problems.append(f"not_fired {got.get('not_fired')} != {expect['not_fired']}")
        got_not_evaluable = {
            entry["rule"]: entry["reason"] for entry in got.get("not_evaluable", [])
        }
        if got_not_evaluable != expect["not_evaluable"]:
            problems.append(f"not_evaluable {got_not_evaluable} != {expect['not_evaluable']}")
        if got.get("rule_count") != expect["rule_count"]:
            problems.append(f"rule_count {got.get('rule_count')} != {expect['rule_count']}")
        return problems

    @staticmethod
    def _check_network(got: dict[str, Any], expect: dict[str, Any]) -> list[str]:
        problems: list[str] = []
        for field in ("nodes_total", "edges_total", "confirmed_transfer_edges"):
            if got.get(field) != expect[field]:
                problems.append(f"network {field}: {got.get(field)} != {expect[field]}")
        node_ids = sorted(node["id"] for node in got.get("nodes", []))
        if node_ids != sorted(expect["node_ids"]):
            problems.append(f"node ids {node_ids} != {sorted(expect['node_ids'])}")
        edges = {(edge["source"], edge["target"]): edge for edge in got.get("edges", [])}
        want_assoc = {(e["source"], e["target"]): e for e in expect["association_edges"]}
        want_rel = {(e["source"], e["target"]): e for e in expect["relationship_edges"]}
        if set(edges) != set(want_assoc) | set(want_rel):
            problems.append(
                f"edge set mismatch: got {sorted(edges)} "
                f"want {sorted(set(want_assoc) | set(want_rel))}"
            )
        for key, want in want_assoc.items():
            edge = edges.get(key)
            if edge is None:
                continue
            if edge.get("edge_kind") != "association" or edge.get("confidence") != "suspected":
                problems.append(f"association edge {key} mis-typed: {edge}")
            if _nos(edge.get("supporting_source_record_ids")) != want["supporting_record_nos"]:
                problems.append(f"association edge {key} supporting ids mismatch")
        for key, want in want_rel.items():
            edge = edges.get(key)
            if edge is None:
                continue
            if edge.get("edge_kind") != "relationship":
                problems.append(f"relationship edge {key} mis-typed: {edge}")
            if edge.get("relationship_type") != want["relationship_type"]:
                problems.append(f"relationship edge {key} type mismatch")
            if edge.get("schema_confidence") != want["schema_confidence"]:
                problems.append(f"relationship edge {key} schema_confidence mismatch")
        return problems

    @staticmethod
    def _adjacency(got: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
        adjacency: dict[str, dict[str, dict[str, Any]]] = {}
        for edge in got.get("edges", []):
            adjacency.setdefault(edge["source"], {})[edge["target"]] = edge
            adjacency.setdefault(edge["target"], {})[edge["source"]] = edge
        return adjacency

    @classmethod
    def _check_trace(cls, got_network: dict[str, Any], expect: dict[str, Any]) -> list[str]:
        problems: list[str] = []
        adjacency = cls._adjacency(got_network)

        def _run(start: str, max_depth: int) -> tuple[list[dict[str, Any]], bool]:
            return _trace_paths(start, adjacency, max_depth=max_depth, max_paths=200)

        paths, truncated = _run(expect["start"], expect["max_depth"])
        if truncated != expect["truncated"]:
            problems.append(f"trace truncated {truncated} != {expect['truncated']}")
        got_shapes = [
            {"nodes": p["nodes"], "depth": p["depth"], "end_state": p["end_state"]} for p in paths
        ]
        if got_shapes != expect["paths"]:
            problems.append(f"trace paths {got_shapes} != {expect['paths']}")
        cap = expect["depth_cap"]
        cap_start = cap["start"] if "start" in cap else expect["start"]
        cap_paths, cap_truncated = _run(cap_start, cap["max_depth"])
        cap_shapes = [
            {"nodes": p["nodes"], "depth": p["depth"], "end_state": p["end_state"]}
            for p in cap_paths
        ]
        if cap_truncated != cap["truncated"]:
            problems.append(f"depth-cap truncated {cap_truncated} != {cap['truncated']}")
        if cap_shapes != cap["paths"]:
            problems.append(f"depth-cap paths {cap_shapes} != {cap['paths']}")
        iso = expect["isolated_node"]
        iso_paths, iso_truncated = _run(iso["start"], expect["max_depth"])
        if iso_paths != iso["paths"] or iso_truncated:
            problems.append(f"isolated node produced paths: {iso_paths}")
        # Hop-level provenance for one documented path (path 5 in fixture order).
        if len(paths) >= 5:
            hops = paths[4].get("hops", [])
            want_hops = expect["hops_for_path_5"]
            if len(hops) != len(want_hops):
                problems.append(f"path-5 hop count {len(hops)} != {len(want_hops)}")
            for want, hop in zip(want_hops, hops, strict=False):
                if hop.get("source") != want["source"] or hop.get("target") != want["target"]:
                    problems.append(f"path-5 hop endpoints mismatch: {hop}")
                if _nos(hop.get("supporting_source_record_ids")) != want["supporting_record_nos"]:
                    problems.append(f"path-5 hop supporting ids mismatch: {hop}")
        return problems

    @classmethod
    def _locator_problems(cls, got: dict[str, Any], known_ids: set[str]) -> list[str]:
        problems: list[str] = []

        def _walk(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "supporting_source_record_ids":
                        for rid in item or []:
                            if str(rid) not in known_ids:
                                problems.append(f"unknown supporting record id {rid}")
                    else:
                        _walk(item)
            elif isinstance(value, list):
                for item in value:
                    _walk(item)

        _walk(got)
        return problems

    def _eval_flow_golden(self) -> dict[str, Any]:
        fixture = _load(FLOW_FIXTURE)
        expect = fixture["expect"]
        rows = self._flow_rows(fixture)
        known_ids = {str(row.id) for row in rows}

        facts, warnings = extract_facts(rows)
        victim_financials = extract_victim_financials(self._flow_victims(fixture))
        aggregates = aggregate_facts(facts, max_supporting_ids=500)
        patterns = evaluate_patterns(
            facts, victim_financials, amount_threshold=Decimal(fixture["amount_threshold"])
        )
        owns_edges = [dict(edge) for edge in fixture["owns_edges"]]
        network = build_structure_network(facts, owns_edges, max_edges=500)
        payload = build_payload(
            case_id=uuid.UUID(fixture["case_id"]),
            facts=facts,
            victim_financials=victim_financials,
            aggregates=aggregates,
            network=network,
            patterns=patterns,
            warnings=warnings,
            scope={"case_id": fixture["case_id"], "records_scanned": len(rows)},
            max_facts=500,
        )

        agg_json = _jsonable(aggregates)
        aggregate_problems = self._check_aggregates(agg_json, expect)
        pattern_problems = self._check_patterns(_jsonable(patterns), expect["patterns"])
        network_problems = self._check_network(network, expect["network"])
        trace_problems = self._check_trace(network, expect["trace"])
        locator_problems = self._locator_problems(
            {
                "aggregates": agg_json,
                "patterns": _jsonable(patterns),
                "network": _jsonable(network),
            },
            known_ids,
        )

        # A1 honesty: victims disclose every missing field, never fabricated.
        victim_problems: list[str] = []
        for want, got in zip(expect["victim_financials"], victim_financials, strict=False):
            if got["victim_id"] != want["victim_id"]:
                victim_problems.append("victim id mismatch")
            if str(got["reported_amount"]) != str(want["reported_amount"]):
                victim_problems.append(
                    f"victim reported_amount {got['reported_amount']!r} != "
                    f"{want['reported_amount']!r}"
                )
            if got["missing"] != want["missing"]:
                victim_problems.append(f"victim missing {got['missing']} != {want['missing']}")
            if got["limitations"] != want["limitations"]:
                victim_problems.append(f"victim limitations {got['limitations']}")

        invalid = next(
            (
                f
                for f in facts
                if f.source_record_id == str(rows[9].id)  # record_no 10
            ),
            None,
        )
        invalid_ok = (
            invalid is not None
            and invalid.amount is None
            and invalid.amount_original == expect["invalid_amount_fact"]["amount_original"]
            and invalid.fact_class == expect["invalid_amount_fact"]["fact_class"]
        )
        direction_key = expect["no_direction_fact"]["every_transaction_missing_includes"]
        direction_ok = all(
            direction_key in f.missing for f in facts if f.fact_class == "transaction"
        )
        status_definition_present = bool(
            (payload.get("calculation_definitions") or {}).get("status_separation")
        )
        forbidden_total_keys = [
            key for key in ("grand_total", "total", "total_amount", "net_total") if key in agg_json
        ]

        # Bounds probes: the same data under deliberately small caps.
        capped_agg = aggregate_facts(
            facts, max_supporting_ids=expect["limits"]["max_supporting_ids"]
        )
        inr_bucket = next(b for b in capped_agg["currency_buckets"] if b["currency"] == "INR")
        capped_net = build_structure_network(
            facts, owns_edges, max_edges=expect["limits"]["max_edges"]
        )
        capped_payload = build_payload(
            case_id=uuid.UUID(fixture["case_id"]),
            facts=facts,
            victim_financials=victim_financials,
            aggregates=aggregates,
            network=network,
            patterns=patterns,
            warnings=warnings,
            scope={"case_id": fixture["case_id"]},
            max_facts=expect["limits"]["max_facts"],
        )
        limits = {
            "max_supporting_ids": expect["limits"]["max_supporting_ids"],
            "bucket_ids_capped": bool(inr_bucket.get("supporting_ids_capped"))
            and len(inr_bucket["supporting_source_record_ids"])
            == expect["limits"]["max_supporting_ids"],
            "max_edges": expect["limits"]["max_edges"],
            "edges_bounded": capped_net["edges_bounded"]
            and capped_net["edges_total"] == expect["limits"]["max_edges"],
            "max_facts": expect["limits"]["max_facts"],
            "facts_bounded": capped_payload["facts_bounded"]
            and len(capped_payload["facts"]) == expect["limits"]["max_facts"],
        }

        # Determinism: two replays over the same rows must agree exactly.
        facts_b, warnings_b = extract_facts(rows)
        replay = _jsonable(
            {
                "warnings": warnings_b,
                "aggregates": aggregate_facts(facts_b, max_supporting_ids=500),
                "patterns": evaluate_patterns(
                    facts_b,
                    extract_victim_financials(self._flow_victims(fixture)),
                    amount_threshold=Decimal(fixture["amount_threshold"]),
                ),
                "network": build_structure_network(facts_b, owns_edges, max_edges=500),
            }
        )
        first = _jsonable(
            {
                "warnings": warnings,
                "aggregates": aggregates,
                "patterns": patterns,
                "network": network,
            }
        )
        determinism_ok = replay == first

        return {
            "n_records": len(rows),
            "n_victims": len(victim_financials),
            "facts_total": len(facts),
            "warnings": _jsonable(warnings),
            "warnings_match": _jsonable(warnings) == expect["warnings"],
            "aggregate_problems": aggregate_problems,
            "pattern_problems": pattern_problems,
            "network_problems": network_problems,
            "trace_problems": trace_problems,
            "locator_problems": locator_problems,
            "victim_problems": victim_problems,
            "invalid_amount_ok": invalid_ok,
            "direction_absence_ok": direction_ok,
            "status_separation_documented": status_definition_present,
            "no_unkeyed_grand_total": not forbidden_total_keys,
            "grand_total_keys_found": forbidden_total_keys,
            "firing_count": len(patterns["firing"]),
            "not_fired": patterns["not_fired"],
            "not_evaluable_rules": sorted(entry["rule"] for entry in patterns["not_evaluable"]),
            "currency_buckets": [
                {
                    "currency": b["currency"],
                    "count": b["count"],
                    "total_records": str(b["total_records"]),
                    "currency_unknown": b["currency_unknown"],
                }
                for b in agg_json["currency_buckets"]
            ],
            "limits": limits,
            "determinism_ok": determinism_ok,
        }

    @staticmethod
    def _cross_rows(case: dict[str, Any]) -> dict[str, Any]:
        records = [
            SourceRecord(
                evidence_file_id=spec["evidence_file_id"],
                record_no=spec["record_no"],
                raw_data=spec["raw_data"],
                status="parsed",
            )
            for spec in case["records"]
        ]
        for row, spec in zip(records, case["records"], strict=True):
            row.id = uuid.UUID(spec["id"])
        evidence = []
        for spec in case["evidence_files"]:
            file_row = EvidenceFile(
                case_id=case["case_id"],
                original_filename="golden.json",
                stored_key=f"golden/{spec['id']}.json",
                content_type="application/json",
                file_size=128,
                sha256=spec["sha256"],
                format="json",
                encoding="utf-8",
                record_count=len(case["records"]),
                status="stored",
            )
            file_row.id = uuid.UUID(spec["id"])
            evidence.append(file_row)
        entities = []
        for spec in case["entities"]:
            entity = Entity(
                case_id=case["case_id"],
                entity_type=spec["entity_type"],
                canonical_value=spec["canonical_value"],
                blocking_key=blocking_key(spec["entity_type"], spec["canonical_value"]),
                display_value=spec["canonical_value"],
                status="active",
            )
            entity.id = uuid.UUID(spec["id"])
            entities.append(entity)
        aliases = []
        for spec in case["aliases"]:
            alias = EntityAlias(
                entity_id=spec["entity_id"],
                alias_value=spec["alias_value"],
                alias_type=spec["alias_type"],
            )
            alias.id = uuid.UUID(spec["id"])
            aliases.append(alias)
        return {
            "records": records,
            "evidence_files": evidence,
            "entities": entities,
            "aliases": aliases,
        }

    @classmethod
    def _check_candidates(
        cls,
        candidates: list[dict[str, Any]],
        expect_candidates: list[dict[str, Any]],
        label_to_case: dict[str, str],
    ) -> list[str]:
        problems: list[str] = []
        if len(candidates) != len(expect_candidates):
            problems.append(f"candidate count {len(candidates)} != {len(expect_candidates)}")
        for want, got in zip(expect_candidates, candidates, strict=False):
            group = got["group"]
            tag = f"{group['indicator_kind']}/{group['value_normalized']}"
            if group["indicator_kind"] != want["indicator_kind"]:
                problems.append(f"{tag}: kind mismatch")
            if group["value_normalized"] != want["value_normalized"]:
                problems.append(f"{tag}: value mismatch")
            if got["classification"] != want["classification"]:
                problems.append(
                    f"{tag}: classification {got['classification']} != {want['classification']}"
                )
            if got["score"] != want["score"]:
                problems.append(f"{tag}: score {got['score']} != {want['score']}")
            if got["reviewable"] != want["reviewable"]:
                problems.append(f"{tag}: reviewable {got['reviewable']} != {want['reviewable']}")
            if want.get("review_disabled_reason_non_null") and not got.get(
                "review_disabled_reason"
            ):
                problems.append(f"{tag}: review_disabled_reason missing")
            if got["additional_shared_kinds"] != want["additional_shared_kinds"]:
                problems.append(
                    f"{tag}: additional {got['additional_shared_kinds']} != "
                    f"{want['additional_shared_kinds']}"
                )
            conflicts = [c["kind"] for c in got["conflicting_attributes"]["evidence"]]
            if conflicts != want["conflicts"]:
                problems.append(f"{tag}: conflicts {conflicts} != {want['conflicts']}")
            sides = {side["case_id"]: side for side in got["sides"]}
            if len(sides) != len(want["sides"]):
                problems.append(f"{tag}: side count {len(sides)} != {len(want['sides'])}")
            for want_side in want["sides"]:
                case_id = label_to_case[want_side["label"]]
                side = sides.get(case_id)
                if side is None:
                    problems.append(f"{tag}: missing side {want_side['label']}")
                    continue
                for field in (
                    "value_originals",
                    "entity_ids",
                    "source_record_ids",
                    "evidence_file_ids",
                ):
                    if sorted(side.get(field) or []) != sorted(want_side[field]):
                        problems.append(f"{tag}: side {field} mismatch")
                if side["reviewed_alias"] != want_side["reviewed_alias"]:
                    problems.append(f"{tag}: side reviewed_alias mismatch")
                if sorted(side["contributing_kinds"]) != sorted(want_side["contributing_kinds"]):
                    problems.append(f"{tag}: side contributing_kinds mismatch")
                if side["supporting_ids_capped"] != want_side["supporting_ids_capped"]:
                    problems.append(f"{tag}: side supporting_ids_capped mismatch")
        return problems

    @classmethod
    def _candidate_keys(cls, candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
        return [
            {
                "indicator_kind": c["group"]["indicator_kind"],
                "value_normalized": c["group"]["value_normalized"],
            }
            for c in candidates
        ]

    def _eval_crosscase_golden(self) -> dict[str, Any]:
        fixture = _load(CROSS_FIXTURE)
        expect = fixture["expect"]
        scope = fixture["scope_case_ids"]
        label_to_case = {case["label"]: case["case_id"] for case in fixture["cases"]}

        indicators_by_case: dict[str, list[Any]] = {}
        per_case_counters: dict[str, Any] = {}
        row_shapes: dict[str, dict[str, Any]] = {}
        for case in fixture["cases"]:
            rows = self._cross_rows(case)
            row_shapes[case["label"]] = rows
            extraction = collect_case_indicators(
                case_id=case["case_id"],
                records=rows["records"],
                evidence_files=rows["evidence_files"],
                entities=rows["entities"],
                aliases=rows["aliases"],
                max_indicators=1000,
            )
            indicators_by_case[case["case_id"]] = extraction.indicators
            per_case_counters[case["label"]] = {
                "indicators": len(extraction.indicators),
                "records_scanned": extraction.records_scanned,
                "evidence_files_scanned": extraction.evidence_files_scanned,
                "entity_rows": extraction.entity_rows,
                "alias_rows": extraction.alias_rows,
                "values_skipped_invalid": extraction.values_skipped_invalid,
            }

        counter_problems: list[str] = []
        for case in fixture["cases"]:
            got = per_case_counters[case["label"]]
            for field, want in case["expect"].items():
                if got[field] != want:
                    counter_problems.append(f"{case['label']}.{field}: {got[field]} != {want}")

        candidates, stats = build_candidates(
            indicators_by_case,
            scope_case_ids=scope,
            scope_hash=_scope_hash(scope),
            max_candidates=100,
            max_supporting_ids=50,
        )
        candidate_problems = self._check_candidates(candidates, expect["candidates"], label_to_case)

        # Precision / recall over candidate keys.
        want_keys = {(c["indicator_kind"], c["value_normalized"]) for c in expect["candidates"]}
        got_keys = {
            (c["group"]["indicator_kind"], c["group"]["value_normalized"]) for c in candidates
        }
        true_positives = len(want_keys & got_keys)
        false_positives = len(got_keys - want_keys)
        false_negatives = len(want_keys - got_keys)

        # Single-case groups must never become candidates.
        decoy_hits = [
            d
            for d in expect["decoys_never_candidates"]
            if (d["indicator_kind"], d["value_normalized"]) in got_keys
        ]

        # Bounds probes.
        limits_expect = expect["limits"]
        bounded_candidates, bounded_stats = build_candidates(
            indicators_by_case,
            scope_case_ids=scope,
            scope_hash=_scope_hash(scope),
            max_candidates=limits_expect["max_candidates"],
            max_supporting_ids=50,
        )
        capped_alpha = collect_case_indicators(
            case_id=fixture["cases"][0]["case_id"],
            records=row_shapes["alpha"]["records"],
            evidence_files=row_shapes["alpha"]["evidence_files"],
            entities=row_shapes["alpha"]["entities"],
            aliases=row_shapes["alpha"]["aliases"],
            max_indicators=limits_expect["max_indicators_alpha"],
        )
        capped_candidates, _ = build_candidates(
            indicators_by_case,
            scope_case_ids=scope,
            scope_hash=_scope_hash(scope),
            max_candidates=100,
            max_supporting_ids=limits_expect["max_supporting_ids"],
        )
        capped_side = next(
            (
                side
                for candidate in capped_candidates
                if candidate["group"]["indicator_kind"] == "account_ref"
                for side in candidate["sides"]
                if side["case_id"] == label_to_case["alpha"]
            ),
            None,
        )
        limits = {
            "candidates_bounded": bounded_stats["candidates_bounded"]
            and self._candidate_keys(bounded_candidates)
            == limits_expect["bounded_first_three_keys"],
            "indicators_bounded": capped_alpha.indicators_bounded
            and len(capped_alpha.indicators) == limits_expect["max_indicators_alpha"],
            "supporting_ids_capped": (
                capped_side is not None
                and capped_side["supporting_ids_capped"] is True
                and sorted(capped_side["source_record_ids"])
                == sorted(limits_expect["capped_side_kept_record_ids"])
            ),
        }

        # Determinism: identical inputs must produce identical candidates.
        replay_indicators: dict[str, list[Any]] = {}
        for case in fixture["cases"]:
            rows = self._cross_rows(case)
            replay_indicators[case["case_id"]] = collect_case_indicators(
                case_id=case["case_id"],
                records=rows["records"],
                evidence_files=rows["evidence_files"],
                entities=rows["entities"],
                aliases=rows["aliases"],
                max_indicators=1000,
            ).indicators
        replay_candidates, replay_stats = build_candidates(
            replay_indicators,
            scope_case_ids=scope,
            scope_hash=_scope_hash(scope),
            max_candidates=100,
            max_supporting_ids=50,
        )
        determinism_ok = (
            _jsonable(replay_candidates) == _jsonable(candidates) and replay_stats == stats
        )

        name_only = next(
            (c for c in candidates if c["classification"] == "similarity_name_only"),
            None,
        )
        hash_candidate = next(
            (c for c in candidates if c["group"]["indicator_kind"] == "evidence_hash"),
            None,
        )

        return {
            "n_cases": len(fixture["cases"]),
            "n_records": sum(len(c["records"]) for c in fixture["cases"]),
            "per_case_indicators": per_case_counters,
            "counter_problems": counter_problems,
            "groups_total": stats["groups_total"],
            "groups_shared": stats["groups_shared"],
            "candidates_bounded": stats["candidates_bounded"],
            "candidate_problems": candidate_problems,
            "candidate_keys": self._candidate_keys(candidates),
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "precision": _rate(true_positives, true_positives + false_positives),
            "recall": _rate(true_positives, true_positives + false_negatives),
            "decoy_hits": decoy_hits,
            "name_only_not_reviewable": (
                name_only is not None
                and name_only["reviewable"] is False
                and bool(name_only.get("review_disabled_reason"))
            ),
            "evidence_hash_exact_identifier": (
                hash_candidate is not None
                and hash_candidate["classification"] == "exact_identifier"
            ),
            "limits": limits,
            "determinism_ok": determinism_ok,
        }

    def _golden_section(self) -> dict[str, Any]:
        print("  golden: financial flow", flush=True)
        flow = self._eval_flow_golden()
        print("  golden: cross-case discovery", flush=True)
        crosscase = self._eval_crosscase_golden()
        return {"financial_flow": flow, "cross_case": crosscase}

    # -- live end-to-end section ---------------------------------------------

    async def login(self, username: str, password: str, *, admin: bool = False) -> str:
        response = await self.api.post(
            "/auth/login", json={"username": username, "password": password}
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        if admin:
            self.admin_token = token
        else:
            self.token = token
        return token

    async def ai_ready(self) -> bool:
        response = await self.api.get("/ai/status", headers=self._headers())
        if response.status_code != 200:
            return False
        return bool(response.json().get("ready"))

    async def _create_case(self, title: str, description: str, *, admin: bool = False) -> str:
        response = await self.api.post(
            "/cases",
            json={"title": title, "description": description},
            headers=self._headers(self.admin_token if admin else None),
        )
        response.raise_for_status()
        return response.json()["id"]

    async def _upload_json(
        self,
        case_id: str,
        name: str,
        records: list[dict[str, Any]],
        *,
        token: str | None = None,
    ) -> str:
        payload = json.dumps(records).encode()
        response = await self.api.post(
            f"/cases/{case_id}/evidence",
            files={"file": (name, payload, "application/json")},
            headers=self._headers(token),
        )
        response.raise_for_status()
        return response.json()["id"]

    async def _ingest(
        self, case_id: str, evidence_id: str, *, token: str | None = None
    ) -> dict[str, Any]:
        response = await self.api.post(
            f"/cases/{case_id}/ingest",
            json={"evidence_file_id": evidence_id},
            headers=self._headers(token),
        )
        response.raise_for_status()
        accepted = response.json()
        job_id = (accepted.get("job") or {}).get("id")
        deadline = time.monotonic() + JOB_POLL_TIMEOUT_SECONDS
        while job_id and time.monotonic() < deadline:
            listing = await self.api.get(
                f"/cases/{case_id}/ingest-jobs", headers=self._headers(token)
            )
            listing.raise_for_status()
            for item in listing.json()["items"]:
                if item["id"] == job_id and item["status"] in INGEST_TERMINAL_STATES:
                    return item
            await asyncio.sleep(1.0)
        raise TimeoutError(f"ingest job {job_id} did not reach a terminal state")

    async def _submit_feature(self, case_id: str, path_segment: str) -> dict[str, Any]:
        response = await self.api.post(
            f"/cases/{case_id}/evidence-intelligence/{path_segment}",
            json={},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    async def _poll_job(
        self, case_id: str, job_id: str, *, feature: str, token: str | None = None
    ) -> dict[str, Any]:
        deadline = time.monotonic() + JOB_POLL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            response = await self.api.get(
                f"/cases/{case_id}/evidence-intelligence/jobs",
                params={"feature": feature},
                headers=self._headers(token),
            )
            response.raise_for_status()
            for item in response.json()["items"]:
                if item["id"] == job_id and item["status"] in TERMINAL_JOB_STATES:
                    return item
            await asyncio.sleep(1.0)
        raise TimeoutError(f"{feature} job {job_id} did not reach a terminal state")

    async def _artifacts(
        self, case_id: str, kind: str, *, token: str | None = None
    ) -> list[dict[str, Any]]:
        response = await self.api.get(
            f"/cases/{case_id}/evidence-intelligence/artifacts",
            params={"kind": kind},
            headers=self._headers(token),
        )
        response.raise_for_status()
        return response.json()["items"]

    async def _db_case_records(self, case_id: str) -> list[SourceRecord]:
        from sqlalchemy import select

        factory = self.database.session_factory()
        async with factory() as session:
            result = await session.execute(
                select(SourceRecord)
                .join(EvidenceFile, SourceRecord.evidence_file_id == EvidenceFile.id)
                .where(EvidenceFile.case_id == str(case_id))
                .order_by(EvidenceFile.created_at, EvidenceFile.id, SourceRecord.record_no)
            )
            return list(result.scalars())

    async def _live_flow(
        self,
        flow_fixture: dict[str, Any],
        live_fixture: dict[str, Any],
    ) -> dict[str, Any]:
        case_id = await self._create_case(
            "phase-4 flow eval (synthetic)",
            "created and deleted by scripts/eval_phase4.py",
        )
        self.case_ids["flow"] = case_id
        print(f"  live: flow case {case_id}", flush=True)

        evidence_id = await self._upload_json(case_id, "phase4-flow.json", flow_fixture["records"])
        ingest = await self._ingest(case_id, evidence_id)

        # Cancellation probe on the first submission (branch-recorded: the
        # runner is cooperative, so a fast machine may finish before the
        # cancel request lands; that branch is 409-refused, not a failure).
        submitted = await self._submit_feature(case_id, "financial-flow")
        first_job_id = submitted["job"]["id"]
        cancel = await self.api.post(
            f"/cases/{case_id}/evidence-intelligence/jobs/{first_job_id}/cancel",
            headers=self._headers(),
        )
        section: dict[str, Any] = {
            "case_id": case_id,
            "ingest_status": ingest.get("status"),
            "cancel": {
                "status_code": cancel.status_code,
                "branch": "accepted" if cancel.status_code in (200, 202) else "refused",
            },
        }
        started = time.monotonic()
        first_job = await self._poll_job(case_id, first_job_id, feature="financial_flow")
        section["cancel"]["job_status"] = first_job["status"]
        if cancel.status_code in (200, 202):
            artifacts_after_cancel = await self._artifacts(case_id, "financial_finding")
            section["cancel"]["artifacts_after_cancel"] = len(artifacts_after_cancel)
            section["cancel"]["zero_artifacts"] = not artifacts_after_cancel
            # A canceled job can never succeed: resubmission must be accepted.
            # This clean submit -> terminal window is the reported flow latency
            # (the cancel probe above would have consumed the first run's time).
            started = time.monotonic()
            rerun = await self._submit_feature(case_id, "financial-flow")
            section["cancel"]["rerun_job_id"] = rerun["job"]["id"]
            rerun_job = await self._poll_job(case_id, rerun["job"]["id"], feature="financial_flow")
            section["latency_ms"] = int((time.monotonic() - started) * 1000)
            section["cancel"]["rerun_status"] = rerun_job["status"]
            job = rerun_job
        else:
            section["cancel"]["note"] = (
                "run finished before the cooperative cancel landed; the "
                "completed artifacts are reused"
            )
            # Refused branch: the first run's timing window was consumed by
            # the cancel round-trip, so one more clean submission is timed. It
            # overwrites nothing: the payload is deterministic over the same
            # records, so the artifact is content-hash deduplicated (reused).
            started = time.monotonic()
            timing = await self._submit_feature(case_id, "financial-flow")
            job = await self._poll_job(case_id, timing["job"]["id"], feature="financial_flow")
            section["latency_ms"] = int((time.monotonic() - started) * 1000)
        section["job_status"] = job["status"]

        artifacts = await self._artifacts(case_id, "financial_finding")
        section["artifacts"] = len(artifacts)
        if not artifacts:
            return section
        payload = artifacts[0]["payload"]
        golden_expect = _load(FLOW_FIXTURE)["expect"]
        expect_live = live_fixture["flow_expect_live"]

        section["facts_total"] = payload.get("facts_total")
        # check_ids=False: live record ids are real uuids, not the golden hex
        # scheme; id-level equality is gated by db_recompute_exact below.
        section["aggregates_match_golden"] = self._check_aggregates(
            payload.get("aggregates", {}), golden_expect, check_ids=False
        )
        # Independent recomputation from PostgreSQL rows (never the self-report).
        db_rows = await self._db_case_records(case_id)
        db_facts, db_warnings = extract_facts(db_rows)
        db_aggregates = aggregate_facts(
            db_facts, max_supporting_ids=self.settings.FLOW_MAX_SUPPORTING_IDS
        )
        section["db_records"] = len(db_rows)
        section["db_recompute_exact"] = _jsonable(db_aggregates) == payload.get(
            "aggregates"
        ) and _jsonable(db_warnings) == payload.get("extraction_warnings")
        db_ids = {str(row.id) for row in db_rows}
        locator_problems = [
            fact.get("source_record_id")
            for fact in payload.get("facts", [])
            if fact.get("source_record_id") not in db_ids
        ]
        section["fact_locator_problems"] = locator_problems

        patterns = payload.get("patterns", {})
        want_firing = [
            entry
            for entry in golden_expect["patterns"]["firing"]
            if entry["rule"] != "victim_loss_unmatched"
        ]
        got_firing = patterns.get("firing", [])
        pattern_problems: list[str] = []
        if len(got_firing) != len(want_firing):
            pattern_problems.append(f"firing count {len(got_firing)} != {len(want_firing)}")
        for want, got in zip(want_firing, got_firing, strict=False):
            if got["rule"] != want["rule"]:
                pattern_problems.append(f"firing rule {got['rule']} != {want['rule']}")
                continue
            for key, value in want["evidence"].items():
                if key == "transaction_amounts_in_case_count":
                    continue  # corpus-independent length; checked in golden
                if str(got["evidence"].get(key)) != str(value):
                    pattern_problems.append(f"{got['rule']} evidence.{key} mismatch")
        not_evaluable = {
            entry["rule"]: entry["reason"] for entry in patterns.get("not_evaluable", [])
        }
        section["pattern_problems"] = pattern_problems
        section["not_fired"] = patterns.get("not_fired")
        section["not_fired_match"] = (
            patterns.get("not_fired") == expect_live["patterns"]["not_fired"]
        )
        section["not_evaluable_match"] = not_evaluable == expect_live["patterns"]["not_evaluable"]
        section["rule_count_match"] = (
            patterns.get("rule_count") == expect_live["patterns"]["rule_count"]
        )
        section["no_victim_fabrication"] = payload.get("victim_financials") == []

        network = payload.get("structure_network", {})
        section["confirmed_transfer_edges"] = network.get("confirmed_transfer_edges")
        section["edges_typed_safely"] = all(
            edge.get("edge_kind") in ("association", "relationship")
            for edge in network.get("edges", [])
        )
        not_computable = payload.get("aggregates", {}).get("not_computable", {})
        section["no_direction_claim"] = all(
            value == "not_computable_no_direction"
            for value in (
                not_computable.get("inflow"),
                not_computable.get("outflow"),
                not_computable.get("net"),
            )
        )
        section["status_separation_documented"] = bool(
            (payload.get("calculation_definitions") or {}).get("status_separation")
        )
        section["no_unkeyed_grand_total"] = not any(
            key in (payload.get("aggregates") or {})
            for key in ("grand_total", "total", "total_amount", "net_total")
        )

        # Trace probes (read-only, deterministic, no job).
        trace_ok = await self.api.post(
            f"/cases/{case_id}/evidence-intelligence/financial-flow/trace",
            json={"target": "ACC-U1", "max_depth": 4},
            headers=self._headers(),
        )
        trace_ok.raise_for_status()
        trace_body = trace_ok.json()
        section["trace"] = {
            "status": trace_body.get("status"),
            "paths": len(trace_body.get("paths") or []),
            "coastal_path_found": any(
                _adjacent(
                    path.get("nodes") or [],
                    ["account:ACCU2", "bank:coastal trust"],
                )
                for path in trace_body.get("paths") or []
            ),
            "simple_paths": all(
                len(path.get("nodes") or []) == len(set(path.get("nodes") or []))
                for path in trace_body.get("paths") or []
            ),
            "confirmed_transfer_edges": (trace_body.get("network") or {}).get(
                "confirmed_transfer_edges"
            ),
        }
        trace_transfer = await self.api.post(
            f"/cases/{case_id}/evidence-intelligence/financial-flow/trace",
            json={"target": "ACC-U1", "edge_kind": "transfer"},
            headers=self._headers(),
        )
        trace_transfer.raise_for_status()
        section["trace"]["transfer_status"] = trace_transfer.json().get("status")
        section["trace"]["transfer_reason"] = trace_transfer.json().get("reason")
        trace_unknown = await self.api.post(
            f"/cases/{case_id}/evidence-intelligence/financial-flow/trace",
            json={"target": "ACC-NOPE-404"},
            headers=self._headers(),
        )
        section["trace"]["unknown_status"] = trace_unknown.json().get("status")

        # Model-dependent explain outcome: reported, never gated.
        explain = await self.api.post(
            f"/cases/{case_id}/evidence-intelligence/artifacts/{artifacts[0]['id']}/explain",
            headers=self._headers(),
        )
        section["explain"] = {
            "status_code": explain.status_code,
            "outcome": (
                "recorded_ai_unverified"
                if explain.status_code == 200
                else explain.json().get("error", {}).get("code")
                if explain.status_code >= 400
                else "unexpected"
            ),
        }
        return section

    async def _live_crosscase(self, live_fixture: dict[str, Any]) -> dict[str, Any]:
        spec = live_fixture["cross_case"]
        section: dict[str, Any] = {}

        case_x = await self._create_case(
            "phase-4 crosscase X (synthetic)",
            "created and deleted by scripts/eval_phase4.py",
        )
        case_y = await self._create_case(
            "phase-4 crosscase Y (synthetic)",
            "created and deleted by scripts/eval_phase4.py",
        )
        case_z = await self._create_case(
            "phase-4 crosscase Z (admin, synthetic)",
            "created and deleted by scripts/eval_phase4.py",
            admin=True,
        )
        self.case_ids["cross_x"] = case_x
        self.case_ids["cross_y"] = case_y
        self.case_ids["cross_z"] = case_z
        print(f"  live: cross-case cases x={case_x} y={case_y} z={case_z}", flush=True)

        for label, case_id, records in (
            ("x", case_x, spec["case_x_records"]),
            ("y", case_y, spec["case_y_records"]),
            ("z", case_z, spec["case_z_records"]),
        ):
            admin_owned = label == "z"
            evidence_id = await self._upload_json(
                case_id,
                f"phase4-cross-{label}.json",
                records,
                token=self.admin_token if admin_owned else None,
            )
            ingest = await self._ingest(
                case_id,
                evidence_id,
                token=self.admin_token if admin_owned else None,
            )
            section[f"ingest_{label}"] = ingest.get("status")

        # Scope {X, Y} as the investigator.
        started = time.monotonic()
        discover = await self.api.post(
            "/cross-case/discover",
            json={"anchor_case_id": case_x, "case_ids": [case_x, case_y]},
            headers=self._headers(),
        )
        discover.raise_for_status()
        job = await self._poll_job(case_x, discover.json()["job"]["id"], feature="cross_case")
        section["latency_ms"] = int((time.monotonic() - started) * 1000)
        section["job_status"] = job["status"]

        candidates = await self.api.get(
            "/cross-case/candidates",
            params={"anchor_case_id": case_x},
            headers=self._headers(),
        )
        candidates.raise_for_status()
        items = candidates.json()["items"]
        section["candidates_xy"] = [
            {
                "id": item["id"],
                "indicator_kind": item["payload"]["group"]["indicator_kind"],
                "value_normalized": item["payload"]["group"]["value_normalized"],
                "classification": item["payload"]["classification"],
                "score": item["payload"]["score"],
                "reviewable": item["payload"]["reviewable"],
                "sides": sorted(side["case_id"] for side in item["payload"]["sides"]),
            }
            for item in items
        ]
        want_candidates = spec["expect_investigator_scope_xy"]["candidates"]
        got_keys = sorted(
            (c["indicator_kind"], c["value_normalized"]) for c in section["candidates_xy"]
        )
        want_keys = sorted((c["indicator_kind"], c["value_normalized"]) for c in want_candidates)
        section["candidate_keys_match"] = got_keys == want_keys
        by_key = {(c["indicator_kind"], c["value_normalized"]): c for c in section["candidates_xy"]}
        per_want: list[bool] = []
        for want in want_candidates:
            got = by_key.get((want["indicator_kind"], want["value_normalized"]))
            per_want.append(
                got is not None
                and got["classification"] == want["classification"]
                and got["reviewable"] == want["reviewable"]
            )
        section["classifications_match"] = all(per_want)
        section["sides_are_xy"] = all(
            c["sides"] == sorted([case_x, case_y]) for c in section["candidates_xy"]
        )
        decoy_present = [
            d
            for d in spec["expect_investigator_scope_xy"]["decoys_absent"]
            if (d["indicator_kind"], d["value_normalized"]) in got_keys
        ]
        section["decoy_present"] = decoy_present

        # Approval: records an audited child artifact; never merges, never
        # rewrites the parent, never adds aliases.
        target = next(
            (item for item in items if item["payload"]["group"]["indicator_kind"] == "account_ref"),
            items[0] if items else None,
        )
        name_target = next(
            (item for item in items if item["payload"]["group"]["indicator_kind"] == "name"),
            None,
        )
        if target is not None:
            section["approval"] = await self._approval_checks(
                case_x=case_x, case_y=case_y, target=target, name_target=name_target
            )

        # Admin scope {X, Z} - a different scope, different candidate set.
        admin_discover = await self.api.post(
            "/cross-case/discover",
            json={"anchor_case_id": case_x, "case_ids": [case_x, case_z]},
            headers=self._headers(self.admin_token),
        )
        admin_discover.raise_for_status()
        admin_job = await self._poll_job(
            case_x,
            admin_discover.json()["job"]["id"],
            feature="cross_case",
            token=self.admin_token,
        )
        section["admin_job_status"] = admin_job["status"]
        admin_candidates = await self.api.get(
            "/cross-case/candidates",
            params={"anchor_case_id": case_x},
            headers=self._headers(self.admin_token),
        )
        admin_candidates.raise_for_status()
        admin_items = admin_candidates.json()["items"]
        section["admin_candidates_xz"] = [
            {
                "id": item["id"],
                "indicator_kind": item["payload"]["group"]["indicator_kind"],
                "value_normalized": item["payload"]["group"]["value_normalized"],
                "sides": sorted(side["case_id"] for side in item["payload"]["sides"]),
            }
            for item in admin_items
        ]
        section["admin_sees_z_side"] = any(
            case_z in entry["sides"] for entry in section["admin_candidates_xz"]
        )

        # B7 read-time omission: the investigator's list must never mention Z.
        recheck = await self.api.get(
            "/cross-case/candidates",
            params={"anchor_case_id": case_x},
            headers=self._headers(),
        )
        recheck.raise_for_status()
        recheck_items = recheck.json()["items"]
        section["omission"] = {
            "total": recheck.json()["total"],
            "items": len(recheck_items),
            "no_z_side": all(
                case_z not in [side["case_id"] for side in item["payload"]["sides"]]
                for item in recheck_items
            ),
            "z_strings_absent": all(
                case_z not in json.dumps(item["payload"]) for item in recheck_items
            ),
        }

        # No-leak probes.
        denied = await self.api.post(
            "/cross-case/discover",
            json={"anchor_case_id": case_x, "case_ids": [case_x, case_z]},
            headers=self._headers(),
        )
        section["scope_denied"] = {
            "status_code": denied.status_code,
            "code": denied.json().get("error", {}).get("code"),
        }
        anon_discover = await self.api.post(
            "/cross-case/discover",
            json={"anchor_case_id": case_x, "case_ids": [case_x, case_y]},
        )
        anon_candidates = await self.api.get(
            "/cross-case/candidates", params={"anchor_case_id": case_x}
        )
        section["anon"] = {
            "discover_status": anon_discover.status_code,
            "candidates_status": anon_candidates.status_code,
        }

        # Explain on the Z-scope artifact as the investigator: fail closed 404.
        z_scope_artifact = next(
            (entry for entry in section["admin_candidates_xz"] if case_z in entry["sides"]),
            None,
        )
        if z_scope_artifact is not None:
            hidden = await self.api.post(
                f"/cases/{case_x}/evidence-intelligence/artifacts/{z_scope_artifact['id']}/explain",
                headers=self._headers(),
            )
            section["hidden_artifact_explain"] = {
                "status_code": hidden.status_code,
                "code": hidden.json().get("error", {}).get("code")
                if hidden.status_code >= 400
                else None,
            }

        section["viewer"] = await self._viewer_probe(case_x, case_y)
        return section

    async def _approval_checks(
        self,
        *,
        case_x: str,
        case_y: str,
        target: dict[str, Any],
        name_target: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from sqlalchemy import func, select

        artifact_id = target["id"]
        before_hash = target.get("content_hash")
        factory = self.database.session_factory()
        async with factory() as session:
            alias_count_before = (
                await session.execute(
                    select(func.count(EntityAlias.id))
                    .join(Entity, EntityAlias.entity_id == Entity.id)
                    .where(Entity.case_id.in_([case_x, case_y]))
                )
            ).scalar() or 0

        # B3 live: approving a name-similarity-only candidate must be refused
        # by the server outright (not merely hidden by the UI).
        name_refusal: dict[str, Any] = {"attempted": False}
        if name_target is not None:
            refuse = await self.api.post(
                f"/cases/{case_x}/evidence-intelligence/artifacts/{name_target['id']}/review",
                json={"decision": "approved", "note": "eval harness (must refuse)"},
                headers=self._headers(),
            )
            name_refusal = {
                "attempted": True,
                "status_code": refuse.status_code,
                "code": refuse.json().get("error", {}).get("code")
                if refuse.status_code >= 400
                else None,
            }

        approve = await self.api.post(
            f"/cases/{case_x}/evidence-intelligence/artifacts/{artifact_id}/review",
            json={"decision": "approved", "note": "eval harness approval"},
            headers=self._headers(),
        )
        approve.raise_for_status()
        parent_review = approve.json()

        parent_after = await self.api.get(
            "/cross-case/candidates",
            params={"anchor_case_id": case_x},
            headers=self._headers(),
        )
        parent_after.raise_for_status()
        parent_row = next(
            (item for item in parent_after.json()["items"] if item["id"] == artifact_id),
            None,
        )
        # The generic artifact listing deliberately excludes cross_case_link
        # rows entirely (no-leak: their payloads span several cases) - the
        # recorded child is therefore verified against PostgreSQL directly,
        # the harness's independent-verification convention.
        generic_list = await self._artifacts(case_x, "cross_case_link")
        from app.models import AuditLog, DerivedArtifact

        async with factory() as session:
            alias_count_after = (
                await session.execute(
                    select(func.count(EntityAlias.id))
                    .join(Entity, EntityAlias.entity_id == Entity.id)
                    .where(Entity.case_id.in_([case_x, case_y]))
                )
            ).scalar() or 0

            children = list(
                (
                    await session.execute(
                        select(DerivedArtifact).where(
                            DerivedArtifact.case_id == uuid.UUID(case_x),
                            DerivedArtifact.parent_artifact_id == uuid.UUID(artifact_id),
                            DerivedArtifact.kind == "cross_case_link",
                        )
                    )
                )
                .scalars()
                .all()
            )
            audit_rows = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.case_id == uuid.UUID(case_x),
                            AuditLog.action == "derived_artifact.approved",
                        )
                    )
                )
                .scalars()
                .all()
            )
        child = children[0] if len(children) == 1 else None
        child_payload = dict(child.payload) if child is not None else {}
        audit_child_ids = [
            (row.metadata_ or {}).get("reviewed_child_artifact_id") for row in audit_rows
        ]

        return {
            "name_only_refusal": name_refusal,
            "parent_status_after_review": parent_review.get("status"),
            "parent_kind_after_review": parent_review.get("kind"),
            "generic_list_omits_crosscase": generic_list == [],
            "child_recorded": (
                child is not None
                and child.status == "recorded"
                and child.origin == "deterministic"
                and child_payload.get("type") == "reviewed_cross_case_link"
                and child_payload.get("decision") == "approved"
                and child_payload.get("indicator_kind")
                == target["payload"]["group"]["indicator_kind"]
                and child_payload.get("value_normalized")
                == target["payload"]["group"]["value_normalized"]
                and child_payload.get("cases") == sorted([case_x, case_y])
                and child_payload.get("for_artifact_id") == artifact_id
            ),
            "parent_unrewritten": (
                parent_row is not None and parent_row.get("content_hash") == before_hash
            ),
            "no_aliases_added": alias_count_before == alias_count_after,
            "audit_row_recorded": (child is not None and str(child.id) in audit_child_ids),
        }

    async def _viewer_probe(self, case_x: str, inaccessible_case: str) -> dict[str, Any]:
        """Register a unique VIEWER, verify every denial, then suspend it.

        Convention under test (documented in ``get_case_or_404``: "404 when
        missing, 403 on IDOR"): the viewer holds ``case.read`` but is not a
        member of any case, so an *existing* inaccessible case answers 403
        CASE_ACCESS_DENIED while a *missing* case answers 404 - either way the
        viewer receives no case content. ``crosscase.read`` is absent from
        VIEWER, so discovery/candidates refuse 403 at the permission
        dependency, before any case or identifier is evaluated.
        """
        investigator_token = self.token  # restored: login() swaps the token
        suffix = uuid.uuid4().hex[:8]
        username = f"ph4_viewer_{suffix}"
        register = await self.api.post(
            "/auth/register",
            json={
                "username": username,
                "email": f"{username}@eval.invalid",
                "password": "viewer-eval-password-1",
            },
        )
        register.raise_for_status()
        self._viewer_id = register.json()["user"]["id"]

        approve = await self.api.post(
            f"/admin/users/{self._viewer_id}/approve",
            json={"role": "VIEWER"},
            headers=self._headers(self.admin_token),
        )
        approve.raise_for_status()
        viewer_token = await self.login(username, "viewer-eval-password-1")

        discover = await self.api.post(
            "/cross-case/discover",
            json={"anchor_case_id": case_x, "case_ids": [case_x]},
            headers=self._headers(viewer_token),
        )
        candidates = await self.api.get(
            "/cross-case/candidates",
            params={"anchor_case_id": case_x},
            headers=self._headers(viewer_token),
        )
        explain = await self.api.post(
            f"/cases/{case_x}/evidence-intelligence/artifacts/{uuid.uuid4()}/explain",
            headers=self._headers(viewer_token),
        )
        artifacts = await self.api.get(
            f"/cases/{inaccessible_case}/evidence-intelligence/artifacts",
            headers=self._headers(viewer_token),
        )
        missing_case = await self.api.get(
            f"/cases/{uuid.uuid4()}/evidence-intelligence/artifacts",
            headers=self._headers(viewer_token),
        )
        self.token = investigator_token

        def _code(response: httpx.Response) -> str | None:
            if response.status_code < 400:
                return None
            body = response.json()
            if isinstance(body, dict) and isinstance(body.get("error"), dict):
                return body["error"].get("code")
            return None  # plain HTTPException body carries no typed code

        return {
            "username": username,
            "discover_status": discover.status_code,
            "discover_code": _code(discover),
            "candidates_status": candidates.status_code,
            "candidates_code": _code(candidates),
            "explain_status": explain.status_code,
            "explain_code": _code(explain),
            "artifacts_on_inaccessible_case_status": artifacts.status_code,
            "artifacts_on_inaccessible_case_code": _code(artifacts),
            "artifacts_on_missing_case_status": missing_case.status_code,
        }

    async def _live_section(self) -> dict[str, Any]:
        live_fixture = _load(LIVE_FIXTURE)
        flow_fixture = _load(FLOW_FIXTURE)
        print("  live: financial flow", flush=True)
        flow = await self._live_flow(
            flow_fixture,
            {**live_fixture["flow"], "flow_expect_live": flow_fixture["expect_live"]},
        )
        print("  live: cross-case discovery", flush=True)
        crosscase = await self._live_crosscase(live_fixture)
        return {"flow": flow, "cross_case": crosscase}

    # -- lifecycle ------------------------------------------------------------

    async def run(self) -> int:
        try:
            await self.database.ping()
        except Exception as exc:  # noqa: BLE001 - setup failure
            print(f"database setup failure: {exc}", file=sys.stderr)
            return 2

        self.report["golden"] = self._golden_section()

        if not self.args.skip_live:
            try:
                await self.login(self.args.username, self.args.password)
                await self.login(self.args.admin_username, self.args.admin_password, admin=True)
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
            try:
                self.report["live"] = await self._live_section()
            finally:
                await self._cleanup()
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
        flow = golden["financial_flow"]
        crosscase = golden["cross_case"]
        gates: dict[str, bool] = {
            # A detector that reports nothing must not pass as "clean".
            "flow_not_vacuous": flow["facts_total"] > 0 and flow["firing_count"] > 0,
            "flow_totals_exact": flow["warnings_match"]
            and not flow["aggregate_problems"]
            and not flow["victim_problems"],
            "flow_currency_segregation": flow["no_unkeyed_grand_total"]
            and sorted(bucket["currency"] or "\x00" for bucket in flow["currency_buckets"])
            == ["\x00", "INR", "USD"],
            "flow_status_separation": flow["status_separation_documented"]
            and not any("by_status" in problem for problem in flow["aggregate_problems"]),
            "flow_pattern_precision_recall": not flow["pattern_problems"]
            and flow["not_fired"] == [],
            "flow_locator_validity": not flow["locator_problems"] and not flow["network_problems"],
            "flow_no_direction_claim": flow["direction_absence_ok"]
            and not flow["network_problems"],
            "flow_invalid_amount_rejected": flow["invalid_amount_ok"]
            and flow["warnings"].get("amount_invalid") == 1,
            "flow_path_correctness": not flow["trace_problems"],
            "flow_limits": all(flow["limits"].values()),
            "flow_determinism": flow["determinism_ok"],
            "crosscase_not_vacuous": crosscase["true_positives"] > 0,
            "crosscase_precision_recall": crosscase["false_positives"] == 0
            and crosscase["false_negatives"] == 0
            and not crosscase["candidate_problems"]
            and not crosscase["counter_problems"],
            "crosscase_classification_exact": not any(
                "classification" in problem for problem in crosscase["candidate_problems"]
            ),
            "crosscase_scores_exact": not any(
                "score" in problem for problem in crosscase["candidate_problems"]
            ),
            "crosscase_name_only_never_reviewable": crosscase["name_only_not_reviewable"],
            "crosscase_conflicts_exact": not any(
                "conflicts" in problem for problem in crosscase["candidate_problems"]
            ),
            "crosscase_evidence_hash_candidate": crosscase["evidence_hash_exact_identifier"],
            "crosscase_provenance_sides": not any(
                "side" in problem or "sides" in problem
                for problem in crosscase["candidate_problems"]
            ),
            "crosscase_limits": all(crosscase["limits"].values()),
            "crosscase_decoys_never_emit": not crosscase["decoy_hits"],
            "crosscase_determinism": crosscase["determinism_ok"],
        }
        if "live" in self.report:
            live = self.report["live"]
            flow_live = live.get("flow", {})
            cancel = flow_live.get("cancel", {})
            trace = flow_live.get("trace", {})
            cross_live = live.get("cross_case", {})
            gates.update(
                {
                    "live_flow_job_succeeded": flow_live.get("job_status") == "succeeded",
                    "live_flow_aggregates_match_golden": not flow_live.get(
                        "aggregates_match_golden"
                    ),
                    "live_flow_db_recompute_exact": flow_live.get("db_recompute_exact") is True,
                    "live_flow_locator_validity": not flow_live.get("fact_locator_problems"),
                    "live_flow_patterns_match_golden": not flow_live.get("pattern_problems")
                    and flow_live.get("not_fired_match") is True
                    and flow_live.get("not_evaluable_match") is True
                    and flow_live.get("rule_count_match") is True,
                    "live_flow_no_transfer_claim": (
                        flow_live.get("confirmed_transfer_edges") == 0
                        and flow_live.get("edges_typed_safely") is True
                        and trace.get("status") == "ok"
                        and trace.get("coastal_path_found") is True
                        and trace.get("simple_paths") is True
                        and trace.get("confirmed_transfer_edges") == 0
                        and trace.get("transfer_status") == "insufficient_data"
                    ),
                    "live_flow_trace_not_found_bogus": trace.get("unknown_status") == "not_found",
                    "live_flow_no_direction": flow_live.get("no_direction_claim") is True,
                    "live_flow_no_victim_fabrication": flow_live.get("no_victim_fabrication")
                    is True,
                    "live_flow_status_separation_documented": flow_live.get(
                        "status_separation_documented"
                    )
                    is True
                    and flow_live.get("no_unkeyed_grand_total") is True,
                    "live_flow_cancel_branch_recorded": cancel.get("branch")
                    in ("accepted", "refused"),
                    "live_flow_cancel_zero_artifacts": (
                        cancel.get("branch") != "accepted" or cancel.get("zero_artifacts") is True
                    ),
                    "live_flow_cancel_rerun_succeeded": (
                        cancel.get("branch") != "accepted"
                        or cancel.get("rerun_status") == "succeeded"
                    ),
                    "live_crosscase_job_succeeded": cross_live.get("job_status") == "succeeded",
                    "live_crosscase_candidates_exact": cross_live.get("candidate_keys_match")
                    is True
                    and cross_live.get("classifications_match") is True
                    and cross_live.get("sides_are_xy") is True,
                    "live_crosscase_decoys_absent": not cross_live.get("decoy_present"),
                    "live_crosscase_omission_no_z_side": (
                        cross_live.get("omission", {}).get("no_z_side") is True
                        and cross_live.get("omission", {}).get("z_strings_absent") is True
                    ),
                    "live_crosscase_scope_denied_no_leak": (
                        cross_live.get("scope_denied", {}).get("status_code") == 404
                        and cross_live.get("scope_denied", {}).get("code")
                        == "CROSS_CASE_SCOPE_DENIED"
                    ),
                    "live_crosscase_admin_sees_z_side": cross_live.get("admin_sees_z_side") is True,
                    "live_crosscase_hidden_artifact_explain_404": (
                        cross_live.get("hidden_artifact_explain", {}).get("status_code") == 404
                    ),
                    "live_crosscase_anon_401": (
                        cross_live.get("anon", {}).get("discover_status") == 401
                        and cross_live.get("anon", {}).get("candidates_status") == 401
                    ),
                    "live_crosscase_viewer_denied": (
                        cross_live.get("viewer", {}).get("discover_status") == 403
                        and cross_live.get("viewer", {}).get("discover_code")
                        == "INSUFFICIENT_PERMISSION"
                        and cross_live.get("viewer", {}).get("candidates_status") == 403
                        # Existing case, no membership: IDOR guard 403 (the
                        # viewer receives no case content either way).
                        and cross_live.get("viewer", {}).get("explain_status") == 403
                        and cross_live.get("viewer", {}).get(
                            "artifacts_on_inaccessible_case_status"
                        )
                        == 403
                        # Missing case: 404 (documented 404-missing /
                        # 403-IDOR split).
                        and cross_live.get("viewer", {}).get("artifacts_on_missing_case_status")
                        == 404
                    ),
                    "live_crosscase_name_only_approve_refused": (
                        cross_live.get("approval", {}).get("name_only_refusal", {}).get("attempted")
                        is True
                        and cross_live.get("approval", {})
                        .get("name_only_refusal", {})
                        .get("status_code")
                        == 409
                        and cross_live.get("approval", {}).get("name_only_refusal", {}).get("code")
                        == "ARTIFACT_NOT_REVIEWABLE"
                    ),
                    "live_crosscase_generic_list_omits_crosscase": (
                        cross_live.get("approval", {}).get("generic_list_omits_crosscase") is True
                    ),
                    "live_crosscase_approval_recorded": all(
                        (cross_live.get("approval") or {}).get(key) is True
                        for key in (
                            "child_recorded",
                            "parent_unrewritten",
                            "no_aliases_added",
                            "audit_row_recorded",
                        )
                    ),
                }
            )
        return gates

    async def _cleanup(self) -> None:
        """Remove everything this run created: objects, rows, temp account."""
        outcome: dict[str, Any] = {}
        from sqlalchemy import delete as sa_delete

        factory = self.database.session_factory()
        for label, case_id in list(self.case_ids.items()):
            case_uuid = uuid.UUID(case_id)
            try:
                outcome[f"{label}_objects_removed"] = await asyncio.to_thread(
                    self.storage.delete_case_objects, case_uuid
                )
                from app.models import AIConversation, AuditLog, Case, CaseMember

                async with factory() as session:
                    await session.execute(sa_delete(AuditLog).where(AuditLog.case_id == case_uuid))
                    await session.execute(
                        sa_delete(CaseMember).where(CaseMember.case_id == case_uuid)
                    )
                    await session.execute(
                        sa_delete(AIConversation).where(AIConversation.case_id == case_uuid)
                    )
                    await session.execute(sa_delete(Case).where(Case.id == case_uuid))
                    await session.commit()
                outcome[f"{label}_case_deleted"] = True
            except Exception as exc:  # noqa: BLE001 - cleanup is best-effort
                outcome[f"{label}_case_deleted"] = False
                outcome[f"{label}_error"] = str(exc)
                print(f"cleanup warning ({label}): {exc}", file=sys.stderr)

        if self._viewer_id is not None:
            try:
                suspend = await self.api.post(
                    f"/admin/users/{self._viewer_id}/suspend",
                    headers=self._headers(self.admin_token),
                )
                outcome["viewer_suspended"] = suspend.status_code == 200
                from app.models import AuditLog

                async with factory() as session:
                    await session.execute(
                        sa_delete(AuditLog).where(AuditLog.actor_id == uuid.UUID(self._viewer_id))
                    )
                    await session.commit()
            except Exception as exc:  # noqa: BLE001 - cleanup is best-effort
                outcome["viewer_cleanup_error"] = str(exc)
                print(f"cleanup warning (viewer): {exc}", file=sys.stderr)

        await self.database.close()
        self.storage.close()
        self.report["cleanup"] = outcome


def _adjacent(nodes: list[str], pair: list[str]) -> bool:
    return any(nodes[i : i + len(pair)] == pair for i in range(len(nodes)))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    parser.add_argument("--api-base", default=API_BASE_DEFAULT)
    parser.add_argument("--username", default="investigator")
    parser.add_argument("--password", default="investigator-dev-password")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--admin-password", default="admin-dev-password")
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="run only the deterministic golden-fixture metrics (no stack needed)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(Phase4EvalRunner(_parse_args(argv)).run())


if __name__ == "__main__":
    sys.exit(main())
