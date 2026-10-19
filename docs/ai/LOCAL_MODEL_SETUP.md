# Local Model Setup (llama.cpp + Qwen3-8B on CUDA)

**Date:** 2026-10-15 · Verified on this machine: Arch Linux host, NVIDIA RTX
3080 12 GB, driver CUDA 12.8-capable, Docker Compose stack.

No Ollama. No cloud. No second copy of the weights: the runtime uses the
`Qwen3-8B-Q4_K_M.gguf` **already in the repo root**.

## 1. TL;DR (fresh machine → working assistant)

```bash
# 0. runtime model (~4.7 GiB download, one time — ONLY if you don't have it)
./scripts/ai/setup_model.sh     # official Qwen HF source + SHA-256 verify

# 1. runtime binaries (~730 MB download, one time)
./scripts/ai/setup_runtime.sh

# 2. secret for the inference server (one time)
printf '\nAI_SERVER_API_KEY=%s\n' "$(openssl rand -hex 32)" >> .env

# 3. inference server on the host
set -a && . ./.env && set +a
setsid -f bash -c 'exec ./scripts/ai/run_server.sh' > /tmp/llama-server.log 2>&1 < /dev/null

# 4. UDS bridge so the container can reach it (UFW blocks container→host TCP here)
setsid -f bash -c 'exec ./scripts/ai/socket_bridge.sh' > /tmp/llama-bridge.log 2>&1 < /dev/null

# 5. backend sees the new env/mounts — must be RECREATED, not restarted
docker compose up -d backend

# 6. prove it works (real completion, real tokens, real GPU)
./scripts/ai/verify_model.sh
```

Expected tail of step 6 on this hardware:

```
OK: streamed 1107 chars, first_token_ms=23, ~276 tokens in 1.54s (178.8 tok/s)
NVIDIA GeForce RTX 3080, 6428 MiB, 12288 MiB, 96 %
verify_model: all checks passed
```

## 2. What each piece is

| Piece | Path | Role |
|---|---|---|
| Weights | `Qwen3-8B-Q4_K_M.gguf` (5 027 783 488 B, repo root) | **Never committed** (gitignored). Obtained only by explicitly running `setup_model.sh` from the official `Qwen/Qwen3-8B-GGUF` source and verified against its SHA-256; no other script fetches it |
| llama.cpp build | `ai_runtime/llama.cpp/llama-server` (release `b11617`, Ubuntu CUDA 12.8 x64) + bundled CUDA 12.x runtime libs | Prebuilt upstream binaries; `setup_runtime.sh` downloads & extracts (idempotent) |
| Server script | `scripts/ai/run_server.sh` | Starts the server; **refuses a non-loopback bind without `AI_SERVER_API_KEY`** |
| Model fetch | `scripts/ai/setup_model.sh` | Optional, explicit: downloads the GGUF from the official Qwen repo (resumable `.part` → verify → rename), or verifies an existing file. Never invoked by `make up`, compose, or tests |
| Bridge | `scripts/ai/socket_bridge.sh` | `socat UNIX-LISTEN:ai_runtime/llama.sock → TCP:127.0.0.1:8081` |
| Verifier | `scripts/ai/verify_model.sh` | GGUF magic → health → real completion → streamed throughput → `nvidia-smi` |
| App side | `backend/app/ai/runtime.py`, `client.py` | Supervision, readiness, metrics, OpenAI-compatible client |

Server flags actually used (see `run_server.sh`): `--model`, `--host`,
`--port`, `--ctx-size`, `--n-gpu-layers -1` (all layers on GPU),
`--parallel 2`, `--no-webui`, `--jinja`. Authentication is delivered via the
`LLAMA_API_KEY` environment variable (the documented env backing of
`--api-key`, see `llama-server --help`) — never as a command-line argument,
so the key cannot leak into `/proc/<pid>/cmdline` through process inspection.

**Residual risk (documented, accepted):** a same-user process can still read
`/proc/<pid>/environ` — env-var authentication is readable by definition —
and the `.env` files hold the source copy. Mitigations in place: `.env` and
bolt.diy's `.env.local` are `0600`, the server binds loopback by default, the
key is never in argv, and UFW is unchanged.

## 3. Why a host process and a socket bridge

- **No NVIDIA container runtime** is registered on this host
  (`docker info` → `Runtimes: runc io.containerd.runc.v2`), so the backend
  container cannot touch the GPU. Inference therefore runs on the host.
- **UFW blocks container→host TCP**, so the container cannot reach
  `host.docker.internal:8081` (verified: connect timeout even to the compose
  gateway). `docker-compose.yml` bind-mounts `./ai_runtime:/run/ai-runtime` and
  sets `AI_SERVER_SOCKET=/run/ai-runtime/llama.sock`; the backend client uses
  `httpx.AsyncHTTPTransport(uds=...)` when `AI_SERVER_SOCKET` is set, falling
  back to TCP otherwise.
- The model file is mounted read-only at `/models/Qwen3-8B-Q4_K_M.gguf` and
  `AI_MODEL_PATH` points the container at it (so `model_valid` checks work
  inside the container).

## 4. Configuration reference (all `AI_*`, defaults in `.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `AI_ENABLED` | `true` | Master switch; `false` → 503 `AI_DISABLED` on every AI route |
| `AI_MODEL_PATH` | `Qwen3-8B-Q4_K_M.gguf` | Absolute, or relative to repo root (container: `/models/…`) |
| `AI_SERVER_BINARY` | `ai_runtime/llama.cpp/llama-server` | Server binary |
| `AI_SERVER_HOST` / `AI_SERVER_PORT` | `127.0.0.1` / `8081` | Host-process bind (loopback; compose passes `host.docker.internal` for its own TCP fallback — the UDS bridge is the sanctioned path) |
| `AI_SERVER_API_KEY` | *(empty; must be set for non-loopback)* | Shared secret, `Authorization: Bearer` on every request |
| `AI_SERVER_SOCKET` | *(empty on host; `/run/ai-runtime/llama.sock` in compose)* | Use the UDS bridge when set |
| `AI_MANAGE_SERVER` | `false` (compose) / `true` (default) | Let the app lifespan spawn the server; `false` because the host process is authoritative here |
| `AI_CONTEXT_LENGTH` | `8192` | `--ctx-size` (with `--parallel 2` → ~4 096 per slot) |
| `AI_MAX_OUTPUT_TOKENS` | `512` | Completion cap |
| `AI_GPU_LAYERS` | `-1` | `-1` = offload every layer |
| `AI_REQUEST_TIMEOUT_SECONDS` | `180` | Per-request read timeout in the client |
| `AI_MAX_CONCURRENT_GENERATIONS` | `2` | App-side semaphore |
| `AI_PER_USER_RATE_LIMIT` | `20` | Chat requests/min per user (0 disables) |
| `AI_MAX_HISTORY_MESSAGES` | `12` | History window sent to the model |
| `AI_TOOL_MAX_ITERATIONS` | `3` | Tool-loop cap |
| `AI_CONVERSATION_RETENTION_DAYS` | `90` | Retention policy value |
| `AI_KNOWLEDGE_ENABLED`, `AI_FEATURE_CASE/EVIDENCE/GRAPH/COPILOT/REPORT_DRAFT` | `true` | Feature/tool toggles, reported by `/ai/status` |
| `AI_LOG_PROMPTS` | `false` | Keep false: never log prompt/answer content |

## 5. Verification ladder (each step isolates a layer)

```bash
# Layer 1 — file & binary
head -c 4 Qwen3-8B-Q4_K_M.gguf            # → GGUF
ai_runtime/llama.cpp/llama-server --version

# Layer 2 — server on the host
curl -s http://127.0.0.1:8081/health       # → 200 (health is unauthenticated)

# Layer 3 — server with auth (completions reject anonymous callers)
KEY=$(grep -E '^AI_SERVER_API_KEY=' .env | cut -d= -f2-)
curl -s http://127.0.0.1:8081/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"model":"local","messages":[{"role":"user","content":"Reply with exactly: pong"}],
       "max_tokens":32,"chat_template_kwargs":{"enable_thinking":false}}'

# Layer 4 — container→server path
docker compose exec -T backend python -c "
import httpx
with httpx.Client(base_url='http://localhost',
                  transport=httpx.HTTPTransport(uds='/run/ai-runtime/llama.sock')) as c:
    print(c.get('/health').status_code)"     # → 200

# Layer 5 — whole product path
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"investigator","password":"investigator-dev-password"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s http://localhost:8000/api/v1/ai/status -H "Authorization: Bearer $TOKEN"
# → "ready": true
```

Or simply: `./scripts/ai/verify_model.sh` (steps 1–5 in one command; it now
loads `AI_SERVER_API_KEY` from `.env` itself).

## 6. Qwen3 "thinking mode" note

Qwen3's chat template defaults to reasoning mode: tokens go to
`reasoning_content` and `content` arrives empty. Every client here
(`backend/app/ai/client.py`, `verify_model.sh`) sends
`chat_template_kwargs: {"enable_thinking": false}` so answers land in `content`.
If you write your own client against the server, do the same, or you will see
"completion returned tokens but empty text".

## 7. Stop / start / logs

```bash
pkill -x llama-server                      # stop inference (server cleans up)
pkill -f "socat.*llama.sock"               # stop the bridge
rm -f ai_runtime/llama.sock               # stale socket after a crash

set -a && . ./.env && set +a
setsid -f bash -c 'exec ./scripts/ai/run_server.sh' > /tmp/llama-server.log 2>&1 < /dev/null
setsid -f bash -c 'exec ./scripts/ai/socket_bridge.sh' > /tmp/llama-bridge.log 2>&1 < /dev/null

tail -f /tmp/llama-server.log              # server log (slots, timings)
docker compose logs -f backend             # app side
```

Use `setsid -f` (fully detached) for the server: a plain background job dies
when the launching shell exits. See `TROUBLESHOOTING.md` for this and other
failure modes.

## 8. What is deliberately NOT here

- **Ollama** — excluded by requirement; nothing in the tree references it.
- **Cloud inference** — no API keys, endpoints or SDKs for remote models exist
  anywhere in the codebase.
- **Silent weights downloads** — nothing fetches a `.gguf` during clone,
  `docker compose up`, install, tests or any unrelated step. The single,
  explicitly-invoked `./scripts/ai/setup_model.sh` is the only script that
  can download the model, and it verifies size + SHA-256 (the checksum
  recorded by the official Qwen repository) before the file is ever used.
- **GPU passthrough into Docker** — considered and rejected (no NVIDIA runtime
  on this host; the container never needs the GPU, only the socket).
