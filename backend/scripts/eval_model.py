"""Deterministic evaluation harness for the local AI assistant.

Implements the harness designed in ``docs/ai/EVALUATION.md`` §5 so a model swap
(including a future fine-tune) is judged instead of guessed:

* **groundedness** — every ``SourceRef`` the gateway cites must exist in the
  database *and* belong to the evaluated case (case-scoped types); knowledge
  sources must point at an allowlisted documentation file. Any unresolvable
  source is a hard failure (hallucinated citation).
* **recall of expected facts** — frozen ``(question, expected_facts)`` tuples
  from ``backend/tests/fixtures/ai_golden.jsonl``; substring match against the
  answer, normalised for case and underscore/space. Reported, not gated (it
  measures model quality, not security).
* **abstention** — questions scoped to cases the caller cannot access must be
  refused by the API (403) or report the unknown case as missing (404). Hard
  gate: 100 % or the run fails.
* **latency** — per-request duration reported from the real API.

Gates (process exit code 1 when any fails):
  abstention == 100 %, zero ungrounded case-mode answers, zero unresolvable
  sources. Fact recall is a reported metric only.

The harness talks to the real backend over HTTP (real auth, real authorization,
real inference) and uses the database only to *verify* citations and to resolve
foreign cases the API will not show the caller. Conversations it creates are
deleted afterwards.

Run via the entry point (loads the environment, checks both servers):

    ./scripts/ai/eval_model.sh

or directly from ``backend/``:

    .venv/bin/python -m scripts.eval_model --report /tmp/report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
from app.core.config import get_settings
from app.db.postgres import Database
from app.models import Case, CaseMember, Entity, EvidenceFile, Finding, TimelineEvent, Victim
from app.models.metric_result import MetricResult
from sqlalchemy import or_, select

REPO_ROOT = get_settings().repo_root
GOLDEN_DEFAULT = REPO_ROOT / "backend" / "tests" / "fixtures" / "ai_golden.jsonl"
REPORT_DEFAULT = REPO_ROOT / "ai_runtime" / "eval_report.json"
API_BASE_DEFAULT = "http://localhost:8000/api/v1"

# Same allowlist the knowledge tool enforces (app/ai/knowledge.py); duplicated
# as data here so the harness never trusts a cited doc path it cannot verify.
KNOWLEDGE_DOC_GLOBS = ("README.md", "docs/*.md", "docs/ai/*.md")

# Pacing: AI_PER_USER_RATE_LIMIT is 20 chat requests/minute by default. Sleeping
# between request *starts* keeps a long run under the limit without tripping it.
MIN_REQUEST_INTERVAL_SECONDS = 3.5
REQUEST_TIMEOUT_SECONDS = 240.0


@dataclass(slots=True)
class EntryResult:
    id: str
    kind: str
    ok: bool
    http_status: int | None = None
    latency_ms: int | None = None
    answer: str = ""
    facts_matched: int = 0
    facts_total: int = 0
    missing_facts: list[str] = field(default_factory=list)
    sources_total: int = 0
    sources_valid: int = 0
    invalid_sources: list[dict[str, str]] = field(default_factory=list)
    ungrounded: bool = False
    error: str | None = None
    conversation_id: str | None = None


def _normalise(text: str) -> str:
    """Case-insensitive, underscore/space-insensitive for fact matching."""
    return re.sub(r"\s+", " ", text.replace("_", " ").replace("’", "'")).strip().lower()


def _fact_present(fact: str, answer: str) -> bool:
    return _normalise(fact) in _normalise(answer)


def _load_golden(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entry = json.loads(line)
        kind = entry.get("kind")
        if kind not in {"grounded", "abstention", "abstention_unknown"}:
            raise ValueError(f"{path}:{line_no}: unknown kind {kind!r}")
        if not entry.get("id") or not entry.get("question"):
            raise ValueError(f"{path}:{line_no}: id and question are required")
        if kind == "grounded" and not entry.get("expected_facts"):
            raise ValueError(f"{path}:{line_no}: grounded entry needs expected_facts")
        entries.append(entry)
    if not entries:
        raise ValueError(f"{path}: no entries")
    ids = [entry["id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate entry ids")
    return entries


async def _resolve_source(
    source: dict[str, Any], case_id: str, session: Any, repo_root: Path
) -> str | None:
    """Return None when the citation resolves, else a reason string."""
    source_type = source.get("type")
    source_id = str(source.get("id", ""))
    if not source_id:
        return "empty id"
    if source_type == "knowledge":
        doc = source_id.split("#", 1)[0]
        for pattern in KNOWLEDGE_DOC_GLOBS:
            if Path(doc).match(pattern) and (repo_root / doc).is_file():
                return None
        return f"knowledge doc {doc!r} not in allowlist or missing"
    if source_type == "graph":
        return None if source_id == case_id else "graph source id is not the case"
    scoped: dict[str, Any] = {
        "case": Case,
        "entity": Entity,
        "evidence": EvidenceFile,
        "finding": Finding,
        "timeline": TimelineEvent,
        "victim": Victim,
        "metric": MetricResult,
    }
    model = scoped.get(str(source_type))
    if model is None:
        return f"unknown source type {source_type!r}"
    try:
        parsed = uuid.UUID(source_id)
    except ValueError:
        return "id is not a UUID"
    row = await session.get(model, parsed)
    if row is None:
        return f"{source_type} {source_id} does not exist"
    owner = getattr(row, "case_id", source_id)
    if str(owner) != case_id:
        return f"{source_type} belongs to case {owner}, not {case_id}"
    return None


class EvalRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.api = httpx.AsyncClient(
            base_url=args.api_base, timeout=REQUEST_TIMEOUT_SECONDS
        )
        self.token: str | None = None
        self._last_request_start = 0.0
        self.conversations: list[str] = []

    # -- HTTP plumbing ------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_start
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        self._last_request_start = time.monotonic()

    async def _post_chat(self, payload: dict[str, Any]) -> httpx.Response:
        for attempt in (1, 2):
            await self._throttle()
            response = await self.api.post(
                "/ai/chat", json=payload, headers=self._headers()
            )
            if response.status_code == 429 and attempt == 1:
                print("    rate limited; waiting 60s", flush=True)
                await asyncio.sleep(60)
                continue
            return response
        return response

    async def login(self, username: str, password: str) -> None:
        response = await self.api.post(
            "/auth/login", json={"username": username, "password": password}
        )
        response.raise_for_status()
        self.token = response.json()["access_token"]

    async def ai_status_ready(self) -> bool:
        response = await self.api.get("/ai/status", headers=self._headers())
        if response.status_code != 200:
            return False
        return bool(response.json().get("ready"))

    # -- case resolution ----------------------------------------------------

    async def _own_case_ids(self) -> dict[str, str]:
        response = await self.api.get(
            "/cases", params={"limit": 200}, headers=self._headers()
        )
        response.raise_for_status()
        return {
            item["case_number"]: item["id"] for item in response.json()["items"]
        }

    async def _foreign_case_id(
        self, database: Database, preferred: str | None
    ) -> tuple[str, str] | None:
        """A case the caller can neither access nor own (abstention target)."""
        factory = database.session_factory()
        async with factory() as session:
            if preferred:
                row = (
                    await session.execute(
                        select(Case).where(Case.case_number == preferred)
                    )
                ).scalar_one_or_none()
                if row is not None and await self._caller_cannot_access(
                    session, row.id
                ):
                    return row.case_number, str(row.id)
            candidates = (
                await session.execute(
                    select(Case)
                    .where(
                        or_(Case.owner_id.is_(None), Case.owner_id != self._caller_id)
                    )
                    .order_by(Case.case_number)
                    .limit(50)
                )
            ).scalars()
            for candidate in candidates:
                if await self._caller_cannot_access(session, candidate.id):
                    return candidate.case_number, str(candidate.id)
        return None

    async def _caller_cannot_access(self, session: Any, case_id: uuid.UUID) -> bool:
        # CaseMember uses a composite PK (case_id, user_id); select case_id as
        # the probe column since there is no surrogate .id.
        row = (
            await session.execute(
                select(CaseMember.case_id).where(
                    CaseMember.case_id == case_id,
                    CaseMember.user_id == self._caller_id,
                )
            )
        ).scalar_one_or_none()
        return row is None

    # -- scoring ------------------------------------------------------------

    async def _score_grounded(
        self,
        entry: dict[str, Any],
        body: dict[str, Any],
        case_id: str,
        database: Database,
    ) -> EntryResult:
        answer = str(body.get("answer", ""))
        facts = [str(f) for f in entry["expected_facts"]]
        matched = [f for f in facts if _fact_present(f, answer)]
        sources = list(body.get("sources", []))
        invalid: list[dict[str, str]] = []
        factory = database.session_factory()
        async with factory() as session:
            for source in sources:
                reason = await _resolve_source(source, case_id, session, REPO_ROOT)
                if reason is not None:
                    invalid.append(
                        {
                            "type": str(source.get("type")),
                            "id": str(source.get("id")),
                            "reason": reason,
                        }
                    )
        ungrounded = not sources
        ok = not invalid and not ungrounded and body.get("status_code", 200) == 200
        return EntryResult(
            id=entry["id"],
            kind="grounded",
            ok=ok,
            http_status=200,
            latency_ms=body.get("duration_ms"),
            answer=answer,
            facts_matched=len(matched),
            facts_total=len(facts),
            missing_facts=[f for f in facts if f not in matched],
            sources_total=len(sources),
            sources_valid=len(sources) - len(invalid),
            invalid_sources=invalid,
            ungrounded=ungrounded,
            conversation_id=str(body.get("conversation_id", "")) or None,
        )

    # -- main run -----------------------------------------------------------

    async def run(self) -> int:
        settings = get_settings()
        entries = _load_golden(self.args.golden)
        database = Database(settings)
        self._caller_id: uuid.UUID | None = None

        try:
            await database.ping()  # fail fast when the database is unreachable
            await self.login(self.args.username, self.args.password)
        except Exception as exc:  # noqa: BLE001 - reported as a setup failure
            print(f"setup failure: {exc}", file=sys.stderr)
            return 2

        if not await self.ai_status_ready():
            print(
                "AI runtime is not ready (see /api/v1/ai/status); start the model "
                "server per docs/ai/LOCAL_MODEL_SETUP.md",
                file=sys.stderr,
            )
            return 2

        # The caller's user id, needed to pick abstention targets they cannot access.
        response = await self.api.get("/auth/me", headers=self._headers())
        response.raise_for_status()
        self._caller_id = uuid.UUID(response.json()["user"]["id"])

        own_cases = await self._own_case_ids()
        results: list[EntryResult] = []
        started = time.monotonic()

        try:
            for index, entry in enumerate(entries, 1):
                print(f"[{index}/{len(entries)}] {entry['id']} …", flush=True)
                result = await self._run_entry(entry, own_cases, database)
                results.append(result)
                verdict = "PASS" if result.ok else "FAIL"
                detail = f" ({result.error})" if result.error else ""
                print(f"    {verdict}{detail}", flush=True)
        finally:
            await self._cleanup_conversations()
            await self.api.aclose()
            await database.close()

        return self._report(entries, results, time.monotonic() - started)

    async def _run_entry(
        self, entry: dict[str, Any], own_cases: dict[str, str], database: Database
    ) -> EntryResult:
        kind = entry["kind"]
        try:
            if kind == "grounded":
                case_number = entry["case_number"]
                case_id = own_cases.get(case_number)
                if case_id is None:
                    return EntryResult(
                        id=entry["id"],
                        kind=kind,
                        ok=False,
                        error=f"caller does not own case {case_number}",
                    )
                payload = {
                    "question": entry["question"],
                    "mode": entry.get("mode", "case"),
                    "case_id": case_id,
                }
                response = await self._post_chat(payload)
                if response.status_code != 200:
                    return EntryResult(
                        id=entry["id"],
                        kind=kind,
                        ok=False,
                        http_status=response.status_code,
                        error=f"HTTP {response.status_code}: {response.text[:200]}",
                    )
                body = response.json()
                result = await self._score_grounded(entry, body, case_id, database)
                if result.conversation_id:
                    self.conversations.append(result.conversation_id)
                return result

            if kind == "abstention":
                target = await self._foreign_case_id(database, entry.get("case_number"))
                if target is None:
                    return EntryResult(
                        id=entry["id"],
                        kind=kind,
                        ok=True,
                        error="skipped: no inaccessible case available",
                    )
                case_number, case_id = target
                payload = {
                    "question": entry["question"],
                    "mode": entry.get("mode", "case"),
                    "case_id": case_id,
                }
                response = await self._post_chat(payload)
                expected = int(entry["expected_status"])
                ok = response.status_code == expected
                return EntryResult(
                    id=entry["id"],
                    kind=kind,
                    ok=ok,
                    http_status=response.status_code,
                    error=(
                        None
                        if ok
                        else f"case {case_number}: expected HTTP {expected}, "
                        f"got {response.status_code}"
                    ),
                )

            # abstention_unknown: a case id nobody can access because it does not exist.
            payload = {
                "question": entry["question"],
                "mode": entry.get("mode", "case"),
                "case_id": str(uuid.uuid4()),
            }
            response = await self._post_chat(payload)
            expected = int(entry["expected_status"])
            ok = response.status_code == expected
            return EntryResult(
                id=entry["id"],
                kind=kind,
                ok=ok,
                http_status=response.status_code,
                error=(
                    None
                    if ok
                    else f"expected HTTP {expected}, got {response.status_code}"
                ),
            )
        except Exception as exc:  # noqa: BLE001 - recorded per entry
            return EntryResult(
                id=entry["id"], kind=kind, ok=False, error=f"{type(exc).__name__}: {exc}"
            )

    async def _cleanup_conversations(self) -> None:
        for conversation_id in self.conversations:
            try:
                await self.api.delete(
                    f"/ai/conversations/{conversation_id}", headers=self._headers()
                )
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                print(f"    cleanup: could not delete {conversation_id}: {exc}", file=sys.stderr)

    def _report(
        self, entries: list[dict[str, Any]], results: list[EntryResult], elapsed: float
    ) -> int:
        grounded = [r for r in results if r.kind == "grounded"]
        abstentions = [r for r in results if r.kind.startswith("abstention")]
        skipped = [r for r in results if r.error and "skipped:" in (r.error or "")]
        scored_abstentions = [r for r in abstentions if r not in skipped]

        facts_matched = sum(r.facts_matched for r in grounded)
        facts_total = sum(r.facts_total for r in grounded)
        sources_total = sum(r.sources_total for r in grounded)
        sources_valid = sum(r.sources_valid for r in grounded)
        invalid_sources = [s for r in grounded for s in r.invalid_sources]
        ungrounded = [r.id for r in grounded if r.ungrounded]
        abstention_passed = sum(1 for r in scored_abstentions if r.ok)
        latencies = [r.latency_ms for r in grounded if r.latency_ms is not None]

        gates = {
            "abstention_100pct": bool(scored_abstentions)
            and abstention_passed == len(scored_abstentions),
            "zero_ungrounded_answers": not ungrounded,
            "zero_invalid_sources": not invalid_sources,
        }
        passed = all(gates.values())

        report = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "api_base": self.args.api_base,
            "golden": str(self.args.golden),
            "entries": len(entries),
            "passed": passed,
            "gates": gates,
            "metrics": {
                "fact_recall": round(facts_matched / facts_total, 4)
                if facts_total
                else None,
                "facts_matched": facts_matched,
                "facts_total": facts_total,
                "groundedness": round(sources_valid / sources_total, 4)
                if sources_total
                else None,
                "sources_valid": sources_valid,
                "sources_total": sources_total,
                "abstention_passed": abstention_passed,
                "abstention_total": len(scored_abstentions),
                "abstention_skipped": len(skipped),
                "latency_ms_avg": round(sum(latencies) / len(latencies))
                if latencies
                else None,
                "latency_ms_max": max(latencies) if latencies else None,
                "elapsed_seconds": round(elapsed, 1),
            },
            "ungrounded_answers": ungrounded,
            "invalid_sources": invalid_sources,
            "results": [asdict(r) for r in results],
        }
        self.args.report.parent.mkdir(parents=True, exist_ok=True)
        self.args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

        metrics = report["metrics"]
        print()
        print("== eval summary ==")
        print(f"  passed:            {passed}  gates={gates}")
        print(
            f"  fact recall:       {metrics['fact_recall']} "
            f"({facts_matched}/{facts_total} expected facts in answers)"
        )
        print(
            f"  groundedness:      {metrics['groundedness']} "
            f"({sources_valid}/{sources_total} citations resolve to the case)"
        )
        print(
            f"  abstention:        {abstention_passed}/{len(scored_abstentions)} "
            f"refusals as required ({len(skipped)} skipped)"
        )
        print(
            f"  latency ms:        avg={metrics['latency_ms_avg']} "
            f"max={metrics['latency_ms_max']} over {len(grounded)} completions"
        )
        print(f"  report:            {self.args.report}")
        return 0 if passed else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--golden", type=Path, default=GOLDEN_DEFAULT)
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    parser.add_argument("--api-base", default=API_BASE_DEFAULT)
    parser.add_argument(
        "--username",
        default="investigator",
        help="owner of the showcase cases (seeded dev account)",
    )
    parser.add_argument(
        "--password",
        default="investigator-dev-password",
        help="matches scripts/seed_users.py unless SEED_INVESTIGATOR_PASSWORD is set",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(EvalRunner(args).run())


if __name__ == "__main__":
    sys.exit(main())
