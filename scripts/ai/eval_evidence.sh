#!/usr/bin/env bash
# Run the phase-2 evidence-intelligence evaluation harness against the live stack.
#
# Measures (real HTTP, real local model, independent DB/MinIO verification):
#   - claim recall, extraction precision, field-level validation rate,
#     unsupported-claim rate          (reported; model quality)
#   - locator accuracy                (hard gate: 100%, re-verified from DB)
#   - hash verification correctness   (hard gate: match/mismatch/missing_source)
#   - custody rule agreement + zero false positives (hard gate)
#
# Usage:
#   ./scripts/ai/eval_evidence.sh
#   ./scripts/ai/eval_evidence.sh --report /tmp/ei.json
#
# Exit code: 0 = all gates pass, 1 = a gate failed, 2 = setup failure.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}/backend"

if [[ ! -x .venv/bin/python ]]; then
  echo "ERROR: backend/.venv missing. Create it first (see README.md)." >&2
  exit 2
fi

exec .venv/bin/python -m scripts.eval_evidence "$@"
