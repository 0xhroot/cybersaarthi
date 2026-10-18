"""Live + golden-fixture evaluation harness for phases 5-6.

Extends the Phase 1-4 harness conventions (``scripts/eval_model.py``,
``scripts/eval_evidence.py``, ``scripts/eval_phase3.py``,
``scripts/eval_phase4.py``: real HTTP, real auth, real local inference,
independent verification against PostgreSQL - never the server's self-report).

Current scope: **phase 5A multilingual complaint intelligence and phase 5B
digital forensics triage**. The AI report auditing (6) section is appended
when that phase lands; the entry point and report path already cover all
three.

The harness has two independent sections:

* **Deterministic golden-fixture metrics** (no stack required) - replays the
  frozen golden set (``multilingual_checks.json``) through the *pure* rule
  services and recomputes:

  - Unicode script profiles (exact character counts + derived candidate) from
    an independently hand-derived fixture, language/script cross-check exactness,
    ambiguity-flag exactness, negation detection (incl. Marathi), per-value
    source containment (false accepts and false rejects both reported and
    gated), instruction-context injection withholding (leaks and false
    withholdings both gated), translation material-preservation exactness with
    the ``total == preserved + missing`` invariant, model-output parse
    accept/reject exactness, anti-vacuous thresholds, and full determinism
    (two passes must be byte-identical).

  For the triage engine the frozen set (``triage_checks.json``) replays
  through the pure ``triage_contents`` engine and gates: structural profile
  counts, exact rule/severity/record-locator observation sets (including
  bounded details), benign no-over-fire, the typed no-structure refusal,
  instruction-injection containment, hash-manifest verdict matrices, auth-
  failure burst windows, explanation parse accept/reject and determinism.

* **Live end-to-end** (requires running stack + local model): real HTTP jobs
  against local Qwen3 - Hindi auto-translation run, Hindi + English runs with
  explicit translation, an unsupported-script refusal probe, a cancellation
  probe, an original-records viewer check, anonymous / non-member / cross-case
  IDOR probes, then an *independent* PostgreSQL re-read verifying every stored
  field value is anchored in the source record, every issue code is typed,
  profiles/flags/material checks/negation flags recompute exactly, locators
  resolve, API and database rows agree, nothing is auto-approved, and audit
  metadata stays counts and identifiers only (never complaint text). Per-run
  latency is measured.

  The triage live block uploads deceptive-URL evidence, a hash manifest with
  real stored objects (one matching, one tampered, one absent) and plain
  prose, runs the job against the local model, then independently recomputes
  every deterministic payload field from PostgreSQL records and verifies
  every manifest verdict by re-hashing the MinIO objects. Unsupported prose
  must be refused with ``TRIAGE_UNSUPPORTED_CONTENT`` and zero artifacts;
  nothing is auto-approved; a failed model explanation is never silent.

Deterministic safety properties are gated; model-dependent label choices
(language label, auto-translation trigger) are reported, never gated. All
harness-created rows (two synthetic cases, their evidence, one temporary
account) are deleted before exit.

Run via the entry point (loads the environment, checks both servers):

    ./scripts/ai/eval_phase567.sh

or directly from ``backend/``:

    .venv/bin/python -m scripts.eval_phase567 --report /tmp/p567.json
    .venv/bin/python -m scripts.eval_phase567 --skip-live   # golden only
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from app.core.config import get_settings
from app.core.enums import EvidenceFormat
from app.db.postgres import Database
from app.db.storage import Storage
from app.models import (
    AIConversation,
    AuditLog,
    Case,
    CaseMember,
    DerivedArtifact,
    EvidenceFile,
    SourceRecord,
)
from app.services.forensic_triage import (
    TRIAGE_RULES_VERSION,
    TriageRunError,
    _parse_explanation,
    _unit_content,
    auth_failure_burst,
    manifest_verdicts,
    triage_contents,
)
from app.services.multilingual import (
    _parse_analysis,
    ambiguity_flags,
    check_material_values,
    in_instruction_context,
    language_consistent,
    negation_present,
    profile_scripts,
    value_in_original,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "evidence_intelligence"
ML_FIXTURE = FIXTURE_DIR / "multilingual_checks.json"
TRIAGE_FIXTURE = FIXTURE_DIR / "triage_checks.json"
REPORT_DEFAULT = REPO_ROOT / "ai_runtime" / "eval_phase567_report.json"
API_BASE_DEFAULT = "http://localhost:8000/api/v1"

REQUEST_TIMEOUT_SECONDS = 240.0
JOB_POLL_TIMEOUT_SECONDS = 420.0
TERMINAL_JOB_STATES = {"succeeded", "partial", "failed", "canceled"}

# Synthetic complaints used only by the live section (no real personal data).
HINDI_AUTO = (
    "शिकायतकर्ता ने बताया कि उसने राहुल शर्मा को ५,००० रुपये नहीं दिए। "
    "भुगतान खाता संख्या ACC-7781 से किया गया। शिकायत दिनांक 01/02/2026 को दर्ज हुई।"
)
HINDI_TRANSLATED = (
    "मैंने कंपनी सूर्य ट्रेडर्स को १२,००० रुपये नहीं भेजे। राशि खाता ACC-2211 से कटी। "
    "शिकायत दिनांक 02/03/2026 को दर्ज हुई।"
)
ENGLISH_TEXT = (
    "I did not receive payment of 5,000.00 INR from Sunrise Traders on 01/02/2026. "
    "Account ACC-7781 was debited without my consent."
)
BENGALI_TEXT = "আমি টাকা পাইনি। অ্যাকাউন্ট ACC-7781 থেকে পেমেন্ট হয়েছে।"
CANCEL_PARAGRAPHS = [
    "पहला संदर्भ: शिकायतकर्ता का नाम अनिल कुमार है और उसने २,५०० रुपये खोए।",
    "दूसरा संदर्भ: कंपनी सूर्य ट्रेडर्स ने भुगतान वापस नहीं किया; खाता ACC-3344 का उपयोग हुआ।",
    "तीसरा संदर्भ: घटना 15/01/2026 को हुई और पुलिस में शिकायत दर्ज की गई।",
]
CANCEL_TEXT = "\n\n".join(CANCEL_PARAGRAPHS)
IDOR_TEXT = "IDOR probe file for the phase-5 evaluation (synthetic)."

# Synthetic triage evidence used only by the live section.
TRIAGE_URLS_TEXT = (
    "Visit log:\n"
    "http://paypal.com@evil.test/login\n"
    "https://192.168.10.5:8443/account/update\n"
    "https://xn--pypal-4ve.com/verify/session\n"
)
TRIAGE_PROSE = (
    "I ordered a laptop from an online seller on the marketplace. "
    "The seller stopped replying after I transferred the amount from my "
    "savings account. I want to know what can be done about the pending "
    "delivery and my money."
)

# Every validation-error code the multilingual services may record.
KNOWN_ISSUE_CODES = {
    "value_not_in_source",
    "value_in_injected_context",
    "material_value_missing",
    "negation_not_preserved",
    "unparseable_model_output",
}
# Audit metadata may carry counts plus the established identifier/status keys
# shared with the phase-2 extraction.submitted and the multi-feature cancel
# audit conventions - and never complaint content (enforced by the check).
AUDIT_COUNT_KEYS = {
    "units_total",
    "artifacts_created",
    "artifacts_reused",
    "artifacts_flagged",
    "artifacts_invalid",
    "translations_created",
    "language_ambiguous",
    "values_total",
    "values_verified",
    "values_withheld_injected",
    # triage (phase 5B) counts - integers only, like every key above
    "records_total",
    "records_scanned",
    "urls_analyzed",
    "observations_total",
    "manifest_entries_verified",
    "explanation_failed",
}
AUDIT_ALLOWED_KEYS = AUDIT_COUNT_KEYS | {
    "code",
    "denial",
    "stage",
    "evidence_file_id",
    "duplicate",
    "status",
}
AUDIT_TOKEN_RE = re.compile(r"^[A-Za-z_]{1,40}$")
AUDIT_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

LIMITATIONS = [
    "Triage never fetches, resolves or executes anything: URL observations "
    "are structural only (userinfo, raw-IP host, punycode, non-standard "
    "port) and cannot detect a malicious payload behind an innocent URL.",
    "Hash-manifest verification compares sha-256 of the filenames the "
    "manifest lists against the stored case objects; a renamed file, or a "
    "manifest that omits files, cannot be detected.",
    "The model's triage explanation is shape-validated and fenced to the "
    "recorded observations; a fluent but unsupported interpretation that "
    "passes the shape check stays pending_review for a human.",
    "Language identification is deterministic Unicode script profiling only; "
    "Devanagari cannot separate Hindi from Marathi, and no language library "
    "is installed (downloads are not permitted).",
    "Unsupported scripts are refused with a typed error before any model "
    "call: OCR and non-Indic script analysis are out of scope.",
    "Translation quality is checked for material values (numbers, dates, "
    "emails, account references) and negation markers; a fluent but "
    "semantically altered rendering that preserves those is not detectable "
    "deterministically and stays pending_review.",
    "Auto-translation on a translate=false run depends on the model's "
    "language label (unknown label + consistent script skips it); this "
    "outcome is reported live, never gated - the deterministic trigger "
    "rules are gated in the API test suite.",
    "The live model label and extraction contents are stochastic: gates "
    "cover only deterministic properties (source anchoring, typed issues, "
    "recompute exactness, refusal codes, authorization, review state).",
    "Cancellation is probed live for route/runner consistency but the exact "
    "terminal status depends on the race between the cancel flag and the "
    "runner's unit boundary; deterministic cancel semantics are covered by "
    "the API test suite.",
]


def _rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{numerator}/{denominator} ({numerator / denominator:.4f})"


def _record_text(raw: dict[str, Any]) -> str:
    """Mirror the deterministic TXT unit extraction for recompute checks."""
    text = raw.get("text")
    if isinstance(text, str):
        return text
    strings = [str(v) for v in raw.values() if isinstance(v, str)]
    if strings:
        return "\n".join(strings)
    return json.dumps(raw, ensure_ascii=False, default=str)


class Phase567EvalRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.api = httpx.AsyncClient(base_url=args.api_base, timeout=REQUEST_TIMEOUT_SECONDS)
        self.token: str | None = None
        self.admin_token: str | None = None
        self.settings = get_settings()
        self.database = Database(self.settings)
        self.storage = Storage(self.settings)
        self.case_ids: dict[str, str] = {}
        self.gates: dict[str, bool] = {}
        self.report: dict[str, Any] = {}
        self._outsider_id: str | None = None

    def _headers(self, token: str | None = None) -> dict[str, str]:
        effective = token if token is not None else self.token
        return {"Authorization": f"Bearer {effective}"} if effective else {}

    # -- deterministic golden-fixture metrics (no stack) --------------------

    @staticmethod
    def _golden_pass(fixture: dict[str, Any]) -> dict[str, Any]:
        problems: dict[str, list[str]] = {
            "profile": [],
            "language": [],
            "flags": [],
            "negation": [],
            "values": [],
            "instruction": [],
            "injection": [],
            "material": [],
            "parse": [],
        }
        values_n = 0
        values_real = 0
        values_fabricated = 0
        false_accepts = 0
        false_rejects = 0
        injection_n = 0
        withheld_expected = 0
        withheld_detected = 0
        flagged_cases_n = 0
        candidates_seen: set[str] = set()

        for case in fixture["complaints"]:
            label = case["label"]
            text = case["text"]
            expect = case["expect"]
            profile = profile_scripts(text)
            candidates_seen.add(str(profile.get("candidate")))
            if profile.get("candidate") != expect["candidate"]:
                problems["profile"].append(
                    f"{label}: candidate {profile.get('candidate')!r} != {expect['candidate']!r}"
                )
            for key, want in expect["counts"].items():
                if profile.get(key) != want:
                    problems["profile"].append(f"{label}.{key}: {profile.get(key)!r} != {want!r}")
            if negation_present(text) != expect["negation"]:
                problems["negation"].append(
                    f"{label}: negation {negation_present(text)} != {expect['negation']}"
                )
            flags = [f["flag"] for f in ambiguity_flags(text)]
            if flags != expect["ambiguity_flags"]:
                problems["flags"].append(f"{label}: flags {flags} != {expect['ambiguity_flags']}")
            if flags:
                flagged_cases_n += 1
            for model_label, want in expect["language_consistent"].items():
                got = language_consistent(profile, model_label)
                if got != want:
                    problems["language"].append(
                        f"{label}/{model_label}: consistent {got} != {want}"
                    )
            for spec in expect["values"]:
                values_n += 1
                want_in = bool(spec["in_source"])
                got_in = value_in_original(spec["value"], text)
                if want_in:
                    values_real += 1
                else:
                    values_fabricated += 1
                if got_in != want_in:
                    if got_in:
                        false_accepts += 1
                    else:
                        false_rejects += 1
                    problems["values"].append(
                        f"{label}: {spec['value']!r} in_source {got_in} != {want_in}"
                    )
                want_ctx = bool(spec["instruction_context"])
                got_ctx = in_instruction_context(spec["value"], text)
                if got_ctx != want_ctx:
                    problems["instruction"].append(
                        f"{label}: {spec['value']!r} context {got_ctx} != {want_ctx}"
                    )

        for case in fixture["injections"]:
            injection_n += 1
            label = case["label"]
            source = case["source"]
            value = case["value"]
            expect = case["expect"]
            if value_in_original(value, source) != bool(expect["in_source"]):
                problems["injection"].append(f"{label}: source-containment mismatch for {value!r}")
            withheld = in_instruction_context(value, source)
            if expect["withheld"]:
                withheld_expected += 1
                if not withheld:
                    problems["injection"].append(
                        f"{label}: INJECTION LEAK - {value!r} not withheld"
                    )
            elif withheld:
                problems["injection"].append(
                    f"{label}: legitimate value {value!r} wrongly withheld"
                )
            if withheld:
                withheld_detected += 1

        complaints_by_label = {c["label"]: c["text"] for c in fixture["complaints"]}
        translations_n = 0
        preserved_n = 0
        lossy_n = 0
        invariant_problems = 0
        for case in fixture["translations"]:
            translations_n += 1
            label = case["label"]
            original = complaints_by_label[case["original_ref"]]
            translated = case["translated"]
            expect = case["expect"]
            result = check_material_values(original, translated)
            if result["preserved"] != expect["preserved"]:
                problems["material"].append(
                    f"{label}: preserved {result['preserved']} != {expect['preserved']}"
                )
            if result["material_missing"] != expect["material_missing"]:
                problems["material"].append(
                    f"{label}: missing {result['material_missing']} != {expect['material_missing']}"
                )
            neg_ok = (not negation_present(original)) or negation_present(translated)
            if neg_ok != expect["negation_ok"]:
                problems["material"].append(
                    f"{label}: negation_ok {neg_ok} != {expect['negation_ok']}"
                )
            if result["material_total"] != (
                result["material_preserved"] + len(result["material_missing"])
            ):
                invariant_problems += 1
                problems["material"].append(f"{label}: material_total != preserved + missing")
            if result["preserved"]:
                preserved_n += 1
            else:
                lossy_n += 1

        parse_n = 0
        for payload in fixture["parse"]["reject"]:
            parse_n += 1
            if _parse_analysis(payload) is not None:
                problems["parse"].append(f"accepted unparseable payload: {payload!r}")
        for payload in fixture["parse"]["accept"]:
            parse_n += 1
            if _parse_analysis(payload) is None:
                problems["parse"].append(f"rejected valid payload: {payload!r}")

        values_true_positive = values_real - false_rejects
        return {
            "problems": problems,
            "complaints_n": len(fixture["complaints"]),
            "candidates_seen": sorted(candidates_seen),
            "flagged_cases_n": flagged_cases_n,
            "values_n": values_n,
            "values_real_n": values_real,
            "values_fabricated_n": values_fabricated,
            "values_false_accepts": false_accepts,
            "values_false_rejects": false_rejects,
            "value_precision": _rate(values_true_positive, values_true_positive + false_accepts),
            "value_recall": _rate(values_true_positive, values_true_positive + false_rejects),
            "injection_n": injection_n,
            "injection_withheld_expected": withheld_expected,
            "injection_withheld_detected": withheld_detected,
            "translations_n": translations_n,
            "translations_preserved_n": preserved_n,
            "translations_lossy_n": lossy_n,
            "material_invariant_problems": invariant_problems,
            "parse_n": parse_n,
            "problems_total": sum(len(v) for v in problems.values()),
        }

    @staticmethod
    def _triage_golden_pass(fixture: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        problems: dict[str, list[str]] = {
            "profile": [],
            "observations": [],
            "missing": [],
            "refusal": [],
            "injection": [],
            "manifest": [],
            "burst": [],
            "explanation": [],
        }
        rules_seen: set[str] = set()
        benign_n = 0
        refusal_n = 0
        injection_n = 0
        manifest_cases_n = 0

        for case in fixture["cases"]:
            name = str(case["name"])
            expect = case["expect"]
            supported = bool(expect["supported"])
            contents: list[tuple[SourceRecord, str]] = []
            for rec in case["records"]:
                if "text" in rec:
                    raw_data: dict[str, Any] = {"text": rec["text"]}
                    text = str(rec["text"])
                else:
                    raw_data = dict(rec["row"])
                    text = "\n".join(str(v) for v in raw_data.values() if isinstance(v, str))
                contents.append(
                    (
                        SourceRecord(
                            evidence_file_id="eval-triage",
                            record_no=int(rec["record_no"]),
                            raw_data=raw_data,
                        ),
                        text,
                    )
                )
            try:
                result = triage_contents(contents, settings=settings)
            except TriageRunError as exc:
                result = None
                if supported:
                    problems["refusal"].append(f"{name}: expected support, got refusal {exc.code}")
                elif exc.code != str(expect.get("error_code") or ""):
                    problems["refusal"].append(
                        f"{name}: refusal code {exc.code} != {expect.get('error_code')}"
                    )
                else:
                    refusal_n += 1
            if result is None:
                continue
            if not supported:
                problems["refusal"].append(f"{name}: expected refusal, analysis succeeded")
                continue
            profile = result["profile"]
            if dict(profile) != dict(expect["profile"]):
                problems["profile"].append(
                    f"{name}: profile {dict(profile)!r} != {dict(expect['profile'])!r}"
                )
            want_obs = list(expect.get("observations") or [])
            got_obs = list(result["observations"])
            if len(got_obs) != len(want_obs):
                problems["observations"].append(
                    f"{name}: {len(got_obs)} observations != {len(want_obs)} expected"
                )
            for index, want in enumerate(want_obs):
                if index >= len(got_obs):
                    break
                got = got_obs[index]
                if (
                    got["rule"] != want["rule"]
                    or got["severity"] != want["severity"]
                    or got["locator"]["record_no"] != want["record_no"]
                ):
                    problems["observations"].append(
                        f"{name}[{index}]: got rule={got['rule']} severity={got['severity']} "
                        f"record_no={got['locator']['record_no']} != want {want!r}"
                    )
                if "detail" in want and got.get("detail") != want["detail"]:
                    problems["observations"].append(
                        f"{name}[{index}]: detail {got.get('detail')!r} != {want['detail']!r}"
                    )
            rules_seen.update(str(o["rule"]) for o in got_obs)
            if list(result["missing_information"]) != list(expect.get("missing_information") or []):
                problems["missing"].append(
                    f"{name}: missing_information {result['missing_information']!r} "
                    f"!= {expect.get('missing_information')!r}"
                )
            if not got_obs:
                benign_n += 1
            forbidden = [str(x) for x in expect.get("injection_forbidden") or []]
            if forbidden:
                injection_n += 1
                blob = json.dumps(got_obs, ensure_ascii=False)
                for needle in forbidden:
                    if needle in blob:
                        problems["injection"].append(
                            f"{name}: forbidden text {needle[:40]!r} leaked into observations"
                        )
            if expect.get("fields_manifest_is_null"):
                manifest_cases_n += 1
                if result["fields"]["manifest"] is not None:
                    problems["manifest"].append(
                        f"{name}: pure stage must leave fields.manifest null"
                    )

        for section in fixture.get("manifest_verdicts", []):
            verdicts = manifest_verdicts(section["entries"], section["available"])
            got = [v["verdict"] for v in verdicts]
            if got != section["expect"]:
                problems["manifest"].append(
                    f"{section['name']}: verdicts {got!r} != {section['expect']!r}"
                )

        burst_cases_n = 0
        for section in fixture.get("bursts", []):
            burst_cases_n += 1
            result = auth_failure_burst(
                section["events"],
                threshold=int(section.get("threshold", 5)),
                window_seconds=int(section.get("window_seconds", 600)),
            )
            expect = section["expect"]
            if expect is None:
                if result is not None:
                    problems["burst"].append(
                        f"{section['name']}: expected no burst, got {result!r}"
                    )
            elif result is None or any(result.get(k) != v for k, v in expect.items()):
                problems["burst"].append(f"{section['name']}: {result!r} != {expect!r}")

        for section in fixture.get("explanations", []):
            accepted = _parse_explanation(section["text"]) is not None
            if accepted != bool(section["accept"]):
                problems["explanation"].append(
                    f"{section['name']}: accepted={accepted} != {section['accept']}"
                )

        return {
            "problems": problems,
            "cases_n": len(fixture["cases"]),
            "rules_seen": sorted(rules_seen),
            "benign_n": benign_n,
            "refusal_n": refusal_n,
            "injection_n": injection_n,
            "manifest_cases_n": manifest_cases_n,
            "burst_cases_n": burst_cases_n,
            "problems_total": sum(len(v) for v in problems.values()),
        }

    def _golden_section(self) -> dict[str, Any]:
        print("  golden: multilingual complaint intelligence", flush=True)
        fixture = json.loads(ML_FIXTURE.read_text(encoding="utf-8"))
        first = self._golden_pass(fixture)
        second = self._golden_pass(fixture)
        first["determinism_ok"] = json.dumps(
            first, sort_keys=True, ensure_ascii=False
        ) == json.dumps(second, sort_keys=True, ensure_ascii=False)
        print("  golden: digital forensics triage", flush=True)
        triage_fixture = json.loads(TRIAGE_FIXTURE.read_text(encoding="utf-8"))
        triage_first = self._triage_golden_pass(triage_fixture)
        triage_second = self._triage_golden_pass(triage_fixture)
        triage_first["determinism_ok"] = json.dumps(
            triage_first, sort_keys=True, ensure_ascii=False
        ) == json.dumps(triage_second, sort_keys=True, ensure_ascii=False)
        return {
            "multilingual": first,
            "fixture": str(ML_FIXTURE.relative_to(REPO_ROOT)),
            "fixture_limitations": fixture.get("limitations", []),
            "triage": triage_first,
            "triage_fixture": str(TRIAGE_FIXTURE.relative_to(REPO_ROOT)),
            "triage_fixture_limitations": triage_fixture.get("limitations", []),
        }

    # -- live end-to-end section ---------------------------------------------

    async def _login(self, username: str, password: str) -> str:
        response = await self.api.post(
            "/auth/login", json={"username": username, "password": password}
        )
        response.raise_for_status()
        return response.json()["access_token"]

    async def ai_ready(self) -> bool:
        response = await self.api.get("/ai/status", headers=self._headers())
        if response.status_code != 200:
            return False
        return bool(response.json().get("ready"))

    async def _create_case(self, title: str, description: str) -> str:
        response = await self.api.post(
            "/cases",
            json={"title": title, "description": description},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()["id"]

    async def _upload_text(self, case_id: str, name: str, text: str) -> str:
        payload = text.encode("utf-8")
        response = await self.api.post(
            f"/cases/{case_id}/evidence",
            files={"file": (name, payload, "text/plain")},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()["id"]

    async def _poll_job(self, case_id: str, job_id: str, *, feature: str) -> dict[str, Any]:
        deadline = time.monotonic() + JOB_POLL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            response = await self.api.get(
                f"/cases/{case_id}/evidence-intelligence/jobs",
                params={"feature": feature},
                headers=self._headers(),
            )
            response.raise_for_status()
            for item in response.json()["items"]:
                if item["id"] == job_id and item["status"] in TERMINAL_JOB_STATES:
                    return item
            await asyncio.sleep(1.0)
        raise TimeoutError(f"{feature} job {job_id} did not reach a terminal state")

    async def _run_job(self, case_id: str, evidence_id: str, *, translate: bool) -> dict[str, Any]:
        submitted = time.monotonic()
        response = await self.api.post(
            f"/cases/{case_id}/evidence-intelligence/multilingual",
            json={"evidence_file_id": evidence_id, "translate": translate},
            headers=self._headers(),
        )
        response.raise_for_status()
        body = response.json()
        job_id = (body.get("job") or {}).get("id")
        if not job_id:
            raise RuntimeError(f"multilingual submit returned no job id: {body!r}")
        job = await self._poll_job(case_id, job_id, feature="multilingual")
        return {
            "job_id": job_id,
            "duplicate": body.get("duplicate"),
            "translate_requested": translate,
            "status": job["status"],
            "error": job.get("error"),
            "summary": job.get("result_summary"),
            "latency_seconds": round(time.monotonic() - submitted, 3),
        }

    async def _upload_bytes(self, case_id: str, name: str, data: bytes) -> str:
        response = await self.api.post(
            f"/cases/{case_id}/evidence",
            files={"file": (name, data, "text/plain")},
            headers=self._headers(),
        )
        response.raise_for_status()
        return str(response.json()["id"])

    async def _run_triage_job(self, case_id: str, evidence_id: str) -> dict[str, Any]:
        submitted = time.monotonic()
        response = await self.api.post(
            f"/cases/{case_id}/evidence-intelligence/triage",
            json={"evidence_file_id": evidence_id},
            headers=self._headers(),
        )
        if response.status_code != 202:
            return {
                "status": f"http_{response.status_code}",
                "error": response.text[:200],
                "summary": None,
                "latency_seconds": 0.0,
            }
        body = response.json()
        job_id = (body.get("job") or {}).get("id")
        if not job_id:
            raise RuntimeError(f"triage submit returned no job id: {body!r}")
        job = await self._poll_job(case_id, job_id, feature="triage")
        return {
            "status": job["status"],
            "error": job.get("error"),
            "summary": job.get("result_summary"),
            "latency_seconds": round(time.monotonic() - submitted, 3),
        }

    async def _db_case_evidence(self, case_id: str) -> list[EvidenceFile]:
        from sqlalchemy import select

        factory = self.database.session_factory()
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(EvidenceFile)
                        .where(EvidenceFile.case_id == uuid.UUID(case_id))
                        .where(EvidenceFile.deleted_at.is_(None))
                        .order_by(EvidenceFile.created_at)
                    )
                )
                .scalars()
                .all()
            )
        return list(rows)

    async def _artifacts(self, case_id: str, kind: str) -> list[dict[str, Any]]:
        response = await self.api.get(
            f"/cases/{case_id}/evidence-intelligence/artifacts",
            params={"kind": kind},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()["items"]

    async def _db_artifacts(self, case_id: str) -> list[DerivedArtifact]:
        from sqlalchemy import select

        factory = self.database.session_factory()
        async with factory() as session:
            result = await session.execute(
                select(DerivedArtifact)
                .where(DerivedArtifact.case_id == str(case_id))
                .order_by(DerivedArtifact.created_at, DerivedArtifact.id)
            )
            return list(result.scalars())

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

    async def _cancel_probe(self, case_id: str, evidence_id: str) -> dict[str, Any]:
        submitted = time.monotonic()
        response = await self.api.post(
            f"/cases/{case_id}/evidence-intelligence/multilingual",
            json={"evidence_file_id": evidence_id, "translate": False},
            headers=self._headers(),
        )
        response.raise_for_status()
        job_id = (response.json().get("job") or {}).get("id")
        if not job_id:
            raise RuntimeError("multilingual cancel submit returned no job id")
        cancel = await self.api.post(
            f"/cases/{case_id}/evidence-intelligence/jobs/{job_id}/cancel",
            headers=self._headers(),
        )
        code = cancel.status_code
        job = await self._poll_job(case_id, job_id, feature="multilingual")
        final = job["status"]
        if code == 200:
            consistent = final in {"canceled", "succeeded", "partial"}
        elif code == 409:
            consistent = final in {"succeeded", "partial", "failed"}
        else:
            consistent = False
        return {
            "cancel_status_code": code,
            "cancel_body_code": (
                (cancel.json().get("error") or {}).get("code") if code >= 400 else None
            ),
            "final_status": final,
            "cancel_requested": job.get("cancel_requested"),
            "latency_seconds": round(time.monotonic() - submitted, 3),
            "consistent": consistent,
        }

    async def _authz_probes(
        self, case_id: str, idor_case: str, ev_case: str, ev_idor: str
    ) -> dict[str, Any]:
        """Anonymous / non-member / cross-case probes (fail closed, no oracles)."""
        probe: dict[str, Any] = {}

        anon_submit = await self.api.post(
            f"/cases/{case_id}/evidence-intelligence/multilingual",
            json={"evidence_file_id": ev_case, "translate": False},
        )
        anon_records = await self.api.get(f"/cases/{case_id}/evidence/{ev_case}/records")
        probe["anonymous_submit_status"] = anon_submit.status_code
        probe["anonymous_records_status"] = anon_records.status_code

        # Temporary non-member INVESTIGATOR (has ingestion.run, no case access).
        suffix = uuid.uuid4().hex[:8]
        username = f"ph567_outsider_{suffix}"
        register = await self.api.post(
            "/auth/register",
            json={
                "username": username,
                "email": f"{username}@eval.invalid",
                "password": "outsider-eval-password-1",
            },
        )
        register.raise_for_status()
        self._outsider_id = register.json()["user"]["id"]
        approve = await self.api.post(
            f"/admin/users/{self._outsider_id}/approve",
            json={"role": "INVESTIGATOR"},
            headers=self._headers(self.admin_token),
        )
        approve.raise_for_status()
        outsider_token = await self._login(username, "outsider-eval-password-1")

        out_submit = await self.api.post(
            f"/cases/{case_id}/evidence-intelligence/multilingual",
            json={"evidence_file_id": ev_case, "translate": False},
            headers=self._headers(outsider_token),
        )
        out_artifacts = await self.api.get(
            f"/cases/{case_id}/evidence-intelligence/artifacts",
            params={"kind": "extraction"},
            headers=self._headers(outsider_token),
        )
        out_records = await self.api.get(
            f"/cases/{case_id}/evidence/{ev_case}/records",
            headers=self._headers(outsider_token),
        )
        probe["outsider_submit_status"] = out_submit.status_code
        probe["outsider_artifacts_status"] = out_artifacts.status_code
        probe["outsider_records_status"] = out_records.status_code
        leak_blobs = [
            out_submit.text.lower(),
            out_artifacts.text.lower(),
            out_records.text.lower(),
        ]
        secrets_of_content = [
            HINDI_AUTO[:24].lower(),
            ENGLISH_TEXT[:24].lower(),
            "phase-5 multilingual eval",
        ]
        probe["outsider_leak"] = any(
            secret in blob for blob in leak_blobs for secret in secrets_of_content
        )

        # Cross-case IDOR: foreign evidence must behave byte-for-byte like a
        # nonexistent id (same 404, same code, body equal after removing the
        # client-supplied id) - an existence oracle would distinguish them.
        idor_forward = await self.api.get(
            f"/cases/{idor_case}/evidence/{ev_case}/records",
            headers=self._headers(),
        )
        idor_back = await self.api.get(
            f"/cases/{case_id}/evidence/{ev_idor}/records",
            headers=self._headers(),
        )
        missing_ev = str(uuid.uuid4())
        idor_missing = await self.api.get(
            f"/cases/{case_id}/evidence/{missing_ev}/records",
            headers=self._headers(),
        )
        probe["idor_forward_status"] = idor_forward.status_code
        probe["idor_back_status"] = idor_back.status_code
        probe["idor_missing_status"] = idor_missing.status_code

        def _error_code(response: httpx.Response) -> str | None:
            try:
                return str(response.json()["error"]["code"])
            except Exception:  # noqa: BLE001 - malformed body reported as a problem
                return None

        def _normalized(response: httpx.Response, probed_id: str) -> str | None:
            try:
                return json.dumps(response.json()).replace(probed_id, "<id>")
            except Exception:  # noqa: BLE001 - malformed body reported as a problem
                return None

        codes = [
            _error_code(idor_forward),
            _error_code(idor_back),
            _error_code(idor_missing),
        ]
        bodies = [
            _normalized(idor_forward, ev_case),
            _normalized(idor_back, ev_idor),
            _normalized(idor_missing, missing_ev),
        ]
        probe["idor_codes"] = codes
        probe["idor_no_oracle"] = all(
            code is not None and code == codes[0] for code in codes
        ) and all(body is not None and body == bodies[0] for body in bodies)
        return probe

    async def _audit_metadata_check(self, case_id: str) -> dict[str, Any]:
        from sqlalchemy import or_, select

        factory = self.database.session_factory()
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditLog)
                        .where(AuditLog.case_id == uuid.UUID(case_id))
                        .where(
                            or_(
                                AuditLog.action.like("multilingual.%"),
                                AuditLog.action.like("triage.%"),
                            )
                        )
                        .order_by(AuditLog.created_at)
                    )
                )
                .scalars()
                .all()
            )
        problems: list[str] = []
        actions: list[str] = []
        # Structural rule (typed keys and typed values) plus an explicit
        # content rule: no metadata string may be a word from any complaint.
        complaint_words: set[str] = set()
        for text in (
            HINDI_AUTO,
            HINDI_TRANSLATED,
            ENGLISH_TEXT,
            BENGALI_TEXT,
            CANCEL_TEXT,
            IDOR_TEXT,
            TRIAGE_URLS_TEXT,
            TRIAGE_PROSE,
        ):
            complaint_words |= {w.lower() for w in re.findall(r"\w+", text) if len(w) >= 4}
        for row in rows:
            actions.append(row.action)
            metadata = dict(row.metadata_ or {})
            extra_keys = set(metadata) - AUDIT_ALLOWED_KEYS
            if extra_keys:
                problems.append(f"{row.action}: unexpected keys {sorted(extra_keys)}")
            for key, value in metadata.items():
                if isinstance(value, bool) or isinstance(value, int):
                    continue
                if isinstance(value, str):
                    if not (AUDIT_UUID_RE.match(value) or AUDIT_TOKEN_RE.match(value)):
                        problems.append(f"{row.action}: untyped metadata value for {key!r}")
                        continue
                    if len(value) >= 4 and value.lower() in complaint_words:
                        problems.append(
                            f"{row.action}: complaint text in metadata value for {key!r}"
                        )
                    continue
                problems.append(f"{row.action}: value of {key!r} has type {type(value).__name__}")
        return {"rows_n": len(rows), "actions": actions, "problems": problems}

    async def _live_section(self) -> dict[str, Any]:
        live: dict[str, Any] = {
            "checks": {},
            "problems": [],
            "runs": {},
            "reports": {},
        }
        case_id = await self._create_case(
            "phase-5 multilingual eval (synthetic)",
            "created and deleted by scripts/eval_phase567.py",
        )
        self.case_ids["ml"] = case_id
        idor_case = await self._create_case(
            "phase-5 idor probe (synthetic)",
            "created and deleted by scripts/eval_phase567.py",
        )
        self.case_ids["idor"] = idor_case
        print(f"  live: multilingual case {case_id}", flush=True)

        ev_auto = await self._upload_text(case_id, "phase5-hindi-auto.txt", HINDI_AUTO)
        ev_trans = await self._upload_text(case_id, "phase5-hindi-translate.txt", HINDI_TRANSLATED)
        ev_en = await self._upload_text(case_id, "phase5-english.txt", ENGLISH_TEXT)
        ev_bn = await self._upload_text(case_id, "phase5-bengali.txt", BENGALI_TEXT)
        ev_cancel = await self._upload_text(case_id, "phase5-cancel.txt", CANCEL_TEXT)
        ev_z = await self._upload_text(idor_case, "phase5-idor.txt", IDOR_TEXT)

        # Real HTTP runs against the local model.
        runs = {
            "hindi_auto": await self._run_job(case_id, ev_auto, translate=False),
            "hindi_translate": await self._run_job(case_id, ev_trans, translate=True),
            "english_translate": await self._run_job(case_id, ev_en, translate=True),
            "unsupported_script": await self._run_job(case_id, ev_bn, translate=False),
        }
        for label, run in runs.items():
            print(
                f"    run {label}: {run['status']} in {run['latency_seconds']}s",
                flush=True,
            )
        live["runs"] = runs
        live["latency_seconds"] = {label: run["latency_seconds"] for label, run in runs.items()}

        live["reports"]["cancel_probe"] = await self._cancel_probe(case_id, ev_cancel)

        # API-side artifacts.
        api_ext = await self._artifacts(case_id, "extraction")
        api_tr = await self._artifacts(case_id, "translation")
        multilingual_evidence = {ev_auto, ev_trans, ev_en}
        ml_ext = [
            a
            for a in api_ext
            if a.get("evidence_file_id") in multilingual_evidence
            and (a.get("payload") or {}).get("multilingual") is True
        ]
        ml_tr = [a for a in api_tr if a.get("evidence_file_id") in multilingual_evidence]
        bn_artifacts = [a for a in api_ext + api_tr if a.get("evidence_file_id") == ev_bn]
        ext_by_ev: dict[str, int] = {}
        for a in ml_ext:
            ext_by_ev[a["evidence_file_id"]] = ext_by_ev.get(a["evidence_file_id"], 0) + 1
        tr_by_ev: dict[str, int] = {}
        for a in ml_tr:
            tr_by_ev[a["evidence_file_id"]] = tr_by_ev.get(a["evidence_file_id"], 0) + 1

        checks = live["checks"]
        checks["hindi_auto_run_ok"] = (
            runs["hindi_auto"]["status"] in {"succeeded", "partial"}
            and ext_by_ev.get(ev_auto, 0) >= 1
        )
        checks["hindi_translate_run_ok"] = (
            runs["hindi_translate"]["status"] in {"succeeded", "partial"}
            and ext_by_ev.get(ev_trans, 0) >= 1
        )
        checks["english_run_ok"] = (
            runs["english_translate"]["status"] in {"succeeded", "partial"}
            and ext_by_ev.get(ev_en, 0) >= 1
        )
        checks["translation_recorded"] = (
            tr_by_ev.get(ev_trans, 0) >= 1 and tr_by_ev.get(ev_en, 0) >= 1
        )
        run_d = runs["unsupported_script"]
        checks["unsupported_script_refused"] = (
            run_d["status"] == "failed"
            and str(run_d.get("error") or "").startswith("LANGUAGE_UNSUPPORTED")
            and not bn_artifacts
        )
        checks["no_auto_approval"] = all(
            a.get("status") == "pending_review" for a in ml_ext + ml_tr
        ) and bool(ml_ext)
        live["reports"]["auto_translation_fired"] = tr_by_ev.get(ev_auto, 0) >= 1
        live["reports"]["model_labels"] = sorted(
            {
                str((a.get("payload") or {}).get("language"))
                for a in ml_ext
                if (a.get("payload") or {}).get("language")
            }
        )

        # Independent PostgreSQL re-read: every stored claim recomputes.
        db_artifacts = await self._db_artifacts(case_id)
        db_by_id = {str(a.id): a for a in db_artifacts}
        db_records = await self._db_case_records(case_id)
        record_by_id = {str(r.id): r for r in db_records}

        api_db_problems: list[str] = []
        for api_art in ml_ext + ml_tr:
            row = db_by_id.get(str(api_art["id"]))
            if row is None:
                api_db_problems.append(f"artifact {api_art['id']} missing in PostgreSQL")
                continue
            if dict(row.payload or {}) != dict(api_art.get("payload") or {}):
                api_db_problems.append(f"artifact {api_art['id']} payload API != DB")
            if row.status != api_art.get("status"):
                api_db_problems.append(f"artifact {api_art['id']} status API != DB")
            if row.validation_status != api_art.get("validation_status"):
                api_db_problems.append(f"artifact {api_art['id']} validation_status API != DB")
        checks["db_matches_api"] = not api_db_problems and bool(ml_ext)
        live["problems"].extend(api_db_problems)

        anchor_problems: list[str] = []
        code_problems: list[str] = []
        profile_problems: list[str] = []
        language_problems: list[str] = []
        flags_problems: list[str] = []
        locator_problems: list[str] = []
        translation_problems: list[str] = []
        values_checked = 0

        for api_art in ml_ext:
            row = db_by_id.get(str(api_art["id"]))
            if row is None:
                continue
            payload: dict[str, Any] = dict(row.payload or {})
            record = record_by_id.get(str(row.source_record_id) or "")
            if record is None:
                anchor_problems.append(f"artifact {row.id}: source record missing")
                continue
            text = _record_text(dict(record.raw_data or {}))
            for field, values in (payload.get("fields") or {}).items():
                for value in values or []:
                    values_checked += 1
                    if not value_in_original(str(value), text):
                        anchor_problems.append(
                            f"artifact {row.id}/{field}: {str(value)[:60]!r} "
                            "not anchored in source record"
                        )
            for issue in row.validation_errors or []:
                code = (issue or {}).get("code")
                if code not in KNOWN_ISSUE_CODES:
                    code_problems.append(f"artifact {row.id}: unknown issue code {code!r}")
            if payload.get("script_profile") != profile_scripts(text):
                profile_problems.append(f"artifact {row.id}: script profile mismatch")
            recomputed_flag = language_consistent(
                profile_scripts(text), str(payload.get("language") or "unknown")
            )
            if payload.get("language_consistent") != recomputed_flag:
                language_problems.append(f"artifact {row.id}: language flag mismatch")
            if payload.get("ambiguity_flags") != ambiguity_flags(text):
                flags_problems.append(f"artifact {row.id}: ambiguity flags mismatch")
            locator = dict(row.source_locator or {})
            if locator.get("record_no") != record.record_no:
                locator_problems.append(f"artifact {row.id}: locator record_no invalid")

        for api_art in ml_tr:
            row = db_by_id.get(str(api_art["id"]))
            if row is None:
                continue
            payload = dict(row.payload or {})
            record = record_by_id.get(str(row.source_record_id) or "")
            if record is None:
                translation_problems.append(f"artifact {row.id}: source record missing")
                continue
            text = _record_text(dict(record.raw_data or {}))
            translated = str(payload.get("translated_text") or "")
            if payload.get("material_check") != check_material_values(text, translated):
                translation_problems.append(f"artifact {row.id}: material check does not recompute")
            expected_neg = (not negation_present(text)) or negation_present(translated)
            if payload.get("negation_preserved") != expected_neg:
                translation_problems.append(f"artifact {row.id}: negation flag does not recompute")

        checks["values_source_anchored"] = not anchor_problems and values_checked >= 1
        checks["issue_codes_known"] = not code_problems
        checks["script_profile_recompute_exact"] = not profile_problems and bool(ml_ext)
        checks["language_flag_recompute_exact"] = not language_problems and bool(ml_ext)
        checks["ambiguity_flags_recompute_exact"] = not flags_problems and bool(ml_ext)
        checks["locator_validity"] = not locator_problems and bool(ml_ext)
        checks["translation_recompute_exact"] = not translation_problems and len(ml_tr) >= 2
        live["reports"]["values_checked_live"] = values_checked
        live["problems"].extend(
            anchor_problems
            + code_problems
            + profile_problems
            + language_problems
            + flags_problems
            + locator_problems
            + translation_problems
        )

        # Original-records viewer returns the source verbatim.
        records_resp = await self.api.get(
            f"/cases/{case_id}/evidence/{ev_auto}/records",
            headers=self._headers(),
        )
        verbatim = False
        if records_resp.status_code == 200:
            items = records_resp.json().get("items") or []
            first_text = ((items[0].get("raw_data") or {}).get("text")) if items else None
            verbatim = isinstance(first_text, str) and first_text.strip() == HINDI_AUTO.strip()
        checks["records_endpoint_verbatim"] = verbatim

        # Authorization / IDOR probes.
        live["reports"]["authz"] = await self._authz_probes(case_id, idor_case, ev_auto, ev_z)
        authz = live["reports"]["authz"]
        checks["authz_anonymous_401"] = (
            authz["anonymous_submit_status"] == 401 and authz["anonymous_records_status"] == 401
        )
        checks["authz_non_member_403"] = (
            authz["outsider_submit_status"] == 403
            and authz["outsider_artifacts_status"] == 403
            and authz["outsider_records_status"] == 403
            and not authz["outsider_leak"]
        )
        checks["records_idor_404"] = (
            authz["idor_forward_status"] == 404
            and authz["idor_back_status"] == 404
            and authz["idor_missing_status"] == 404
            and authz["idor_no_oracle"]
        )

        # Cancellation + audit metadata.
        checks["cancel_probe_consistent"] = live["reports"]["cancel_probe"]["consistent"]

        # ---- digital forensics triage (5B) -------------------------------
        target_bytes = b"chain of custody target bytes"
        sha_target = hashlib.sha256(target_bytes).hexdigest()
        await self._upload_bytes(case_id, "phase5b-target.txt", target_bytes)
        await self._upload_bytes(case_id, "phase5b-other.txt", b"unrelated other bytes")
        manifest_text = (
            f"phase5b-target.txt {sha_target}\n\n"  # matches stored bytes -> match
            f"phase5b-other.txt {sha_target}\n\n"  # exists, bytes differ -> mismatch
            f"phase5b-absent.txt {sha_target}\n\n"  # no such file -> missing
        )
        ev_triage = await self._upload_text(case_id, "phase5b-triage-urls.txt", TRIAGE_URLS_TEXT)
        ev_manifest = await self._upload_text(case_id, "phase5b-manifest.txt", manifest_text)
        ev_prose = await self._upload_text(case_id, "phase5b-prose.txt", TRIAGE_PROSE)

        runs_t = {
            "triage_urls": await self._run_triage_job(case_id, ev_triage),
            "triage_manifest": await self._run_triage_job(case_id, ev_manifest),
            "triage_unsupported": await self._run_triage_job(case_id, ev_prose),
        }
        for label, run in runs_t.items():
            print(
                f"    run {label}: {run['status']} in {run['latency_seconds']}s",
                flush=True,
            )
        live["runs"].update(runs_t)
        live["latency_seconds"].update(
            {label: run["latency_seconds"] for label, run in runs_t.items()}
        )

        triage_api = await self._artifacts(case_id, "triage_observation")
        triage_by_ev = {str(a.get("evidence_file_id")): a for a in triage_api}
        triage_url_art = triage_by_ev.get(ev_triage)
        triage_manifest_art = triage_by_ev.get(ev_manifest)
        checks["triage_run_ok"] = runs_t["triage_urls"]["status"] in {"succeeded", "partial"}
        checks["triage_artifact_recorded"] = (
            triage_url_art is not None and triage_manifest_art is not None
        )
        prose_artifacts = [a for a in triage_api if a.get("evidence_file_id") == ev_prose]
        checks["triage_unsupported_refused"] = (
            runs_t["triage_unsupported"]["status"] == "failed"
            and str(runs_t["triage_unsupported"].get("error") or "").startswith(
                "TRIAGE_UNSUPPORTED_CONTENT"
            )
            and not prose_artifacts
        )
        checks["triage_no_auto_approval"] = bool(triage_api) and all(
            a.get("status") == "pending_review" for a in triage_api
        )
        checks["triage_explanation_failure_never_silent"] = bool(triage_api) and all(
            (a.get("payload") or {}).get("explanation_failed") is not True
            or a.get("validation_status") == "flagged"
            for a in triage_api
        )
        live["reports"]["triage_explanations_recorded"] = {
            "urls": triage_url_art is not None
            and (triage_url_art.get("payload") or {}).get("explanation") is not None,
            "manifest": triage_manifest_art is not None
            and (triage_manifest_art.get("payload") or {}).get("explanation") is not None,
        }

        # Independent recompute: PostgreSQL records -> pure engine -> payload.
        db_artifacts_after = await self._db_artifacts(case_id)
        db_by_id_after = {str(a.id): a for a in db_artifacts_after}
        db_records_after = await self._db_case_records(case_id)
        db_evidence_rows = await self._db_case_evidence(case_id)
        db_evidence_by_name = {
            str(row.original_filename).lower(): row
            for row in db_evidence_rows
            if row.original_filename
        }
        records_for: dict[str, list[SourceRecord]] = {}
        for record in db_records_after:
            records_for.setdefault(str(record.evidence_file_id), []).append(record)

        triage_problems: list[str] = []
        for ev_id, triage_api_art in (
            (ev_triage, triage_url_art),
            (ev_manifest, triage_manifest_art),
        ):
            if triage_api_art is None:
                continue
            row = db_by_id_after.get(str(triage_api_art["id"]))
            if row is None:
                triage_problems.append(
                    f"triage artifact {triage_api_art['id']} missing in PostgreSQL"
                )
                continue
            payload = dict(row.payload or {})
            ev_row = next((r for r in db_evidence_rows if str(r.id) == ev_id), None)
            fmt = EvidenceFormat(ev_row.format) if ev_row is not None and ev_row.format else None
            contents: list[tuple[SourceRecord, str]] = []
            for record in sorted(records_for.get(ev_id, []), key=lambda r: r.record_no):
                text = _unit_content(record, fmt)
                if text.strip():
                    contents.append((record, text))
            try:
                analysis = triage_contents(contents, settings=self.settings)
            except TriageRunError as exc:
                triage_problems.append(f"triage recompute refused for {ev_id}: {exc.code}")
                continue
            if payload.get("format_profile") != analysis["profile"]:
                triage_problems.append(
                    f"triage artifact {row.id}: format profile does not recompute"
                )
            if payload.get("missing_information") != analysis["missing_information"]:
                triage_problems.append(
                    f"triage artifact {row.id}: missing_information does not recompute"
                )
            if payload.get("rules_version") != TRIAGE_RULES_VERSION:
                triage_problems.append(f"triage artifact {row.id}: rules_version mismatch")
            if "no URL was fetched" not in str(payload.get("analysis_scope") or ""):
                triage_problems.append(f"triage artifact {row.id}: analysis scope missing")
            locator = dict(row.source_locator or {})
            if locator.get("scope") != "evidence_file" or locator.get("records_scanned") != len(
                contents
            ):
                triage_problems.append(f"triage artifact {row.id}: locator invalid")
            expected_obs = [
                obs
                for obs in analysis["observations"]
                if not str(obs["rule"]).startswith("triage.manifest.")
            ]
            got_obs = [
                obs
                for obs in (payload.get("observations") or [])
                if not str(obs.get("rule", "")).startswith("triage.manifest.")
            ]
            if got_obs != expected_obs:
                triage_problems.append(f"triage artifact {row.id}: observations do not recompute")

        # Manifest verdicts verified by re-hashing the real MinIO objects.
        manifest_verdict_counts: dict[str, int] = {}
        if triage_manifest_art is not None:
            manifest_payload = dict(triage_manifest_art.get("payload") or {})
            manifest_rows = list((manifest_payload.get("fields") or {}).get("manifest") or [])
            for entry in manifest_rows:
                name = str(entry.get("filename") or "").lower()
                verdict = str(entry.get("verdict"))
                manifest_verdict_counts[verdict] = manifest_verdict_counts.get(verdict, 0) + 1
                target = db_evidence_by_name.get(name)
                if verdict == "missing":
                    if target is not None or entry.get("computed_sha256") is not None:
                        triage_problems.append(
                            f"manifest entry {name!r}: missing verdict but file/hash exists"
                        )
                    continue
                if target is None or verdict not in {"match", "mismatch"}:
                    triage_problems.append(
                        f"manifest entry {name!r}: unverifiable verdict {verdict!r}"
                    )
                    continue
                raw_bytes = self.storage.download(str(target.stored_key))
                computed = hashlib.sha256(raw_bytes).hexdigest()
                if entry.get("computed_sha256") != computed:
                    triage_problems.append(
                        f"manifest entry {name!r}: computed hash does not recompute"
                    )
                agrees = computed == str(entry.get("sha256"))
                if (verdict == "match") != agrees:
                    triage_problems.append(
                        f"manifest entry {name!r}: verdict {verdict!r} disagrees with bytes"
                    )
            manifest_rule_counts = {
                rule: sum(
                    1
                    for obs in manifest_payload.get("observations") or []
                    if obs.get("rule") == rule
                )
                for rule in ("triage.manifest.hash_mismatch", "triage.manifest.entry_missing")
            }
            if manifest_rule_counts != {
                "triage.manifest.hash_mismatch": 1,
                "triage.manifest.entry_missing": 1,
            }:
                triage_problems.append(f"manifest observations wrong: {manifest_rule_counts!r}")
        checks["triage_observations_recompute"] = not triage_problems and triage_url_art is not None
        checks["triage_manifest_bytes_verified"] = (
            not triage_problems
            and triage_manifest_art is not None
            and manifest_verdict_counts == {"match": 1, "mismatch": 1, "missing": 1}
        )
        live["problems"].extend(triage_problems)

        audit = await self._audit_metadata_check(case_id)
        live["reports"]["audit"] = audit
        checks["audit_metadata_content_free"] = audit["rows_n"] >= 2 and not audit["problems"]
        live["problems"].extend(audit["problems"])
        return live

    # -- orchestration ---------------------------------------------------------

    async def run(self) -> int:
        try:
            await self.database.ping()
        except Exception as exc:  # noqa: BLE001 - setup failure
            print(f"database setup failure: {exc}", file=sys.stderr)
            return 2

        self.report["golden"] = self._golden_section()

        if not self.args.skip_live:
            try:
                self.token = await self._login(self.args.username, self.args.password)
                self.admin_token = await self._login(
                    self.args.admin_username, self.args.admin_password
                )
            except Exception as exc:  # noqa: BLE001 - setup failure
                print(f"login failure: {exc}", file=sys.stderr)
                await self.api.aclose()
                return 2
            if not await self.ai_ready():
                print(
                    "AI runtime is not ready (see /api/v1/ai/status); start the "
                    "model server per docs/ai/LOCAL_MODEL_SETUP.md, or pass "
                    "--skip-live to run golden metrics only.",
                    file=sys.stderr,
                )
                await self.api.aclose()
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
        self.args.report.write_text(
            json.dumps(self.report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(self.report, indent=2, ensure_ascii=False), flush=True)
        print(f"report written to {self.args.report}", flush=True)
        return 0 if all(self.gates.values()) else 1

    def _compute_gates(self) -> dict[str, bool]:
        golden = self.report["golden"]["multilingual"]
        problems = golden["problems"]
        gates: dict[str, bool] = {
            # A checker that never finds anything must not pass as "clean".
            "ml_not_vacuous": (
                golden["complaints_n"] >= 7
                and golden["values_n"] >= 14
                and golden["values_fabricated_n"] >= 4
                and golden["injection_n"] >= 4
                and golden["injection_withheld_expected"] >= 2
                and golden["translations_n"] >= 6
                and golden["translations_preserved_n"] >= 2
                and golden["translations_lossy_n"] >= 2
                and golden["flagged_cases_n"] >= 3
                and golden["candidates_seen"] == ["devanagari", "latin", "mixed", "unsupported"]
            ),
            "ml_profile_counts_exact": not problems["profile"],
            "ml_language_crosscheck_exact": not problems["language"],
            "ml_ambiguity_flags_exact": not problems["flags"],
            "ml_negation_exact": not problems["negation"],
            "ml_values_source_containment_exact": (
                not problems["values"]
                and golden["values_false_accepts"] == 0
                and golden["values_false_rejects"] == 0
            ),
            "ml_instruction_context_exact": not problems["instruction"],
            "ml_injection_withholding_exact": not problems["injection"],
            "ml_material_checks_exact": (
                not problems["material"] and golden["material_invariant_problems"] == 0
            ),
            "ml_parse_accept_reject_exact": not problems["parse"],
            "ml_determinism": golden["determinism_ok"],
        }
        triage = self.report["golden"].get("triage")
        if triage:
            t_problems = triage["problems"]
            gates["triage_not_vacuous"] = (
                triage["cases_n"] >= 8
                and len(triage["rules_seen"]) >= 7
                and triage["benign_n"] >= 2
                and triage["refusal_n"] >= 1
                and triage["injection_n"] >= 1
                and triage["manifest_cases_n"] >= 1
                and triage["burst_cases_n"] >= 2
            )
            gates["triage_profile_counts_exact"] = not t_problems["profile"]
            gates["triage_observations_exact"] = not t_problems["observations"]
            gates["triage_missing_information_exact"] = not t_problems["missing"]
            gates["triage_refusal_exact"] = not t_problems["refusal"]
            gates["triage_injection_containment"] = not t_problems["injection"]
            gates["triage_manifest_verdicts_exact"] = not t_problems["manifest"]
            gates["triage_burst_exact"] = not t_problems["burst"]
            gates["triage_explanation_parse_exact"] = not t_problems["explanation"]
            gates["triage_determinism"] = triage["determinism_ok"]
        live = self.report.get("live")
        if live:
            for name, ok in live.get("checks", {}).items():
                gates[f"live_{name}"] = bool(ok)
            gates["live_no_problems"] = not live.get("problems")
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

        if self._outsider_id is not None:
            try:
                suspend = await self.api.post(
                    f"/admin/users/{self._outsider_id}/suspend",
                    headers=self._headers(self.admin_token),
                )
                outcome["outsider_suspended"] = suspend.status_code == 200
                async with factory() as session:
                    await session.execute(
                        sa_delete(AuditLog).where(AuditLog.actor_id == uuid.UUID(self._outsider_id))
                    )
                    await session.commit()
            except Exception as exc:  # noqa: BLE001 - cleanup is best-effort
                outcome["outsider_cleanup_error"] = str(exc)
                print(f"cleanup warning (outsider): {exc}", file=sys.stderr)

        await self.database.close()
        self.storage.close()
        self.report["cleanup"] = outcome


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
    return asyncio.run(Phase567EvalRunner(_parse_args(argv)).run())


if __name__ == "__main__":
    sys.exit(main())
