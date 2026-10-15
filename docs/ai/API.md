# AI API Reference (`/api/v1/ai/*`)

**Date:** 2026-10-15 · Base path `API_V1_PREFIX = /api/v1`. **Every** route
requires `Authorization: Bearer <JWT>`; without it → **401**. Errors follow the
platform envelope `{"error": {"type", "code", "message"}}`.

Internal tool payloads and raw model transcripts never cross this boundary
unsanitised: the shapes below (`backend/app/schemas/ai.py`) are the only AI
shapes the browser sees.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/ai/status` | Runtime readiness, tools, feature flags (authenticated) |
| POST | `/ai/chat` | One grounded completion (non-streaming) |
| POST | `/ai/chat/stream` | Same turn as SSE |
| GET | `/ai/conversations` | List my threads |
| POST | `/ai/conversations` | Create an empty thread |
| GET | `/ai/conversations/{id}` | Thread messages (history) |
| PATCH | `/ai/conversations/{id}` | Rename a thread I own |
| DELETE | `/ai/conversations/{id}` | Delete a thread I own |
| POST | `/ai/report-draft` | Grounded investigation draft for a case |

Cross-account access is **404** (foreign ids are indistinguishable from missing
ones); access to a case you don't belong to is **403 `CASE_ACCESS_DENIED`**.

## GET `/ai/status`

Authenticated because runtime state is operational information (this was fixed
during the audit — it used to answer anonymously).

```json
{
  "enabled": true, "ready": true, "managed": false,
  "model_configured": "Qwen3-8B-Q4_K_M.gguf", "model_valid": true,
  "context_length": 8192, "max_output_tokens": 512, "gpu_layers": -1,
  "started": true, "load_seconds": 0.02, "restarts": 0,
  "requests_total": 123, "errors_total": 0, "generations_active": 0,
  "last_error": null,
  "last_request_ms": 584, "avg_request_ms": 316,
  "gpu_name": "NVIDIA GeForce RTX 3080",
  "vram_used_mb": 6428, "vram_total_mb": 12288, "gpu_util_percent": 96,
  "prompt_version": "1.0.0",
  "tools": ["get_analytics_summary", "get_case_summary", "get_entity",
            "get_timeline", "list_evidence", "search_cases", "search_knowledge"],
  "feature_flags": {"case": true, "evidence": true, "graph": true,
                    "copilot": true, "report_draft": true, "knowledge": true}
}
```

`ready` is a **live probe** on every call, not a cached startup flag.
`gpu_name`/`vram_*`/`gpu_util_percent` are `null` inside the container (no
`nvidia-smi` there) — they are populated when available, never invented.
(`started`/`load_seconds` describe the *managed* server; in this deployment the
server is a host process, so they stay `false`/`null` by design.)

## POST `/ai/chat`

```jsonc
// request
{
  "question": "Summarize this case.",       // 1..4000 chars
  "mode": "case",                            // general|case|evidence|graph|copilot|report|knowledge
  "case_id": "e3e26b2d-…",                   // required for case modes; ownership enforced
  "conversation_id": "968683b5-…"            // optional: continue an owned thread
}
```

```jsonc
// 200 response
{
  "answer": "The case involves a Ponzi investment racket…",
  "conversation_id": "968683b5-…",
  "message_id": "3c5813bb-…",
  "sources": [{"type": "evidence", "id": "…", "label": "call_detail_record.csv",
               "url": "/cases/…/evidence/…"}],
  "tool_events": [{"tool": "search_cases", "ok": true,
                   "arguments": {"query": "Ponzi"}, "error": null, "duration_ms": 12}],
  "grounded": true,
  "prompt_version": "1.0.0",
  "duration_ms": 1161, "first_token_ms": 91,
  "prompt_tokens": null, "completion_tokens": null
}
```

Omitting `conversation_id` opens a new thread (server-created, title = question
truncated to 80 chars). Passing another user's id → **404**. Passing a
`conversation_id` bound to a different case than the payload → **400**
(`test_conversation_bound_to_another_case_is_rejected`).

### Error codes

| HTTP | `code` | When |
|---|---|---|
| 400 | `AI_MESSAGE_INVALID` | empty/blank question or title |
| 401 | `UNAUTHORIZED` | missing/malformed/expired/revoked token |
| 403 | `CASE_ACCESS_DENIED` | caller isn't a member of `case_id` |
| 404 | `AI_CONVERSATION_NOT_FOUND` | foreign or deleted thread |
| 429 | `AI_RATE_LIMITED` | > `AI_PER_USER_RATE_LIMIT` per minute |
| 503 | `AI_DISABLED` | `AI_ENABLED=false` |
| 503 | `AI_UNAVAILABLE` | inference server down/unreachable/failed (**not** 500 — fixed in the audit) |

## POST `/ai/chat/stream`

Identical request body. Response is `text/event-stream`; each frame is
`data: {json}\n\n`. Event types, in the order they occur:

| `type` | Payload | Notes |
|---|---|---|
| `token` | `{"text": "…"}` | streamed deltas — **every** tool-loop iteration streams live |
| `tool` | `{"tool": "search_cases", "arguments": {…}}` | **Clear your buffer**: preceding tokens were the model's raw ```` ```tool_call ```` fence, not answer text |
| `sources` | `{"sources": [...]}` | same shape as `/chat` |
| `done` | `{"answer", "conversation_id", "grounded", "sources", "tool_events", "prompt_version", "duration_ms", "first_token_ms", "completion_tokens"}` | `conversation_id` was added in this audit so multi-turn clients never guess |
| `error` | `{"code": "AI_UNAVAILABLE", "message": "inference failed; try again"}` | last event on failure |

Live sample (real model, this machine):

```
data: {"type": "token", "text": "1"}
data: {"type": "token", "text": "  \n"}
…
data: {"type": "sources", "sources": []}
data: {"type": "done", "answer": "1  \n2  \n3  \n4  \n5", "grounded": false,
       "conversation_id": "3a757ff8-…", "sources": [], "tool_events": [],
       "prompt_version": "1.0.0", "duration_ms": 145, "first_token_ms": 72,
       "completion_tokens": null}
```

Disconnecting mid-stream is safe: the server keeps running, the partial turn is
simply abandoned, and the next request works normally (verified live).

## Conversations

```
GET    /ai/conversations?case_id=<uuid>&limit=50
       → {"items": [AiConversation], "total": 3}
POST   /ai/conversations           (empty thread for later use)
GET    /ai/conversations/{id}      → {"items": [AiMessage]}   // history, in order
PATCH  /ai/conversations/{id}      {"title": "Renamed"}       → AiConversation
DELETE /ai/conversations/{id}                                   → 204
```

`AiConversation`: `{id, case_id, mode, status, title, prompt_version?,
created_at, updated_at, last_message_at}`.
`AiMessage`: `{id, role ("user"|"assistant"), content, sources?, tool_events?,
grounded, prompt_version?, created_at}`.

Rename trims whitespace and rejects blank titles (400 `AI_MESSAGE_INVALID`).
Foreign id → 404 on read/rename/delete.

## POST `/ai/report-draft`

```jsonc
// request
{"case_id": "e3e26b2d-…"}
// 200
{"draft": "# Investigation draft…", "sources": [...], "grounded": true,
 "prompt_version": "1.0.0", "duration_ms": 2100}
```

Same ownership rule: non-member → 403.

## Client rules of thumb

1. Send the JWT on every call; handle 401 by re-authenticating.
2. In streaming mode, treat `tool` as "reset the visible buffer".
3. Adopt `done.conversation_id` and reuse it for follow-ups.
4. Render `sources` as chips; they are DB-verified citations, not model output.
5. Treat 503 `AI_UNAVAILABLE` as "the local runtime is down" — retry later; the
   rest of the platform still works.
