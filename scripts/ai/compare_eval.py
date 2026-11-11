#!/usr/bin/env python3
"""Compare two eval_model.sh reports and decide whether a tuned model may replace the baseline.

The decision rule is deliberately conservative, because the brief this project
works to says the fine-tuned adapter is adopted *only* on a measured
improvement with no gate regression:

  ADOPT   every hard gate still passes in the tuned report AND at least one
          reported metric improved.
  REJECT  any hard gate that passed in the baseline fails in the tuned run,
          or no metric improved at all.

Everything printed comes from the two JSON files — nothing is estimated,
extrapolated or filled in. If the two runs scored different golden sets the
comparison is refused rather than silently averaged, since numbers from
different question sets are not comparable.

Usage:
  python3 scripts/ai/compare_eval.py BASELINE.json TUNED.json
  python3 scripts/ai/compare_eval.py BASELINE.json TUNED.json --json out.json

Exit codes: 0 = ADOPT, 1 = REJECT, 2 = usage/shape error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Metrics where a higher value is better. Everything else in `metrics` that is
# not on this list is reported but never used to justify adoption (latency,
# elapsed time, raw counts of checked items, and the "bad"/"missing" lists).
HIGHER_IS_BETTER = frozenset(
    {
        "groundedness",
        "fact_recall",
        "abstention_passed",  # only comparable when *_total matches
        "sources_valid",
        "analysis_entries_passed",
        "hypothesis_entries_passed",
    }
)

# Metrics where a lower value is better (they are counts of defects).
LOWER_IS_BETTER = frozenset(
    {
        "ungrounded_answers",
        "invalid_sources",
        "analysis_sections_missing",
        "hypothesis_draft_errors",
    }
)


def load(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise SystemExit(f"error: no such report: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: {path} is not valid JSON: {exc}")
    if not isinstance(data, dict) or "gates" not in data or "metrics" not in data:
        raise SystemExit(
            f"error: {path} does not look like an eval_model.sh report "
            "(missing 'gates'/'metrics')"
        )
    return data


def golden_fingerprint(report: dict[str, Any]) -> tuple[str, int]:
    """Identity of the golden set that produced this report."""
    golden = report.get("golden")
    if isinstance(golden, dict):
        path = str(golden.get("path") or golden.get("file") or "")
        count = int(golden.get("entries") or golden.get("count") or 0)
        return path, count
    return str(golden or ""), int(report.get("entries") or 0)


def ratio(numerator: Any, denominator: Any) -> float | None:
    try:
        num, den = float(numerator), float(denominator)
    except (TypeError, ValueError):
        return None
    if den == 0:
        return None
    return num / den


def derived(metrics: dict[str, Any]) -> dict[str, float | None]:
    """Rates this comparison reasons about, plus the raw rates already stored."""
    out: dict[str, float | None] = {}
    # eval_model.sh already stores these as fractions; keep them if present.
    for key in ("groundedness", "fact_recall"):
        value = metrics.get(key)
        out[key] = float(value) if isinstance(value, (int, float)) else None
    # Recompute the ratios from their raw counts so the comparison cannot be
    # fooled by a report that only stored the numerator.
    pairs = {
        "fact_recall": ("facts_matched", "facts_total"),
        "groundedness": ("sources_valid", "sources_total"),
        "abstention": ("abstention_passed", "abstention_total"),
        "analysis_entries": ("analysis_entries_passed", "analysis_entries"),
    }
    for name, (num_key, den_key) in pairs.items():
        value = ratio(metrics.get(num_key), metrics.get(den_key))
        if value is not None:
            out[name] = value
    return out


def defect_counts(metrics: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key in (
        "ungrounded_answers",
        "invalid_sources",
        "analysis_sections_missing",
        "hypothesis_draft_errors",
        "metric_claims_bad",
    ):
        value = metrics.get(key)
        if isinstance(value, list):
            out[key] = len(value)
        elif isinstance(value, (int, float)):
            out[key] = int(value)
    return out


def compare(baseline: dict[str, Any], tuned: dict[str, Any]) -> dict[str, Any]:
    b_gates: dict[str, Any] = baseline.get("gates") or {}
    t_gates: dict[str, Any] = tuned.get("gates") or {}

    gate_rows: list[dict[str, Any]] = []
    regressed: list[str] = []
    for name in sorted(set(b_gates) | set(t_gates)):
        before, after = bool(b_gates.get(name)), bool(t_gates.get(name))
        # Only a gate the baseline PASSED can regress; one that failed in both
        # runs is not a regression (it is a pre-existing failure, reported).
        if before and not after:
            regressed.append(name)
        gate_rows.append({"gate": name, "baseline": before, "tuned": after})

    b_rates, t_rates = derived(baseline.get("metrics") or {}), derived(
        tuned.get("metrics") or {}
    )
    rate_rows: list[dict[str, Any]] = []
    improved: list[str] = []
    worsened: list[str] = []
    for name in sorted(set(b_rates) | set(t_rates)):
        before, after = b_rates.get(name), t_rates.get(name)
        delta = None
        direction = "flat"
        if before is not None and after is not None:
            delta = after - before
            if delta > 1e-9:
                direction, improved = "up", improved + [name]
            elif delta < -1e-9:
                direction, worsened = "down", worsened + [name]
        rate_rows.append(
            {
                "metric": name,
                "baseline": before,
                "tuned": after,
                "delta": delta,
                "direction": direction,
            }
        )

    b_defects, t_defects = defect_counts(
        baseline.get("metrics") or {}
    ), defect_counts(tuned.get("metrics") or {})
    defect_rows: list[dict[str, Any]] = []
    for name in sorted(set(b_defects) | set(t_defects)):
        before = b_defects.get(name)
        after = t_defects.get(name)
        delta = (after - before) if (before is not None and after is not None) else None
        if delta is not None:
            if delta < 0:
                improved = improved + [name]
            elif delta > 0:
                worsened = worsened + [name]
        defect_rows.append(
            {"defect": name, "baseline": before, "tuned": after, "delta": delta}
        )

    # Sample counts must match for the rates to mean anything.
    b_entries = int(baseline.get("entries") or 0)
    t_entries = int(tuned.get("entries") or 0)
    same_golden = golden_fingerprint(baseline) == golden_fingerprint(tuned)

    if not same_golden:
        decision = "INCOMPARABLE"
        reason = (
            "the two reports were produced from different golden sets "
            f"({golden_fingerprint(baseline)} vs {golden_fingerprint(tuned)}) — "
            "re-run both against the same frozen set before comparing"
        )
    elif b_entries != t_entries:
        decision = "INCOMPARABLE"
        reason = (
            f"sample counts differ (baseline n={b_entries}, tuned n={t_entries}) — "
            "rates from different sample counts are not comparable"
        )
    elif regressed:
        decision = "REJECT"
        reason = "gate regression(s): " + ", ".join(sorted(regressed))
    elif not improved:
        decision = "REJECT"
        reason = "no measured metric improved over the baseline"
    else:
        decision = "ADOPT"
        reason = (
            "all baseline-passing gates still pass and "
            f"{len(improved)} metric(s) improved: " + ", ".join(sorted(improved))
        )

    return {
        "decision": decision,
        "reason": reason,
        "baseline_report": {
            "entries": b_entries,
            "generated_at": baseline.get("generated_at"),
            "passed": baseline.get("passed"),
        },
        "tuned_report": {
            "entries": t_entries,
            "generated_at": tuned.get("generated_at"),
            "passed": tuned.get("passed"),
        },
        "golden_sets_match": same_golden,
        "gates": gate_rows,
        "gate_regressions": sorted(regressed),
        "rates": rate_rows,
        "defects": defect_rows,
        "improved": sorted(set(improved)),
        "worsened": sorted(set(worsened)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare two eval_model.sh reports and decide adopt/reject."
    )
    parser.add_argument("baseline", type=Path, help="baseline eval report JSON")
    parser.add_argument("tuned", type=Path, help="tuned eval report JSON")
    parser.add_argument("--json", type=Path, help="also write the comparison here")
    args = parser.parse_args(argv)

    baseline = load(args.baseline)
    tuned = load(args.tuned)
    result = compare(baseline, tuned)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def fmt(value: Any) -> str:
        return "-" if value is None else f"{value:.4f}" if isinstance(value, float) else str(value)

    print(f"baseline: {args.baseline}  (n={result['baseline_report']['entries']})")
    print(f"tuned:    {args.tuned}  (n={result['tuned_report']['entries']})")
    print()

    print("gates")
    for row in result["gates"]:
        mark = "REGRESSION" if row["gate"] in result["gate_regressions"] else "ok"
        print(f"  {row['gate']:30} baseline={str(row['baseline']):5} "
              f"tuned={str(row['tuned']):5} {mark}")
    print()

    print("rates (tuned - baseline)")
    for row in result["rates"]:
        arrow = {"up": "UP  ", "down": "DOWN", "flat": "    "}[row["direction"]]
        print(f"  {row['metric']:20} {fmt(row['baseline']):>9} -> "
              f"{fmt(row['tuned']):>9}  {arrow} {fmt(row['delta'])}")
    print()

    print("defect counts (lower is better)")
    for row in result["defects"]:
        print(f"  {row['defect']:26} baseline={fmt(row['baseline']):>6} "
              f"tuned={fmt(row['tuned']):>6}  delta={fmt(row['delta'])}")
    print()

    print(f"improved: {', '.join(result['improved']) or 'none'}")
    print(f"worsened: {', '.join(result['worsened']) or 'none'}")
    print()
    print(f"DECISION: {result['decision']}")
    print(f"  {result['reason']}")
    if args.json:
        print(f"\nwrote {args.json}")

    if result["decision"] == "ADOPT":
        return 0
    if result["decision"] == "REJECT":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
