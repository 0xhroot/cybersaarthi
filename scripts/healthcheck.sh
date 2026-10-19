#!/usr/bin/env bash
# Verify a running CyberSaarthi stack, end to end. Read-only.
#
#   ./scripts/healthcheck.sh
#
# Checks: compose services, backend /health + /ready, database connectivity,
# the local AI runtime (/api/v1/ai/status) and the frontend dev server.
# Exit 0 = everything checked is healthy.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${BACKEND_URL:-http://localhost:8000}"
FRONTEND="${FRONTEND_URL:-http://localhost:5173}"
FAIL=0

ok()   { printf 'OK    %-10s %s\n' "$1" "$2"; }
bad()  { printf 'FAIL  %-10s %s\n' "$1" "$2"; FAIL=1; }
note() { printf 'NOTE  %-10s %s\n' "$1" "$2"; }

echo "== CyberSaarthi health =="

# --- Compose services ---------------------------------------------------------
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  UNHEALTHY="$(cd "${REPO_ROOT}" && docker compose ps --format '{{.Name}} {{.Health}}' 2>/dev/null \
    | awk '$2=="unhealthy" || $2=="running" {print}' | grep -c 'unhealthy' || true)"
  RUNNING="$(cd "${REPO_ROOT}" && docker compose ps --format '{{.State}}' 2>/dev/null | grep -c running || true)"
  if (( UNHEALTHY > 0 )); then
    bad compose "${UNHEALTHY} service(s) unhealthy — see: docker compose ps"
  elif (( RUNNING > 0 )); then
    ok compose "${RUNNING} service(s) running"
  else
    bad compose "no services running — start with: docker compose up -d"
  fi
else
  note compose "docker compose not available; skipping service check"
fi

# --- Backend health + readiness ----------------------------------------------
health_code="$(curl -s -o /dev/null -w '%{http_code}' "${BACKEND}/api/v1/health" || echo 000)"
if [[ "${health_code}" == "200" ]]; then
  ok backend "${BACKEND}/api/v1/health -> 200"
else
  bad backend "${BACKEND}/api/v1/health -> ${health_code} (is the stack up?)"
fi

ready_code="$(curl -s -o /dev/null -w '%{http_code}' "${BACKEND}/api/v1/ready" || echo 000)"
if [[ "${ready_code}" == "200" ]]; then
  ok ready "${BACKEND}/api/v1/ready -> 200 (database reachable)"
else
  bad ready "${BACKEND}/api/v1/ready -> ${ready_code}"
fi

# --- Local AI runtime ---------------------------------------------------------
# /api/v1/ai/status requires an authenticated user, so this checks the llama
# server's own health endpoint instead (same API key the backend uses).
REPO_KEY=""
if [[ -f "${REPO_ROOT}/.env" ]]; then
  REPO_KEY="$(grep -E '^AI_SERVER_API_KEY=' "${REPO_ROOT}/.env" | head -n1 | cut -d= -f2- || true)"
fi
LLAMA="http://${AI_SERVER_HOST:-127.0.0.1}:${AI_SERVER_PORT:-8081}/health"
if [[ -n "${REPO_KEY:-${AI_SERVER_API_KEY:-}}" ]]; then
  LLAMA_OK="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${AI_SERVER_API_KEY:-$REPO_KEY}" "${LLAMA}" || echo 000)"
else
  LLAMA_OK="$(curl -s -o /dev/null -w '%{http_code}' "${LLAMA}" || echo 000)"
fi
if [[ "${LLAMA_OK}" == "200" ]]; then
  ok ai "${LLAMA} -> 200"
else
  bad ai "${LLAMA} -> ${LLAMA_OK} — AI features are down. See docs/ai/TROUBLESHOOTING.md"
fi

# --- Frontend dev server ------------------------------------------------------
FE_CODE="$(curl -s -o /dev/null -w '%{http_code}' "${FRONTEND}/" || echo 000)"
if [[ "${FE_CODE}" == "200" ]]; then
  ok frontend "${FRONTEND} -> 200"
else
  bad frontend "${FRONTEND} -> ${FE_CODE} (start with: cd frontend && npm run dev)"
fi

echo
if (( FAIL == 0 )); then
  echo "All checks passed."
else
  echo "Some checks failed (FAIL lines above)."
  exit 1
fi
