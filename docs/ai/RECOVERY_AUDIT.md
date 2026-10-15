# AI Subsystem — Recovery Audit

**Date:** 2026-10-15
**Scope:** Recover the lost OpenCode session that was building CyberSaarthi's AI
subsystem, establish the true repository state it left behind, and account for
every claim in this audit with verifiable evidence.

## 1. What was lost and what was recovered

The previous work session (a ~5-week-old OpenCode session, last active
**2026-10-15 00:17 IST**) was interrupted mid-flight by an OpenCode tool-schema
migration (`bash` → `shell`, `filePath` → `path`). Its work was **not committed**;
everything lived only in the working tree. The session was recovered through the
documented CLI:

```bash
opencode session export ses_f790911bfffeZH827oZZNErgJl > /tmp/opencode/ai_session.json
```

| Fact | Value | Evidence |
|---|---|---|
| Session ID | `ses_f790911bfffeZH827oZZNErgJl` | exported `info.id` |
| Title | "CyberSaarthi audit, persistence fix, and completion" | exported `info.title` |
| Created | 2026-09-09 21:48 IST | `info.time.created` |
| Last activity | **2026-10-15 00:17:09 IST** | `info.time.updated` |
| Messages | 4 823 | exported `messages` length |
| Export size | 45 742 571 bytes | `ls -l /tmp/opencode/ai_session.json` |
| Final message | system notice: "The `bash` tool is now `shell`…" | last element of `messages` |

The transcript was also rendered to a readable tail
(`/tmp/opencode/old_session_tail.txt`, 219 lines) covering the last ~2 hours of
work, which pinned the exact stopping point.

### Exact stopping point

The lost session ended immediately after:

> "Ruff and mypy are both clean. Now I need to: 1. Re-run the backend test suite
> to make sure my lint fixes didn't break anything … 2. Run frontend checks
> (tsc, lint, vitest, build) 3. Then docs, secret audit, commit, final report"

…while two verification commands (a full pytest run and `tsc`/`lint`) were in
flight. Both were aborted by the tool migration, **not** by a failing result.
No test failure, no partial edit and no unsaved file was ever implicated in the
interruption.

## 2. True repository state at recovery time

`git status --short` (re-run at recovery) showed the entire AI subsystem as
**uncommitted work**:

- **17 modified tracked files** (`git diff --stat`: 2 212 insertions, 7 deletions)
  — backend wiring (`main.py`, `config.py`, `router.py`, `codes.py`,
  `docker-compose.yml`, `pyproject.toml`, `uv.lock`, `.gitignore`) and frontend
  wiring (`contract.ts`, `real/index.ts`, `mock/index.ts`, `app-shell.tsx`,
  `package.json`).
- **Untracked new code** — `backend/app/ai/` (9 modules), `backend/app/api/routes/ai.py`,
  `backend/app/schemas/ai.py`, `backend/app/models/ai_conversation.py`,
  `backend/app/models/ai_message.py`, one Alembic revision
  (`36e5ad8fd75e_add_ai_conversations_and_messages.py`), `backend/tests/unit/ai/`,
  `backend/tests/api/test_ai_api.py`, `frontend/src/components/ai/`, `scripts/ai/`,
  `backend/scripts/seed_showcase_cases.py`.
- **Nothing was staged** and **nothing was lost**: every file the lost session
  had touched was present and byte-complete on disk.

### Weight/secret hygiene (verified, not assumed)

| Check | Result |
|---|---|
| `git check-ignore Qwen3-8B-Q4_K_M.gguf` | ignored via `.gitignore:26` (`*.gguf`) |
| `git check-ignore .env` | ignored via `.gitignore:2` |
| `git check-ignore ai_runtime/` | ignored via `.gitignore:27` |
| Real `AI_SERVER_API_KEY` (64 hex chars) present in `.env`? | yes — and `.env` is ignored, so never tracked |
| Secret scan of tracked files | only dev placeholders in `.env.example` (`cybersaarthi`, `dev-secret-change-me`) — no real secrets |

No model weights, runtime binaries, sockets or secrets are tracked or staged.

## 3. What the recovered session had already achieved (and this session re-verified)

Everything below was **re-verified from scratch in this session**; nothing is
carried over on trust.

| Claim from the lost session | Re-verified here |
|---|---|
| llama.cpp runtime downloaded, CUDA build, model loads | `scripts/ai/verify_model.sh` passes end-to-end (§4) |
| Backend AI routes wired, auth enforced | 18/18 live E2E checks (§4) |
| 80 AI tests green before lint fixes | 93 AI tests green after this session's additions (§5) |
| Streaming emits `token → sources → done` | live SSE capture (§4) |
| Isolation: outsider 403 on case chat, 404 on foreign conversations | live E2E + API tests (§4, §5) |
| Ruff + mypy clean after the last lint pass | re-run: `All checks passed!` / `no issues found in 140 source files` |

## 4. Live end-to-end evidence (this session, running stack)

Environment: `docker compose` backend (healthy), host-process `llama-server`
(model loaded, ~6 GB VRAM on the RTX 3080), `socat` UDS bridge.

### `scripts/ai/verify_model.sh` (real inference, real GPU)

```
== 1. GGUF magic ==        OK: GGUF magic valid (5027783488 bytes)
== 2. server health ==     OK: http://127.0.0.1:8081/health
== 3. real completion ==   OK: completion returned (4 chars, …) answer: pong
== 4. throughput + streaming ==
                           OK: streamed 1107 chars, first_token_ms=23,
                               ~276 tokens in 1.54s (178.8 tok/s)
== 5. GPU usage ==         NVIDIA GeForce RTX 3080, 6428 MiB, 12288 MiB, 96 %
verify_model: all checks passed
```

GPU offload is confirmed independently of the throughput number:
`nvidia-smi --query-compute-apps` lists **llama-server (pid 43961) at 5986 MiB**.

One real defect was found and fixed during this audit: `verify_model.sh` required
the caller to `source .env` first (otherwise step 3 got a 401 from the
API-key-protected server). The script now loads `AI_SERVER_API_KEY` from the repo
`.env` itself and passes standalone.

### Live API walkthrough (18/18 checks, `e2e_stage8.py`)

```
PASS  status authenticated: http=200 ready=True
PASS  status unauthenticated rejected: http=401
PASS  general chat: http=200 346ms answer_len=156
PASS  general chat created conversation_id=413cf1c2-…
PASS  case chat grounded: http=200 1161ms sources=39 case_scoped_sources=24
PASS  case chat opened its own conversation: 968683b5-…
PASS  follow-up reuses conversation: http=200 conv=968683b5-…
PASS  history: http=200 messages=4 roles=['user','assistant','user','assistant']
PASS  rename own conversation: http=200 title=Stage-8 renamed thread
PASS  streaming: tokens=26 first_token_ms=364 total=558ms
                 event_types=['done','sources','token'] done_answer_len=48
PASS  server healthy after client cancel (read 64 bytes then closed): http=200 ready=True
PASS  request after cancellation works: http=200
PASS  outsider case chat denied: http=403
PASS  outsider foreign conversation read denied: http=404
PASS  outsider foreign conversation rename denied: http=404
PASS  outsider foreign conversation delete denied: http=404
PASS  outsider general chat still allowed (no case scope): http=200
PASS  malformed token rejected: http=401

TOTAL=18 PASSED=18 FAILED=0
```

Mid-stream client cancellation was exercised by opening an SSE stream, reading
64 bytes and closing the socket; the server stayed healthy and the next request
succeeded. (Two script-side parsing bugs — the history key and SSE framing — were
fixed in the *script*, not papered over in the product; the product behaviour was
confirmed correct by direct `curl` before any code was touched.)

### Tool loop and the stream contract, live

A general-mode question that forces a tool call produced exactly the contract
this session designed:

```
FENCE BEFORE TOOL: '```tool_call\n{"tool": "search_cases", "arguments": {"query": "Ponzi OR investmen…'
TOOL : search_cases {'query': 'Ponzi OR investment fraud'}
DONE : tools= [('search_cases', True)] answer_head='There are no cases in your records related to …'
```

i.e. the model first streams a raw ```` ```tool_call ```` fence, then the `tool`
event arrives, then the real answer. Clients **must** drop the pre-tool text.

## 5. Automated tests (this session)

| Suite | Result |
|---|---|
| Full backend, `-m "not integration"` | **524 passed, 1 deselected** in 107.57 s (baseline before this session's additions: 511) |
| AI unit tests (`tests/unit/ai/`) | 62 collected, all pass |
| AI API tests (`tests/api/test_ai_api.py`) | 31 collected, all pass (12 are the Stage-6 security set) |
| Ruff (whole backend) | `All checks passed!` |
| Mypy (whole backend) | `Success: no issues found in 140 source files` |
| Frontend `tsc -b --noEmit` | exit 0 |
| Frontend `eslint .` | 0 problems |
| Frontend vitest | **110 passed** (18 files) — was 90 before this session |
| Frontend `npm run build` | ✓ built in 3.3 s (pre-existing chunk-size warning only) |

## 6. Defects found and fixed during recovery

Real bugs surfaced while re-verifying the recovered work — each had a test or a
live check before the fix was called done:

1. **`/ai/status` leaked runtime state unauthenticated** → now requires a bearer
   token (401 without).
2. **Model runtime failure returned 500 `INTERNAL_ERROR`** in non-streaming
   `ask()` → now 503 `AI_UNAVAILABLE`.
3. **Streamed turns dropped the conversation id** → `done` now carries
   `conversation_id` (the frontend previously needed a racy
   `listConversations(limit=1)` guess); test:
   `test_stream_without_tools_emits_token_sources_done` asserts the field.
4. **Floating chatbot never cleared the tool fence** → a turn that used a tool
   would have rendered raw ```` ```tool_call ```` JSON before the answer; the
   widget now resets its buffer on the `tool` event (mock adapter reproduces the
   fence so the behaviour is covered by a test).
5. **`verify_model.sh` needed manual `env` sourcing** → loads the key from
   `.env` itself.
6. **`.env.example` documented no AI settings at all** → full `AI_*` block added
   with safe defaults and a "never commit the real `.env`" warning.
7. **Knowledge-mode hallucinated a citation** (found by live probing): asked for
   the inference port, it invented "8080 … inference-server-configuration.md"
   (wrong port, nonexistent file, zero sources) because knowledge mode has no
   DATA block and the model answered from memory instead of calling
   `search_knowledge`. The prompt now mandates the tool lookup when no excerpts
   are present and forbids guessing filenames/ports/paths
   (`test_knowledge_mode_requires_tool_lookup_before_answering`); re-asked after
   the fix, it called the tool and cited 4 real documents.

## 7. Known limitations (audited, not hidden)

- **GPU metrics inside the container are `null`**: the backend container has no
  `nvidia-smi`, so `gpu_stats()` reports name/VRAM as unavailable there. The
  numbers in §4 were captured on the host, where the inference server actually
  runs. Mounting GPU devices into the container was considered and rejected as
  invasive; the container only *talks* to the server, it never needs the GPU.
- **Container→host TCP is blocked by UFW** on this machine, which is why the
  inference server is reached over a Unix domain socket bridge instead of TCP.
  This is a property of the host firewall, not of the code.
- **"Soup" fine-tuning has no repository on this machine**: the name appears only
  in `docs/architecture/complete-project-status-report.md` (as a greenfield
  item). Nothing was fabricated for it; see `docs/ai/EVALUATION.md` §Soup.

## 8. Bottom line

The lost session's work was fully recovered from disk and from its own exported
transcript, re-verified end-to-end against the live stack, hardened with 12 new
security tests plus 20 new frontend tests, and left in a state where every
number in this audit can be re-produced with the commands in
`docs/ai/LOCAL_MODEL_SETUP.md` and `docs/ai/TROUBLESHOOTING.md`.
