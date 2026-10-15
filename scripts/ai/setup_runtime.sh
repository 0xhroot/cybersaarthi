#!/usr/bin/env bash
# Download and unpack the prebuilt llama.cpp CUDA server into ai_runtime/.
#
# Two assets are required:
#   1. llama-b*-bin-ubuntu-cuda-*-x64.tar.gz  — llama-server binaries (~164 MB)
#   2. cudart-llama-b*-bin-ubuntu-cuda-*-x64.tar.gz — CUDA 12.x runtime libs
#      (~566 MB), needed because the host may only have newer system CUDA.
#
# Idempotent: re-running with an existing binary is a no-op.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_DIR="${REPO_ROOT}/ai_runtime"
BIN_DIR="${RUNTIME_DIR}/llama.cpp"
BIN_ARCHIVE="${RUNTIME_DIR}/llama-bin.tar.gz"
CUDART_ARCHIVE="${RUNTIME_DIR}/llama-cuda.tar.gz"
RELEASE_TAG="b11617"
BIN_ASSET="llama-${RELEASE_TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz"
CUDART_ASSET="cudart-llama-${RELEASE_TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz"
BASE_URL="https://github.com/ggml-org/llama.cpp/releases/download/${RELEASE_TAG}"

if [[ -x "${BIN_DIR}/llama-server" ]]; then
  echo "llama-server already present at ${BIN_DIR}/llama-server"
  "${BIN_DIR}/llama-server" --version || true
  exit 0
fi

mkdir -p "${RUNTIME_DIR}"

fetch() {
  local asset="$1" dest="$2"
  if [[ -f "${dest}" ]]; then
    echo "already downloaded: $(basename "${dest}")"
    return
  fi
  echo "downloading ${asset} ..."
  curl -fL --retry 3 --retry-delay 5 -o "${dest}.part" "${BASE_URL}/${asset}"
  mv "${dest}.part" "${dest}"
}

fetch "${BIN_ASSET}" "${BIN_ARCHIVE}"
fetch "${CUDART_ASSET}" "${CUDART_ARCHIVE}"

echo "extracting into ${BIN_DIR} ..."
mkdir -p "${BIN_DIR}"
tar -xzf "${BIN_ARCHIVE}" -C "${BIN_DIR}" --strip-components=1
tar -xzf "${CUDART_ARCHIVE}" -C "${BIN_DIR}" --strip-components=1

if [[ ! -x "${BIN_DIR}/llama-server" ]]; then
  echo "ERROR: llama-server missing after extraction" >&2
  exit 1
fi

echo "verifying binary ..."
"${BIN_DIR}/llama-server" --version
echo "runtime ready: ${BIN_DIR}/llama-server"
