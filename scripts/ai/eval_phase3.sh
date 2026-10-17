#!/usr/bin/env bash
# Run the phase-3 case-intelligence evaluation harness.
#
# Two sections:
#   - deterministic golden-fixture metrics (always run, no stack needed):
#       entity-match precision/recall with a hard zero false-merge gate,
#       timeline parse precision/recall + exact timestamp correctness +
#       locator validity (zero invented timestamps),
#       contradiction classifier accuracy + anchored-comparison precision/
#       recall with a hard zero entity-anchor false-positive gate,
#       anti-vacuous gates (a feature that finds nothing fails).
#   - live end-to-end (requires running stack + local model): real HTTP jobs,
#     independent PostgreSQL verification of provenance, approval -> additive
#     aliases with no merge, idempotent timeline commits, contradiction child
#     artifacts, per-feature latency.
#
# Usage:
#   ./scripts/ai/eval_phase3.sh                  # full evaluation
#   ./scripts/ai/eval_phase3.sh --skip-live      # golden metrics only (offline)
#   ./scripts/ai/eval_phase3.sh --report /tmp/p3.json
#
# Exit code: 0 = all gates pass, 1 = a gate failed, 2 = setup failure.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}/backend"

if [[ ! -x .venv/bin/python ]]; then
  echo "ERROR: backend/.venv missing. Create it first (see README.md)." >&2
  exit 2
fi

exec .venv/bin/python -m scripts.eval_phase3 "$@"
