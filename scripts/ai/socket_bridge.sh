#!/usr/bin/env bash
# Bridge the local llama-server to a Unix domain socket so the Dockerized
# backend can reach it without any TCP path through the host firewall.
# The socket is created inside ai_runtime/ (bind-mounted read-only-ish into
# the backend container).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOCK="${REPO_ROOT}/ai_runtime/llama.sock"
PORT="${AI_SERVER_PORT:-8081}"

if [[ -S "${SOCK}" ]] && socat -u OPEN:/dev/null "UNIX-CONNECT:${SOCK}" 2>/dev/null; then
  echo "socket bridge already live at ${SOCK}"
  exit 0
fi
rm -f "${SOCK}"
exec socat "UNIX-LISTEN:${SOCK},fork,reuseaddr,mode=0660" "TCP:127.0.0.1:${PORT}"
