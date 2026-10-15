#!/usr/bin/env bash
# Run the local AI evaluation harness against the live stack.
#
# Scores the frozen golden set in backend/tests/fixtures/ai_golden.jsonl:
#   - groundedness  every cited SourceRef must exist in the DB and belong to
#                   the evaluated case (hard gate: 100%)
#   - abstention    questions about cases the caller cannot access must be
#                   refused (hard gate: 100%)
#   - fact recall   frozen expected facts must appear in answers (reported)
#   - latency       per-request duration (reported)
#
# The harness talks to the real backend over HTTP (real auth, real inference)
# and writes a JSON report (default: ai_runtime/eval_report.json).
#
# Usage:
#   ./scripts/ai/eval_model.sh                     # full run, default report path
#   ./scripts/ai/eval_model.sh --report /tmp/r.json
#   ./scripts/ai/eval_model.sh --username investigator --password ...
#
# Exit code: 0 = all gates pass, 1 = a gate failed, 2 = setup failure
# (backend unreachable, model server not ready, bad golden set).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}/backend"

if [[ ! -x .venv/bin/python ]]; then
  echo "ERROR: backend/.venv missing. Create it first (see README.md)." >&2
  exit 2
fi

# The runner authenticates to the backend, which proxies inference; it never
# talks to the model server directly, so no AI_SERVER_API_KEY is needed here.
export PYTHONPATH="${REPO_ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"

exec .venv/bin/python -m scripts.eval_model "$@"
