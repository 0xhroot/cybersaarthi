"""Combined final evaluation harness for all ten AI features.

Phase 7 delivery harness: orchestrates the per-phase harnesses
(``scripts/eval_model.py``, ``scripts/eval_evidence.py``,
``scripts/eval_phase3.py``, ``scripts/eval_phase4.py``,
``scripts/eval_phase567.py``) as subprocesses, merges their gates into one
report with **individual metrics kept separate**, and adds cross-cutting
operational gates the phase harnesses cannot see:

* **test inventory** - the collected hermetic/integration test counts are
  read from pytest (collect-only) and gated with an anti-vacuous floor, so
  "the suite shrank silently" fails the delivery.
* **migration state** - ``alembic heads`` must be exactly the single
  expected head (no branched history); the constant must be updated
  deliberately when a new migration lands.
* **feature coverage** - every one of the ten features must map to at least
  one *measured* section in a harness that actually ran (golden cases or a
  live run); a feature whose evidence vanished fails.
* **error shape** (live mode only) - one anonymous probe verifies the
  documented ``{"error": {"code", "message"}}`` shape end-to-end.

Each phase harness keeps ownership of its own metrics (precision/recall,
false-positive counts, ``n=`` sample sizes, limitations); this file never
recomputes or dilutes them - it only prefixes gate names per phase and
refuses to pass if any included harness reported a failed gate, even when
the harness's own exit code was lost.

Live-model sections (phases 1-2 are live-only harnesses) are marked
separately in the report; in ``--skip-live`` mode they are labelled "not
measured here" rather than silently absent.

Run via the entry point (loads the environment, checks the stack):

    ./scripts/ai/eval_final.sh

or directly from ``backend/``:

    .venv/bin/python -m scripts.eval_final --report /tmp/eval_final.json
    .venv/bin/python -m scripts.eval_final --skip-live   # golden only
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
REPORT_DEFAULT = REPO_ROOT / "ai_runtime" / "eval_final_report.json"
API_BASE_DEFAULT = "http://localhost:8000/api/v1"

# Deliberate constant: Phase 7 requires migration history to be unchanged.
# If a new alembic migration lands, update this in the same commit and say
# so in the delivery report - never silently accept a branched history.
EXPECTED_ALEMBIC_HEAD = "c5e2b8f4d9a3"

# Anti-vacuous floor for the collected backend test suite. The suite has
# 1045 tests at Phase 7 delivery; the floor catches accidental mass
# deletion without failing on ordinary additions.
MIN_COLLECTED_TESTS = 1000

_PHASE_HARNESSES = (
    # (report key, module, live-only, description)
    ("phase1_model", "scripts.eval_model", True, "grounded AI assistant"),
    ("phase2_evidence", "scripts.eval_evidence", True, "ingestion + custody"),
    ("phase3_case_intel", "scripts.eval_phase3", False, "entity/timeline/contradiction"),
    ("phase4_flow", "scripts.eval_phase4", False, "financial flow + cross-case"),
    ("phase567_expansion", "scripts.eval_phase567", False, "multilingual/triage/audit"),
)

# The ten-feature delivery matrix. Each entry maps a feature to the harness
# section(s) that measure it: golden fixture sections (key path inside the
# harness report) and/or a live-run marker (the harness ran live end-to-end).
FEATURES: tuple[dict[str, Any], ...] = (
    {
        "feature": "grounded AI assistant (chat/stream/draft/tools)",
        "harness": "phase1_model",
        "golden_sections": [],
        "live_required": True,
    },
    {
        "feature": "evidence intelligence (ingestion copilot + chain-of-custody auditor)",
        "harness": "phase2_evidence",
        "golden_sections": [],
        "live_required": True,
    },
    {
        "feature": "entity resolution",
        "harness": "phase3_case_intel",
        "golden_sections": ["entity_resolution"],
        "live_required": False,
    },
    {
        "feature": "timeline reconstruction",
        "harness": "phase3_case_intel",
        "golden_sections": ["timeline_reconstruction"],
        "live_required": False,
    },
    {
        "feature": "contradiction detection",
        "harness": "phase3_case_intel",
        "golden_sections": ["contradiction_detection"],
        "live_required": False,
    },
    {
        "feature": "financial flow analysis",
        "harness": "phase4_flow",
        "golden_sections": ["financial_flow"],
        "live_required": False,
    },
    {
        "feature": "cross-case linkage",
        "harness": "phase4_flow",
        "golden_sections": ["cross_case"],
        "live_required": False,
    },
    {
        "feature": "multilingual complaint intelligence",
        "harness": "phase567_expansion",
        "golden_sections": ["multilingual"],
        "live_required": False,
    },
    {
        "feature": "digital forensics triage",
        "harness": "phase567_expansion",
        "golden_sections": ["triage"],
        "live_required": False,
    },
    {
        "feature": "AI report auditing",
        "harness": "phase567_expansion",
        "golden_sections": ["report_audit"],
        "live_required": False,
    },
)

GATE_PREFIX = {
    "phase1_model": "p1",
    "phase2_evidence": "p2",
    "phase3_case_intel": "p3",
    "phase4_flow": "p4",
    "phase567_expansion": "p567",
}

# Which report section proves a harness actually ran its live end-to-end
# work (see _live_ran).
_LIVE_SECTION_KEYS: dict[str, tuple[str, ...]] = {
    "phase1_model": ("results",),
    "phase2_evidence": ("ingestion", "integrity", "custody"),
    "phase3_case_intel": ("live",),
    "phase4_flow": ("live",),
    "phase567_expansion": ("live",),
}


def _run_module(module: str, report_path: Path, *, skip_live: bool) -> tuple[int, str]:
    """Run one phase harness in a subprocess; return (exit code, tail of stderr)."""
    command = [sys.executable, "-m", module, "--report", str(report_path)]
    if skip_live:
        command.append("--skip-live")
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        command,
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    tail = (result.stderr or "").strip()[-1500:]
    return result.returncode, tail


def _test_inventory() -> dict[str, Any]:
    """Collected test counts via pytest collect-only (no tests are executed)."""

    def _collect(extra: list[str]) -> int | None:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                *extra,
                "tests/",
            ],
            cwd=BACKEND_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        match = re.search(r"^(\d+)(?:/\d+)? tests collected", result.stdout, re.MULTILINE)
        return int(match.group(1)) if match else None

    total = _collect([])
    integration = _collect(["-m", "integration"])
    hermetic = None
    if total is not None and integration is not None:
        hermetic = total - integration
    return {
        "collected_total": total,
        "collected_integration": integration,
        "collected_hermetic": hermetic,
        "min_total": MIN_COLLECTED_TESTS,
    }


def _migration_state() -> dict[str, Any]:
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "alembic", "heads"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    heads = [line.strip().split(" ")[0] for line in result.stdout.splitlines() if line.strip()]
    return {
        "heads": heads,
        "expected_head": EXPECTED_ALEMBIC_HEAD,
        "single_head": len(heads) == 1,
        "head_unchanged": heads == [EXPECTED_ALEMBIC_HEAD],
    }


def _error_shape_probe(api_base: str) -> dict[str, Any]:
    """One anonymous probe: the documented error shape, live, no auth.

    Probes the Phase-6 ``POST /cases/{id}/report-audits`` route: its
    ``require_permission`` dependency resolves before the route body (and
    before any case lookup), so an anonymous caller always gets 401 with the
    documented ``{"error": {"code", "message"}}`` contract regardless of
    whether the case id exists.
    """
    import httpx

    problem: str | None = None
    observed: dict[str, Any] | None = None
    status: int | None = None
    try:
        response = httpx.post(
            f"{api_base}/cases/00000000-0000-0000-0000-000000000000/report-audits",
            json={"draft_text": "anonymous probe (never reaches the model)"},
            timeout=10.0,
        )
        status = response.status_code
        observed = response.json()
        code = str((observed or {}).get("error", {}).get("code", ""))
        message = (observed or {}).get("error", {}).get("message")
        if response.status_code != 401 or not code or not isinstance(message, str):
            problem = (
                f"status={response.status_code} body={str(observed)[:200]!r} "
                "(expected 401 + error.code + error.message)"
            )
    except Exception as exc:  # noqa: BLE001 - probe failure is a gate, not a crash
        problem = f"probe failed: {type(exc).__name__}: {exc}"
    return {
        "ok": problem is None,
        "problem": problem,
        "status": status,
        "observed": observed,
    }


def _golden_cases_n(report: dict[str, Any], section: str) -> int | None:
    """Sample size of a golden section, whichever naming it uses.

    Phase harnesses name their denominators ``cases_n`` (phase 567),
    ``complaints_n`` (multilingual), ``n_cases`` / ``n_parse_cases`` /
    ``n_records`` (phases 3-4). Any positive integer ``*_n`` or ``n_*``
    key counts as a measured denominator; ``None`` means unmeasured.
    """
    golden = report.get("golden")
    if not isinstance(golden, dict):
        return None
    entry = golden.get(section)
    if not isinstance(entry, dict):
        return None
    for key, value in entry.items():
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            continue
        if key.endswith("_n") or key.startswith("n_"):
            return value
    return None


def _live_ran(report: dict[str, Any], harness: str) -> bool:
    """True when the harness's live end-to-end work is present in its report.

    Phases 3-6 record a dedicated ``live`` section. The phase 1/2 harnesses
    are live-only (no ``--skip-live``): their top-level sections *are* the
    live runs, so a non-empty section proves the live path executed.
    """
    keys = _LIVE_SECTION_KEYS.get(harness, ("live",))
    for key in keys:
        value = report.get(key)
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, list) and value:
            return True
    return False


class FinalEvalRunner:
    """Orchestrates the phase harnesses and the cross-cutting gates."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.report: dict[str, Any] = {}
        self.gates: dict[str, bool] = {}

    async def run(self) -> int:  # noqa: ASYNC109 - symmetric with sibling harnesses
        started = time.monotonic()
        phase_reports: dict[str, Any] = {}
        phase_meta: dict[str, Any] = {}

        with tempfile.TemporaryDirectory(prefix="eval_final_") as tmp:
            tmp_path = Path(tmp)
            for key, module, live_only, description in _PHASE_HARNESSES:
                if self.args.skip_live and live_only:
                    phase_meta[key] = {
                        "description": description,
                        "ran": False,
                        "reason": "live-only harness; not measured in --skip-live mode",
                        "gates_total": 0,
                    }
                    print(f"  skip {key}: {description} (live-only)", flush=True)
                    continue
                report_path = tmp_path / f"{key}.json"
                print(f"  run  {key}: {description}", flush=True)
                exit_code, stderr_tail = await _run_module_async(
                    module, report_path, skip_live=self.args.skip_live
                )
                entry: dict[str, Any] = {
                    "description": description,
                    "ran": True,
                    "skip_live": self.args.skip_live,
                    "exit_code": exit_code,
                    "stderr_tail": stderr_tail or None,
                }
                if report_path.is_file():
                    phase_report = json.loads(report_path.read_text(encoding="utf-8"))
                    phase_reports[key] = phase_report
                    phase_gates = phase_report.get("gates", {})
                    entry["gates_total"] = len(phase_gates)
                    entry["gates_failed"] = sorted(
                        name for name, ok in phase_gates.items() if not ok
                    )
                    entry["live_ran"] = _live_ran(phase_report, key)
                else:
                    entry["gates_total"] = 0
                    entry["error"] = "harness produced no report file"
                phase_meta[key] = entry

        self.report["phases"] = phase_meta
        self.report["phase_reports"] = phase_reports

        # -- cross-cutting gates --------------------------------------------
        gates: dict[str, bool] = {}

        # Every included harness must have run, exited 0, produced a report
        # and reported zero failed gates - checked from the *report*, never
        # trusting the exit code alone.
        for key, meta in phase_meta.items():
            if not meta.get("ran"):
                gates[f"{key}_skipped_live_only"] = True
                continue
            gates[f"{key}_ran_clean"] = (
                meta.get("exit_code") == 0
                and "error" not in meta
                and not meta.get("gates_failed")
                and int(meta.get("gates_total") or 0) > 0
            )
            # Prefix and carry every individual phase gate forward so the
            # combined report keeps them separate and traceable.
            for name, ok in (phase_reports.get(key, {}).get("gates") or {}).items():
                gates[f"{GATE_PREFIX[key]}_{name}"] = bool(ok)

        # Feature coverage: each feature's golden sections must be present
        # with a non-vacuous case count, or (live-only features) its harness
        # must have run live. In --skip-live mode live-only features are
        # labelled "not measured here" and excluded from the gate - never
        # silently reported as covered.
        coverage: list[dict[str, Any]] = []
        for item in FEATURES:
            key = str(item["harness"])
            phase_report = phase_reports.get(key)
            coverage_entry: dict[str, Any] = {
                "feature": item["feature"],
                "harness": key,
                "measurable": True,
                "measured": False,
                "evidence": None,
            }
            if phase_report is None:
                if self.args.skip_live and item["live_required"]:
                    # Expected in golden-only mode: explicitly not measured.
                    coverage_entry["measurable"] = False
                    coverage_entry["evidence"] = (
                        "not measured here (live-only harness, --skip-live mode)"
                    )
                else:
                    # A harness that should have run but produced no report
                    # is a delivery failure, not an exemption.
                    coverage_entry["evidence"] = "harness produced no report (failure)"
            elif item["live_required"]:
                coverage_entry["measured"] = _live_ran(phase_report, key)
                coverage_entry["evidence"] = (
                    "live end-to-end section ran"
                    if coverage_entry["measured"]
                    else "live section ran but recorded no runs"
                )
            else:
                sections = list(item["golden_sections"])
                counts = {section: _golden_cases_n(phase_report, section) for section in sections}
                coverage_entry["golden_cases_n"] = counts
                coverage_entry["measured"] = bool(sections) and all(
                    count is not None and count > 0 for count in counts.values()
                )
                coverage_entry["evidence"] = f"golden cases n={counts}"
            coverage.append(coverage_entry)
        self.report["feature_coverage"] = coverage
        measurable = [item for item in coverage if item["measurable"]]
        gates["all_features_measured"] = all(item["measured"] for item in measurable)
        gates["feature_matrix_complete"] = len(coverage) == len(FEATURES)

        # Test inventory (anti-vacuous floor; counts only, no execution).
        inventory = _test_inventory()
        self.report["test_inventory"] = inventory
        total = inventory["collected_total"]
        gates["test_inventory_present"] = total is not None
        gates["test_inventory_floor"] = isinstance(total, int) and total >= MIN_COLLECTED_TESTS

        # Migration state: exactly one head, unchanged from the Phase-7 base.
        migration = _migration_state()
        self.report["migration"] = migration
        gates["migration_single_head"] = bool(migration["single_head"])
        gates["migration_head_unchanged"] = bool(migration["head_unchanged"])

        # Error-shape consistency (live only): anonymous probe of the
        # documented {"error": {"code", "message"}} contract.
        if not self.args.skip_live:
            probe = _error_shape_probe(self.args.api_base)
            self.report["error_shape_probe"] = probe
            gates["error_shape_documented"] = bool(probe["ok"])

        self.gates = gates
        self.report["gates"] = gates
        self.report["elapsed_seconds"] = round(time.monotonic() - started, 1)
        self.report["mode"] = "golden-only" if self.args.skip_live else "golden+live"

        self.args.report.parent.mkdir(parents=True, exist_ok=True)
        self.args.report.write_text(
            json.dumps(self.report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        failed = sorted(name for name, ok in gates.items() if not ok)
        print(json.dumps({"gates": gates, "failed": failed}, indent=2), flush=True)
        print(f"report written to {self.args.report}", flush=True)
        return 0 if not failed else 1


async def _run_module_async(module: str, report_path: Path, *, skip_live: bool) -> tuple[int, str]:
    import asyncio

    return await asyncio.to_thread(_run_module, module, report_path, skip_live=skip_live)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    parser.add_argument("--api-base", default=API_BASE_DEFAULT)
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="run only the deterministic golden-fixture sections (no stack needed)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import asyncio

    return asyncio.run(FinalEvalRunner(_parse_args(argv)).run())


if __name__ == "__main__":
    sys.exit(main())
