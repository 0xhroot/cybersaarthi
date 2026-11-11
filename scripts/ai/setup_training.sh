#!/usr/bin/env bash
# Build the isolated local training stack into ai_runtime/soup/.venv.
#
# The venv is git-ignored (like every other ai_runtime/ artifact), so this
# script is how a fresh clone reproduces the environment the fine-tuning
# report was measured in. Nothing here touches backend/.venv or the Docker
# image — training deps stay in their own venv (isolation rule, see
# docs/architecture/local-ai-training.md).
#
# Requirements:
#   - uv (https://docs.astral.sh/uv/) — creates the venv with a pinned
#     CPython 3.12. The host's system Python (3.14) is unsupported by Soup.
#   - network access to PyPI for the first run only.
#
# Idempotent: an existing venv is upgraded in place, not recreated.
#
# Usage:
#   scripts/ai/setup_training.sh           # install/refresh
#   scripts/ai/setup_training.sh --check   # verify only, install nothing
#
# After this succeeds: `make train-check` (doctor + dry-run), then
# `make train-pilot` (the measured training run).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

VENV_DIR="${REPO_ROOT}/ai_runtime/soup/.venv"
SOUP="${VENV_DIR}/bin/soup"
# soup-cli's own extras carry the training stack; the `liger` extra pulls
# liger-kernel, which soup.yaml's `use_liger: true` requires (fused linear
# cross-entropy — without it a 151k-vocab model OOMs on the logits tensor
# at 12 GB, see scripts/ai/peft_upcast_guard.py for the full memory story).
# Version pins live in soup's own metadata; the measured versions are
# recorded in docs/ai/FINE_TUNING_REPORT.md.
SPECS=("soup-cli[train,liger]==0.76.1")

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv not found on PATH — install it first: https://docs.astral.sh/uv/" >&2
  exit 2
fi

if [[ "${1:-}" == "--check" ]]; then
  if [[ ! -x "${SOUP}" ]]; then
    echo "error: ${SOUP} missing — run scripts/ai/setup_training.sh first" >&2
    exit 1
  fi
  "${SOUP}" doctor
  PYTHONPATH="${REPO_ROOT}/scripts/ai" "${VENV_DIR}/bin/python" -c \
    "import peft_upcast_guard as g; raise SystemExit(0 if g.APPLIED else 'peft upcast guard not installed')"
  echo "training stack: OK"
  exit 0
fi

mkdir -p "$(dirname "${VENV_DIR}")"

if [[ ! -x "${SOUP}" ]]; then
  echo "creating ${VENV_DIR} (CPython 3.12 — Soup does not support the host Python)..."
  uv venv --python 3.12 "${VENV_DIR}"
fi

echo "installing: ${SPECS[*]}"
uv pip install --python "${VENV_DIR}/bin/python" "${SPECS[@]}"

echo "verifying..."
"${SOUP}" doctor
PYTHONPATH="${REPO_ROOT}/scripts/ai" "${VENV_DIR}/bin/python" -c \
  "import peft_upcast_guard as g; raise SystemExit(0 if g.APPLIED else 'peft upcast guard not installed')" \
  && echo "peft upcast guard: ok"
echo "training stack ready: ${SOUP}"
echo "next: make train-check && make train-pilot"
