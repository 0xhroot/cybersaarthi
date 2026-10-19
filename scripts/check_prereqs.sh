#!/usr/bin/env bash
# Check every prerequisite CyberSaarthi needs, and say exactly what is
# missing. Read-only: nothing is installed, downloaded or modified.
#
#   ./scripts/check_prereqs.sh
#
# Exit code 0 = everything needed for the full stack (including AI features)
# is present; 1 = something required is missing (each gap is printed with the
# command that fixes it on Debian/Ubuntu).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0

ok()   { printf 'OK    %-12s %s\n' "$1" "$2"; }
miss() { printf 'MISS  %-12s %s\n' "$1" "$2"; FAIL=1; }
note() { printf 'NOTE  %-12s %s\n' "$1" "$2"; }

echo "== CyberSaarthi prerequisites =="

# --- Docker + compose plugin -------------------------------------------------
if command -v docker >/dev/null 2>&1; then
  ok docker "$(docker --version | head -n1)"
  if docker compose version >/dev/null 2>&1; then
    ok compose "$(docker compose version | head -n1)"
  else
    miss compose "Docker Compose v2 plugin missing — install docker-compose-plugin"
  fi
  if docker info >/dev/null 2>&1; then
    ok daemon "Docker daemon is reachable"
  else
    miss daemon "Docker daemon not reachable — is Docker running / do you have permission? (sudo usermod -aG docker \$USER)"
  fi
else
  miss docker "not found — install: https://docs.docker.com/engine/install/"
  miss compose "requires Docker"
fi

# --- Node.js (frontend) -------------------------------------------------------
if command -v node >/dev/null 2>&1; then
  NODE_MAJOR="$(node --version | sed 's/^v//' | cut -d. -f1)"
  if (( NODE_MAJOR >= 22 )); then
    ok node "v${NODE_MAJOR} (>= 22 required)"
  else
    miss node "$(node --version) found, but >= 22 is required"
  fi
else
  miss node "not found — install Node.js 22+ (https://nodejs.org)"
fi

# --- Python (backend tooling, migrations, seeds) ------------------------------
if command -v python3 >/dev/null 2>&1; then
  PY_MINOR="$(python3 --version | sed 's/.* \([0-9]*\)\.[0-9]*\.[0-9]*/\1/')"
  if (( PY_MINOR >= 3 )); then
    ok python3 "$(python3 --version)"
  fi
else
  miss python3 "not found — install Python 3.12+ (backend itself runs inside Docker)"
fi

# --- GPU (optional but recommended for AI features) ---------------------------
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  ok gpu "$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -n1)"
else
  note gpu "no NVIDIA GPU detected — AI features still run on CPU, but slowly. See docs/ai/LOCAL_MODEL_SETUP.md"
fi

# --- Disk space (the model alone needs ~4.7 GiB) ------------------------------
FREE_GB="$(df -Pk "${REPO_ROOT}" | awk 'NR==2 {print int($4/1048576)}')"
if (( FREE_GB >= 10 )); then
  ok disk "${FREE_GB} GiB free"
elif (( FREE_GB >= 6 )); then
  note disk "${FREE_GB} GiB free — enough for the stack + model, little headroom"
else
  miss disk "only ${FREE_GB} GiB free; ~6 GiB is needed (stack + AI model)"
fi

# --- Model file (informational; fetched by its own script) --------------------
MODEL="${REPO_ROOT}/Qwen3-8B-Q4_K_M.gguf"
if [[ -f "${MODEL}" ]]; then
  ok model "present ($(stat -c%s "${MODEL}") bytes) — verify with ./scripts/ai/verify_model.sh"
else
  note model "not present — AI features need it: ./scripts/ai/setup_model.sh (~4.7 GiB, official Qwen source)"
fi

echo
if (( FAIL == 0 )); then
  echo "All prerequisites satisfied. Next steps:"
  echo "  cp .env.example .env      # then edit secrets"
  echo "  docker compose up -d"
  echo "  cd frontend && npm install && npm run dev"
else
  echo "Some prerequisites are missing (MISS lines above). Fix them and re-run."
  exit 1
fi
