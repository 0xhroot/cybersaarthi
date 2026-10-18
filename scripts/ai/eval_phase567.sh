#!/usr/bin/env bash
# Run the phase-5/6 evaluation harness (currently: phase 5A multilingual).
#
# Two sections:
#   - deterministic golden-fixture metrics (always run, no stack needed):
#       exact Unicode script profiles (independently derived character
#       counts + candidate), language/script cross-check exactness,
#       ambiguity-flag exactness, negation detection (incl. Marathi),
#       per-value source containment (false accepts/rejects gated),
#       instruction-context injection withholding (leaks and false
#       withholdings gated), translation material-preservation exactness
#       with the total == preserved + missing invariant, parse
#       accept/reject exactness, anti-vacuous gates, determinism.
#   - live end-to-end (requires running stack + local model): real HTTP
#     jobs against local Qwen3 (Hindi auto-translate, Hindi + English with
#     translation, unsupported-script refusal), cancellation probe,
#     original-records verbatim viewer, anonymous / non-member / cross-case
#     IDOR probes, independent PostgreSQL recompute of every stored value,
#     profile/flags/material/negation exactness, locator validity,
#     API-vs-database agreement, no auto-approval, complaint-free audit
#     metadata (counts/identifiers only), per-run latency.
#
# Usage:
#   ./scripts/ai/eval_phase567.sh              # full evaluation
#   ./scripts/ai/eval_phase567.sh --skip-live  # golden metrics only (offline)
#   ./scripts/ai/eval_phase567.sh --report /tmp/p567.json
#
# Exit code: 0 = all gates pass, 1 = a gate failed, 2 = setup failure.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}/backend"

if [[ ! -x .venv/bin/python ]]; then
  echo "ERROR: backend/.venv missing. Create it first (see README.md)." >&2
  exit 2
fi

exec .venv/bin/python -m scripts.eval_phase567 "$@"
