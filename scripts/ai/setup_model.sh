#!/usr/bin/env bash
# Fetch the local inference model from its OFFICIAL source and verify it.
#
#   Model : Qwen3-8B-Q4_K_M.gguf  (Qwen3-8B, 4-bit, instruct)
#   Source: https://huggingface.co/Qwen/Qwen3-8B-GGUF  (official Qwen org)
#   Size  : 5,027,783,488 bytes (~4.68 GiB)
#   SHA-256: d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785
#   License : Apache-2.0 (see the model card on Hugging Face)
#
# Why not committed to this repository? The file is ~5 GB. GitHub LFS caps
# files at 2 GB on the free plan and release assets at 2 GiB, so neither can
# host it; the model is therefore obtained from its official publisher and
# verified against the checksum below, which is the SHA-256 recorded by the
# Qwen repository itself for this exact file.
#
# This script is the ONLY step that downloads the model. It is never invoked
# by `make up`, the compose stack, or any install/test command. It is safe to
# re-run: an existing, correctly-hashed file is left untouched, and a partial
# download resumes from the .part file.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODEL="${REPO_ROOT}/Qwen3-8B-Q4_K_M.gguf"
URL="https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf"
EXPECTED_SHA256="d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785"
EXPECTED_BYTES="5027783488"

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

echo "== model setup =="

# 1. Already present? Verify and stop — never re-download a good file.
if [[ -f "${MODEL}" ]]; then
  echo "found existing ${MODEL} ($(stat -c%s "${MODEL}") bytes); verifying..."
  ACTUAL="$(sha256_of "${MODEL}")"
  if [[ "${ACTUAL}" == "${EXPECTED_SHA256}" ]]; then
    echo "OK: checksum matches; nothing to download."
    exit 0
  fi
  echo "WARN: checksum mismatch (got ${ACTUAL})." >&2
  echo "      The file will NOT be replaced automatically. Inspect it, then" >&2
  echo "      move it aside and re-run this script to fetch a verified copy." >&2
  exit 1
fi

# 2. Disk space: refuse to start a download we cannot finish.
FREE_KB="$(df -Pk "${REPO_ROOT}" | awk 'NR==2 {print $4}')"
NEED_KB="$((EXPECTED_BYTES / 1024 + 1048576))" # model + 1 GiB headroom
if (( FREE_KB < NEED_KB )); then
  echo "FAIL: insufficient free space — need ~$((NEED_KB / 1048576)) GiB," >&2
  echo "      only $((FREE_KB / 1048576)) GiB available on $(df -h "${REPO_ROOT}" | awk 'NR==2 {print $6}')." >&2
  exit 1
fi

# 3. Download to a .part file (resumable), verify, then atomically rename.
#    A partially-downloaded file is never left under the final name.
PART="${MODEL}.part"
if [[ -f "${PART}" ]]; then
  echo "resuming partial download ($(stat -c%s "${PART}") bytes)..."
fi
echo "downloading ${URL}"
echo "  -> ${MODEL} (~4.7 GiB, one-time)"
curl -fL --retry 3 --retry-delay 5 -C - -o "${PART}" "${URL}"

SIZE="$(stat -c%s "${PART}")"
if [[ "${SIZE}" != "${EXPECTED_BYTES}" ]]; then
  echo "FAIL: size mismatch — expected ${EXPECTED_BYTES} bytes, got ${SIZE}." >&2
  echo "      The .part file is kept for resume; re-run to retry." >&2
  exit 1
fi

echo "verifying SHA-256..."
ACTUAL="$(sha256_of "${PART}")"
if [[ "${ACTUAL}" != "${EXPECTED_SHA256}" ]]; then
  echo "FAIL: checksum mismatch." >&2
  echo "      expected ${EXPECTED_SHA256}" >&2
  echo "      got      ${ACTUAL}" >&2
  echo "      Do not use this file. Re-run to fetch a fresh copy." >&2
  rm -f "${PART}"
  exit 1
fi

mv "${PART}" "${MODEL}"
echo "OK: ${MODEL}"
echo "    ${EXPECTED_BYTES} bytes · sha256 ${EXPECTED_SHA256}"
echo "    license: Apache-2.0 · source: Qwen/Qwen3-8B-GGUF (official)"
echo
echo "Next: start the stack and check the runtime:"
echo "  ./scripts/ai/verify_model.sh        # GGUF magic, health, real completion"
echo "  curl -s http://localhost:8000/api/v1/ai/status"
