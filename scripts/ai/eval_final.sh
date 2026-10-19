#!/usr/bin/env bash
# Run the Phase-7 combined evaluation over all ten AI features.
#
# Orchestrates the per-phase harnesses (phases 1-6) as subprocesses and
# merges their gates, plus cross-cutting delivery gates:
#   - every included harness ran clean (report-checked, not exit-code-only)
#   - per-feature coverage: each of the ten features maps to a measured
#     golden section (non-zero n=) or a live end-to-end run
#   - test-inventory floor (collected counts; anti-vacuous, no execution)
#   - alembic heads == the single expected head (migration history intact)
#   - error-shape probe (live mode): anonymous 401 carries the documented
#     {"error": {"code", "message"}} contract
#
# Individual phase metrics (precision/recall/FPR, n=, limitations) stay in
# their own phase reports inside the combined JSON - never merged or diluted.
#
# Usage:
#   ./scripts/ai/eval_final.sh                          # golden + live
#   ./scripts/ai/eval_final.sh --skip-live              # golden only (offline)
#   ./scripts/ai/eval_final.sh --report /tmp/final.json
#
# Exit code: 0 = all gates pass, 1 = a gate failed, 2 = setup failure.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}/backend"

if [[ ! -x .venv/bin/python ]]; then
  echo "ERROR: backend/.venv missing. Create it first (see README.md)." >&2
  exit 2
fi

exec .venv/bin/python -m scripts.eval_final "$@"
