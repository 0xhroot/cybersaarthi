#!/usr/bin/env bash
# Run the phase-4 financial-flow + cross-case evaluation harness.
#
# Two sections:
#   - deterministic golden-fixture metrics (always run, no stack needed):
#       exact aggregation (per-currency buckets, per-status separation,
#       per-account/bank splits), pattern precision/recall with honest
#       not_evaluable/not_fired reporting, structure-network exactness,
#       bounded trace path correctness, cross-case candidate
#       precision/recall + classification exactness (name-only never
#       reviewable), conflict-flag exactness, evidence-hash candidates,
#       side provenance, bounds probes, determinism, anti-vacuous gates.
#   - live end-to-end (requires running stack + local model): real HTTP jobs,
#     independent PostgreSQL recompute of aggregates, trace probes
#     (association ok / transfer insufficient_data / unknown not_found),
#     a cancellation branch probe, cross-case discovery over
#     investigator + admin cases with read-time omission and no-leak
#     refusals, audited approval of a candidate, anonymous / VIEWER /
#     scope-denied probes, per-feature latency.
#
# Usage:
#   ./scripts/ai/eval_phase4.sh                  # full evaluation
#   ./scripts/ai/eval_phase4.sh --skip-live      # golden metrics only (offline)
#   ./scripts/ai/eval_phase4.sh --report /tmp/p4.json
#
# Exit code: 0 = all gates pass, 1 = a gate failed, 2 = setup failure.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}/backend"

if [[ ! -x .venv/bin/python ]]; then
  echo "ERROR: backend/.venv missing. Create it first (see README.md)." >&2
  exit 2
fi

exec .venv/bin/python -m scripts.eval_phase4 "$@"
