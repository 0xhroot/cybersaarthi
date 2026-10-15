# CyberSaarthi Local AI Platform — Implementation Audit (Phase Zero)

Date: 2026-10-14 · Repository: `0xhroot/cybersaarthi` @ `3061ea5` (branch `main`)

## 1. Repository shape

| Area | Finding |
|---|---|
| Backend | FastAPI 0.141 + SQLAlchemy 2 async + Alembic (15 migrations, head `cd34ef56ab78`), Python 3.12+ (venv runs 3.14.7), `uv`-managed (`backend/pyproject.toml`). App package `backend/app/{api,core,db,models,repositories,schemas,services,analytics}`. |
| Frontend | React 19 + TS + Vite, typed API facade `src/api/{contract,mock,real}` — every service implements `Api`; mock is test/demo-only. UI kit in `components/ui`, shell in `app/layouts/app-shell.tsx`. 85 vitest tests. |
| Data | PostgreSQL (cases, evidence, entities, relationships, findings, hypotheses, victims, devices, reports, audit_logs, case_members…), Neo4j graph mirror, Redis (cache + login throttle + token revocation), MinIO evidence storage. |
| Tests | Backend 432 passing (`-m "not integration"` 431 + 1 integration-readiness). Layers: `tests/unit`, `tests/api` (ASGITransport + real Postgres), `tests/integration`, `tests/e2e`. |
| Docker | compose: postgres/redis/neo4j/minio/backend. Backend binds host source; uvicorn without `--reload` — restart required after backend edits. |

## 2. Existing interfaces to reuse

- **AuthN**: JWT bearer (`app/core/auth.py`); `get_current_user` dependency validates token, revocation (Redis), and account status (`app/api/dependencies.py`).
- **AuthZ**: `assert_case_access` = owner ∨ case-member ∨ admin (`dependencies.py:163`); `get_case_or_404` composes fetch + access check (401/403/404 semantics, IDOR-safe). `require_permission("case.read")` etc. via `app/core/rbac.py` permission strings.
- **Ownership model**: `cases.owner_id` + `case_members(case_id,user_id,role)`. **No organization/tenant model** (RBAC docstring: "no organizations/tenants — Phase 4 scope"). The strongest correct isolation boundary today is **user + case membership**; AI retrieval must go through the same checks.
- **Services**: `search.py`, `timeline.py`, `analytics` package, `findings_service.py`, `reporting.py` (PDF/JSON/CSV export), `audit.record_audit` (append-only trail).
- **Audit**: `record_audit(session, actor_id=…, action="ai.chat", …)` — reused for every AI mutation/tool call.
- **Frontend**: `api` facade + `useAuthStore` + design tokens; command palette + toast patterns for the assistant UX.

## 3. Gaps and risks identified

1. **No AI tables** — conversations/messages/tool-audit need new models + migration.
2. **No vector store** — none required: case metadata retrieval is deterministic structured SQL; knowledge-base search starts as keyword/FTS over approved local docs. No new infra.
3. **Tenant isolation**: not applicable beyond user/case; AI must not invent a tenant layer. Conversation rows carry `owner_id` (user) and optional `case_id` with FK + indexes; every read/write goes through ownership checks. Cache keys (if used) must include user id.
4. **Prompt injection**: evidence text and case records are untrusted — they enter prompts as fenced data blocks with explicit "data, not instructions" framing; tool arguments are schema-validated; model output never grants permissions.
5. **Secrets**: inference endpoint is localhost-only; llama-server binds `127.0.0.1`; backend adds an optional shared token header for defense in depth. CORS unchanged; browser never talks to the model server.
6. **Model artifact**: `Qwen3-8B-Q4_K_M.gguf` (5,027,783,488 B) at repo root, **GGUF v3**, 399 tensors, 28 KV metadata — not yet gitignored (`*.gguf` rule to add). Must never be committed.
7. **Python 3.14 backend venv**: `llama-cpp-python` wheels/builds are not guaranteed for 3.14 — per brief, use a **separately managed llama.cpp server** (prebuilt CUDA binaries) so backend deps stay untouched. `httpx` promoted from dev to runtime dependency for the async client.
8. **GPU**: RTX 3080 12 GB, driver 610.57 (CUDA user-mode 13.3), `nvcc` 13.3 present. Q4_K_M 8B ≈ 5.0 GB weights → 4k context KV+compute comfortably fits; conservative defaults `ctx=4096`, `gen=512`, all layers offload.

## 4. Runtime decision

- **llama.cpp server (b11617, prebuilt Ubuntu x64 CUDA 12.8 runtime bundle)** — driver 13.3 runs 12.8 runtime (backward compatible); bundle ships its own cudart/cublas so system CUDA version drift cannot break it.
- Managed as a child process (spawned by backend lifespan when `AI_MANAGE_SERVER=true`, or externally via `scripts/ai/run_server.sh`), bound to `127.0.0.1:8081`, OpenAI-compatible `/v1/chat/completions` + `/health`.
- One shared runtime for all features (no per-feature model copies); concurrency via server request queue + backend semaphore.

## 5. Compatibility constraints

- All AI routes live under `/api/v1/ai/*`, follow existing error envelope (`ApiHTTPException` + codes), pagination and auth conventions.
- Frontend adds `ApiAiService` to the contract; mock adapter stays deterministic so the 85 existing vitest tests and parity tests keep passing.
- Migration is additive only (new tables; no changes to existing ones). Alembic head after this work chains from `cd34ef56ab78`.
- Docker: no new exposed ports; model/runtime paths configurable via env; compose file gains no public inference port.

## 6. What this audit does *not* claim

- No org/tenant model exists — isolation is enforced at user+case membership (documented in `docs/ai/SECURITY_AND_ISOLATION.md`).
- OCR/vision/speech: not present in backend today → clean optional extension points only.
- Fine-tuning: GGUF Q4_K_M is an inference artifact, not a training checkpoint — Soup compatibility is audit-only unless a training checkpoint is supplied.
