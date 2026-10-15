#!/usr/bin/env bash
# Start the local llama.cpp inference server.
#
# Binding policy: the server listens on 0.0.0.0 so the Dockerized backend can
# reach it via the bridge gateway, but it ALWAYS requires an API key
# (AI_SERVER_API_KEY) whenever the bind address is not loopback. Internet
# exposure is never intended — keep host firewalls sane.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODEL="${REPO_ROOT}/Qwen3-8B-Q4_K_M.gguf"
BIN="${REPO_ROOT}/ai_runtime/llama.cpp/llama-server"
HOST="${AI_SERVER_HOST:-0.0.0.0}"
PORT="${AI_SERVER_PORT:-8081}"
CTX="${AI_CONTEXT_LENGTH:-8192}"
NGPU_LAYERS="${AI_GPU_LAYERS:--1}"
API_KEY="${AI_SERVER_API_KEY:-}"

if [[ ! -f "${MODEL}" ]]; then
  echo "ERROR: model not found at ${MODEL}" >&2
  echo "Place the Qwen3-8B GGUF file at the repo root (see docs/ai/LOCAL_MODEL_SETUP.md)." >&2
  exit 1
fi
if [[ ! -x "${BIN}" ]]; then
  echo "ERROR: llama-server not found. Run scripts/ai/setup_runtime.sh first." >&2
  exit 1
fi
if [[ "${HOST}" != "127.0.0.1" && "${HOST}" != "localhost" && -z "${API_KEY}" ]]; then
  echo "ERROR: AI_SERVER_API_KEY is required when binding to ${HOST}." >&2
  echo "Generate one (openssl rand -hex 32) and add it to .env as AI_SERVER_API_KEY." >&2
  exit 1
fi

# Prefer the CUDA 12.x runtime libs shipped with the prebuilt binary; fall
# back to the system CUDA toolkit if the bundle is absent.
LIB_DIR="${REPO_ROOT}/ai_runtime/llama.cpp"
if [[ -d "${LIB_DIR}" ]]; then
  export LD_LIBRARY_PATH="${LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
fi

ARGS=(
  --model "${MODEL}"
  --host "${HOST}"
  --port "${PORT}"
  --ctx-size "${CTX}"
  --n-gpu-layers "${NGPU_LAYERS}"
  --parallel 2
  --no-webui
  --jinja
)
if [[ -n "${API_KEY}" ]]; then
  ARGS+=(--api-key "${API_KEY}")
fi

exec "${BIN}" "${ARGS[@]}"
