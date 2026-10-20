# AI Subsystem — Troubleshooting

**Date:** 2026-10-15 · Every entry below is a failure mode that actually occurred
on this machine (during the lost session, this audit, or both) with the fix that
was verified to work.

## Quick triage

```bash
# 1. Is the inference server up?
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8081/health      # want 200
pgrep -x llama-server                                                      # want a pid

# 2. Is the bridge alive?
test -S ai_runtime/llama.sock && echo socket-present
pgrep -f "socat.*llama.sock"

# 3. Does the container see it?
docker compose exec -T backend python -c "
import httpx
with httpx.Client(base_url='http://localhost',
                  transport=httpx.HTTPTransport(uds='/run/ai-runtime/llama.sock')) as c:
    print(c.get('/health').status_code)"                                   # want 200

# 4. What does the app think?
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"investigator","password":"investigator-dev-password"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s http://localhost:8000/api/v1/ai/status -H "Authorization: Bearer $TOKEN"

# 5. Full smoke test
./scripts/ai/verify_model.sh
```

## Symptoms → causes → fixes

### `/ai/status` says `"ready": false` but the server is fine

The status route probes live, so this is a *connectivity* problem from the
container, not a stale flag. Check the bridge (step 3 above). If the socket is
missing (crashed bridge), restart it:

```bash
rm -f ai_runtime/llama.sock
setsid -f bash -c 'exec ./scripts/ai/socket_bridge.sh' >/tmp/llama-bridge.log 2>&1 </dev/null
```

### Chat returns 503 `AI_UNAVAILABLE`

Runtime unreachable or a generation failed. `AI_UNAVAILABLE` (not 500) is the
intended mapping — the platform keeps working. Check
`docker compose logs backend | grep -i "AI stream failed"` and the server log.
Then restart the server (see below). Verify with a real completion:
`./scripts/ai/verify_model.sh`.

### Chat returns 503 `AI_DISABLED`

`AI_ENABLED=false` in `.env` — deliberate kill switch. Re-enable and restart.

### Completion succeeds but `content` is empty (tokens counted, text blank)

**Qwen3 thinking mode.** The template routes reasoning to `reasoning_content`
and leaves `content` empty. Fix: send
`"chat_template_kwargs": {"enable_thinking": false}` — already done in
`backend/app/ai/client.py` and `scripts/ai/verify_model.sh`. If you wrote your
own client against the server, add it there too.

### HTTP 400 from the server on case-scoped prompts ("prompt too long" class)

**Context split by `--parallel`.** With `--ctx-size 4096 --parallel 2` each of
the 2 slots gets ~2 096 tokens; a grounded prompt needs more. This bit us
once (prompt needed 3 947 tokens). Fixes applied: `AI_CONTEXT_LENGTH=8192` and
trimmed retrieval budgets (`retrieval.py` clip limits). If it recurs, either
lower `--parallel`, raise the context, or reduce the digests. The API answer is
a clean 503, never a leak.

### The server dies right after starting (log: "cleaning up before exit" at 0.3 s)

**It was launched as a child of a shell that exited.** `nohup … &` inside a
command that later times out gets reaped with it. Use `setsid -f` (fully
detached, returns immediately):

```bash
pkill -x llama-server      # NOTE: -x, exact name only
sleep 2
cd /path/to/CyberSaarthi && set -a && . ./.env && set +a
setsid -f bash -c 'exec ./scripts/ai/run_server.sh' >/tmp/llama-server.log 2>&1 </dev/null
sleep 12 && tail -2 /tmp/llama-server.log
```

**Related trap:** `pkill -f "llama-server --model"` can match your *own* shell
command line and kill the very command you're running. Always `pkill -x llama-server`.

### `run_server.sh` refuses to start: "AI_SERVER_API_KEY is required when binding to 0.0.0.0"

Working as designed — the server binds all interfaces so the container can reach
it, so it must never be keyless:

```bash
printf '\nAI_SERVER_API_KEY=%s\n' "$(openssl rand -hex 32)" >> .env
```

Then relaunch with the env sourced (`set -a && . ./.env && set +a`).

### Completions return 401 from the server

The key isn't reaching the caller. `verify_model.sh` now loads it from `.env`
itself; for your own scripts, export `AI_SERVER_API_KEY` or read it from `.env`.
`/health` stays open; `/v1/*` requires the key (verified: no key → 401).

### Container can't reach the server over TCP (`ConnectTimeout` to `host.docker.internal:8081`)

**UFW blocks container→host TCP on this host** (even to the compose gateway).
Do not fight the firewall — use the socket bridge, which is the configured path:

```bash
setsid -f bash -c 'exec ./scripts/ai/socket_bridge.sh' >/tmp/llama-bridge.log 2>&1 </dev/null
# compose must mount ./ai_runtime → /run/ai-runtime and set AI_SERVER_SOCKET
docker compose up -d backend
```

If you *must* use TCP, the host needs `sudo ufw allow in on docker0 to any port 8081`
(also for the compose bridge `br-<id>`) — not done here, by design.

### Changed `.env`, compose mounts, `extra_hosts`, or env defaults — nothing changed in the running container

**`docker compose restart` does not apply env/volume/network changes.** Use
`docker compose up -d backend` to *recreate* the container. (Code changes under
the `./backend` bind mount only need a restart.)

### `/ai/status` shows `gpu_name: null`, `vram_*: null`

Expected inside the container — there is no `nvidia-smi` in it, and the container
doesn't need the GPU. The real numbers live on the host:

```bash
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader
nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv,noheader
```

### Stale socket file after a crash (`connect: No such file or directory` / connection refused)

```bash
rm -f ai_runtime/llama.sock && setsid -f bash -c 'exec ./scripts/ai/socket_bridge.sh' >/tmp/llama-bridge.log 2>&1 </dev/null
```

### `model_valid: false` from the container but the file exists on the host

The model is mounted read-only at `/models/Qwen3-8B-Q4_K_M.gguf` and
docker-compose.yml pins the container's `AI_MODEL_PATH` to that path. The
host path (`./Qwen3-8B-Q4_K_M.gguf`) is invisible to the container; `.env`'s
repo-root-relative value applies to host-side runs only.

### Frontend assistant shows the offline banner though the API works

`/ai/status` requires a JWT — the banner's re-probe must run with the logged-in
session. Log in (or refresh the token) and press Retry on the banner. A 401 here
means "not authenticated", not "AI down".

### Assistant shows raw ```` ```tool_call ```` JSON before the answer

The stream client isn't honouring the `tool`-event contract: tokens streamed
*before* a `tool` event are the model's raw fence and must be discarded. The
reference implementation (`frontend/src/components/ai/assistant.tsx`) clears its
buffer on `tool`; copy that if you write another client.

### `backend-dev` container fails on a missing import (e.g. `pypdf`)

The dev image predates a dependency bump. Rebuild it:
`docker compose build backend-dev`.

### Tests: 429 `AI_RATE_LIMITED` in API tests

The limiter is real (20/min/user). Tests stub or lower
`AI_PER_USER_RATE_LIMIT`; if you add many AI tests in one minute, raise the limit
in the test fixture rather than deleting the limiter.

## Restarting everything cleanly

```bash
# inference
pkill -x llama-server; pkill -f "socat.*llama.sock"; rm -f ai_runtime/llama.sock
cd /path/to/CyberSaarthi && set -a && . ./.env && set +a
setsid -f bash -c 'exec ./scripts/ai/run_server.sh'      >/tmp/llama-server.log 2>&1 </dev/null
setsid -f bash -c 'exec ./scripts/ai/socket_bridge.sh'   >/tmp/llama-bridge.log 2>&1 </dev/null
sleep 12 && ./scripts/ai/verify_model.sh

# backend (recreate if compose config changed)
docker compose up -d backend && sleep 12
docker compose ps backend        # want "(healthy)"
```

## Where to look

| Log | Contains |
|---|---|
| `/tmp/llama-server.log` | model load, per-slot timings (`print_timing`), auth warnings |
| `docker compose logs -f backend` | app-side AI warnings, tool audits, stream failures |
| `ai_runtime/llama.sock` | bridge endpoint (remove if stale) |
