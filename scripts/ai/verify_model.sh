#!/usr/bin/env bash
# Verify the local inference runtime: GGUF magic, server health, a real
# completion, and (when nvidia-smi is available) GPU usage during generation.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODEL="${REPO_ROOT}/Qwen3-8B-Q4_K_M.gguf"
BASE_URL="http://${AI_SERVER_HOST:-127.0.0.1}:${AI_SERVER_PORT:-8081}"
# Pick up AI_SERVER_API_KEY from the repo .env when the caller has not
# exported it, so `./scripts/ai/verify_model.sh` works standalone (the
# completions endpoint rejects unauthenticated requests).
if [[ -z "${AI_SERVER_API_KEY:-}" && -f "${REPO_ROOT}/.env" ]]; then
  AI_SERVER_API_KEY="$(grep -E '^AI_SERVER_API_KEY=' "${REPO_ROOT}/.env" | head -n1 | cut -d= -f2- || true)"
  export AI_SERVER_API_KEY
fi
API_KEY="${AI_SERVER_API_KEY:-}"
AUTH_ARGS=()
if [[ -n "${API_KEY}" ]]; then AUTH_ARGS=(-H "Authorization: Bearer ${API_KEY}"); fi

echo "== 1. GGUF magic =="
if [[ ! -f "${MODEL}" ]]; then
  echo "FAIL: model missing at ${MODEL}" >&2
  exit 1
fi
MAGIC="$(head -c 4 "${MODEL}")"
if [[ "${MAGIC}" != "GGUF" ]]; then
  echo "FAIL: ${MODEL} is not a GGUF file (magic=${MAGIC})" >&2
  exit 1
fi
echo "OK: GGUF magic valid ($(stat -c%s "${MODEL}") bytes)"

echo "== 2. server health =="
for _ in $(seq 1 30); do
  if curl -sf "${AUTH_ARGS[@]}" "${BASE_URL}/health" >/dev/null 2>&1; then
    echo "OK: ${BASE_URL}/health"
    break
  fi
  sleep 1
done
if ! curl -sf "${AUTH_ARGS[@]}" "${BASE_URL}/health" >/dev/null 2>&1; then
  echo "FAIL: server not healthy at ${BASE_URL}" >&2
  exit 1
fi

echo "== 3. real completion =="
# Qwen3's chat template defaults to reasoning mode, which emits tokens into
# reasoning_content and leaves content empty — disable thinking explicitly so
# the smoke test measures a real answer, exactly like the backend client does.
RESP="$(curl -sf "${AUTH_ARGS[@]}" "${BASE_URL}/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"local","messages":[{"role":"user","content":"Reply with exactly: pong"}],"max_tokens":32,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}')"
echo "${RESP}" | python3 -c '
import json, sys
data = json.load(sys.stdin)
text = data["choices"][0]["message"]["content"]
usage = data.get("usage", {})
if not text.strip():
    print("FAIL: completion content is empty (thinking mode leak?)", file=sys.stderr)
    sys.exit(1)
print(f"OK: completion returned ({len(text)} chars, usage={usage})")
print("answer:", text.strip()[:80])
'

echo "== 4. throughput + streaming =="
python3 - "${BASE_URL}" <<'PY'
import json, os, sys, time, urllib.request

base = sys.argv[1]
payload = {
    "model": "local",
    "messages": [{"role": "user", "content": "Write a 150-word paragraph about digital forensics."}],
    "max_tokens": 220,
    "temperature": 0.2,
    "stream": True,
    "chat_template_kwargs": {"enable_thinking": False},
}
headers = {"Content-Type": "application/json"}
api_key = os.environ.get("AI_SERVER_API_KEY", "")
if api_key:
    headers["Authorization"] = f"Bearer {api_key}"
req = urllib.request.Request(
    f"{base}/v1/chat/completions",
    data=json.dumps(payload).encode(),
    headers=headers,
)
started = time.monotonic()
first_token_ms = None
tokens = 0
content = []
with urllib.request.urlopen(req, timeout=120) as resp:
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            event = json.loads(data)
        except ValueError:
            continue
        choices = event.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        text = delta.get("content")
        if text:
            if first_token_ms is None:
                first_token_ms = int((time.monotonic() - started) * 1000)
            content.append(text)
        if choices[0].get("finish_reason"):
            usage = event.get("usage") or {}
            tokens = usage.get("completion_tokens") or tokens
elapsed = time.monotonic() - started
if not content:
    print("FAIL: streaming produced no content", file=sys.stderr)
    sys.exit(1)
# Fallback token estimate (~4 chars/token) when the server omits usage deltas.
tok = tokens or max(1, sum(len(p) for p in content) // 4)
print(
    f"OK: streamed {len(''.join(content))} chars, first_token_ms={first_token_ms}, "
    f"~{tok} tokens in {elapsed:.2f}s ({tok / elapsed:.1f} tok/s)"
)
PY

echo "== 5. GPU usage =="
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader || true
else
  echo "nvidia-smi not available; skipping GPU check"
fi

echo "verify_model: all checks passed"
