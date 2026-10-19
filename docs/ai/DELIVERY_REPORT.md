# CyberSaarthi AI Expansion — Final Delivery Report

**Date:** 2026-10-19 · **Scope:** Phases 5A, 5B, 6, 7 (multilingual complaint
intelligence, digital forensics triage, AI report auditor, and full
integration/security/evaluation/delivery) on top of the already-delivered
Phases 1–4 (grounded assistant, evidence intelligence, case intelligence,
financial/cross-case).

Every number below is measured from a reproducible command run on this day;
raw combined report kept at `/tmp/opencode/eval_final_delivery_final.json`
(gitignored). Nothing is marked done on assertion alone.

---

## 1. Commits and HEAD

| | Commit | Message |
|---|---|---|
| Initial HEAD (Phases 5–7 window) | `6a128cf` | `docs(ai): add phase 5-7 expansion plan` |
| Phase 5A | `2188527` | `feat(ai): add multilingual complaint intelligence` |
| Phase 5B | `4447609` | `feat(ai): add digital forensics triage` |
| Phase 6 | `bfa3171` | `feat(ai): add AI report auditing` |
| Phase 7 · runtime fixes | `edae3ae` | `fix(ai): stop analysis answers truncating mid-report` |
| Phase 7 · harness + tests | `c808f00` | `test(ai): complete final AI integration and evaluation` |
| Phase 7 · docs | `aa397f3` | `docs(ai): finalize AI expansion status and delivery` |
| **Final HEAD** | `aa397f3` | (working tree clean) |

Pre-window context (unchanged this session): Phase 3 = case intelligence,
Phase 4 = `8d90d6c` `feat(ai): add financial flow and cross-case intelligence`.
No destructive git operations were used; unrelated changes were preserved.

## 2. Files and migrations changed (6a128cf → HEAD)

**51 files, +17 099 / −441.**

| Area | Files | Notes |
|---|---|---|
| `backend/app` | 15 | services, routes, schemas, prompts, config, models |
| `backend/tests` | 11 | API/security/unit tests (3 new report-audit security tests) |
| `backend/scripts` | 2 | `eval_phase567.py` (modified), `eval_final.py` (new) |
| `frontend` | 15 | panels, adapters, hooks, types, tests |
| `scripts/ai` | 3 | `eval_final.sh` (new), `run_server.sh` (ctx fix) |
| `docs/ai` | 5 | FEATURE_STATUS, PHASE_5_6_7_PLAN, EVALUATION, IMPLEMENTATION_PROGRESS, AI_EXPANSION_AUDIT |

**Migrations: 0** — alembic head stays `c5e2b8f4d9a3` (enforced by the
`migration_head_unchanged` gate). No model re-downloads, no new weights, no
`.env`/secrets added.

## 3. Feature status matrix (10 features)

| # | Feature | Status | Frontend | Review behavior | Evidence |
|---|---|---|---|---|---|
| 1 | Grounded AI assistant (chat/stream/draft/tools) | ✅ | floating assistant + history | answers stay chat, never evidence | phase-1 live 5/5 gates |
| 2 | Evidence intelligence (ingestion copilot + chain-of-custody) | ✅ | `extraction-panel.tsx` | artifacts `pending_review` | phase-2 live 3/3 gates |
| 3 | Entity resolution | ✅ | `resolution-panel.tsx` | never auto-merged | golden n=8 |
| 4 | Timeline reconstruction | ✅ | `reconstruction-panel.tsx` | human commit required | golden n=13 |
| 5 | Contradiction detection | ✅ | `contradiction-panel.tsx` | human-resolved | golden n=19 |
| 6 | Financial flow analysis | ✅ | `financial-flow-panel.tsx` | `pending_review` | golden n=23 |
| 7 | Cross-case linkage | ✅ | `cross-case-panel.tsx` | approval ≠ merge | golden n=3 |
| 8 | Multilingual complaint intelligence | ✅ | `multilingual-panel.tsx` | `pending_review` | golden n=7 + live |
| 9 | Digital forensics triage | ✅ | `triage-panel.tsx` | structural only, flagged | golden n=9 + live |
| 10 | AI report auditing | ✅ | `report-audit-panel.tsx` | always `pending_review` + `flagged` | golden n=19 + live |

**10/10 features measured** by the combined gate (golden `n=` or live run each).

## 4. Exact gate results

**Backend** (`backend/`):
- `ruff check .` → **All checks passed!**
- `ruff format --check .` → **290 files already formatted**
- `mypy app/ scripts/eval_evidence.py scripts/eval_phase3.py scripts/eval_phase4.py scripts/eval_phase567.py scripts/eval_final.py` → **Success: no issues found in 177 source files**
- `pytest -q` → **1048 passed** (1040 hermetic + 8 integration), exit 0, ~179 s

**Frontend** (`frontend/`):
- `npm test` → **216/216** (see §9 stochastic note)
- `npm run lint` → exit 0 · `npm run typecheck` → exit 0 · `npm run build` → exit 0 (only the pre-existing >500 kB chunk warning)

**Combined evaluation** (`./scripts/ai/eval_final.sh --report …` → exit 0):

| Gate group | Result |
|---|---|
| Total gates | **147, 0 failed**, 213.4 s |
| phase1_model | 5/5 |
| phase2_evidence | 3/3 |
| phase3_case_intel | 16/16 |
| phase4_flow | 47/47 |
| phase567_expansion | 64/64 |
| cross-cutting (coverage / inventory / migration / error-shape) | 12/12 |
| Feature coverage | 10/10 measured |
| Test inventory | 1048 collected (1040 hermetic + 8), floor 1000 ✅ |
| Migration head | `c5e2b8f4d9a3`, single, unchanged ✅ |
| Anonymous error-shape probe | 401 `{"error":{"code":"UNAUTHORIZED","message":"authentication required"}}` ✅ |

Golden-only mode (`--skip-live`) separately green at **75 gates, exit 0**.

## 5. Per-feature metrics (with sample sizes)

**Phase 1 — assistant (live):** 41 golden entries · fact recall **51/54** ·
groundedness **1.0** · sources **1282/1282** valid · abstention **7/7** ·
analysis **2/2** (0 sections missing) · hypothesis **2/2** (4 drafts, 0
errors) · **0 ungrounded answers · 0 invalid sources** · avg latency 1604 ms.

**Phase 2 — evidence intelligence (live):**
- Ingestion, **n=3 cases**: claim recall **12/13 (92%)**, extraction precision **21/22 (95%)**, field validation **59/60**, unsupported-claim rate **1/22 (5%)**, 0 schema-invalid, **0 locator violations**.
- Integrity, **n=3 states** (intact/overwritten/deleted): **3/3 correct**.
- Custody, **n=2 cases**: gap rule fires on the gap case, clean case **0 findings**.

**Phase 3 — case intelligence (golden):**
- Entity resolution **n=8**: precision **4/4 (100%)**, recall **4/4 (100%)**, false merges **0/4**.
- Timeline **n=13** parse: precision/recall **7/7**, timestamp correctness **7/7**, invented timestamps **0**; **n=5** record cases **5/5**.
- Contradiction **n=19** classify: **19/19 (100%)**; **n=11** pair cases: category precision/recall **7/7**, false positives **0**.

**Phase 4 — flow (golden):**
- Financial flow **n=23 records** (2 victims): 22 facts, warnings recomputed exactly, invalid amounts stay invalid, direction absence preserved, no unkeyed grand total, determinism ok.
- Cross-case **n=3 cases / 4 records**: precision **6/6 (100%)**, recall **6/6 (100%)**, FP **0**, FN **0**, determinism ok.

**Phase 5A — multilingual (golden n=7):** 20 values (15 real / 5 planted
fabrication) · value precision **15/15**, recall **15/15** · false accepts
**0**, false rejects **0** · 4 injection cases (2 expected-withheld, both
detected) · 6 translations (3 material-preserved, 3 lossy) · material-invariant
problems **0** · determinism ok.

**Phase 5B — triage (golden n=9):** 3 benign, 1 refusal, 1 injection, 1
manifest, 3 burst · problems **0** · determinism ok.

**Phase 6 — report audit (golden n=19):** rules 1.0.0 · problems **0** ·
determinism ok.

## 6. Authorization / IDOR results

| Check | Result |
|---|---|
| Anonymous submit/list/detail (report audit) | **401** `UNAUTHORIZED`, nothing queued (new test) |
| Anonymous (multilingual/triage/case routes) | **401** (live-verified) |
| Non-member cross-tenant read | **403** (live-verified) |
| Records IDOR (random UUID) | **404** (live-verified) |
| Read-only (closed) case mutation | **409** `CODE_CASE_READ_ONLY` |
| Mid-run permission revocation | **fails closed**: `CASE_ACCESS_DENIED`, extraction ran but no assessment call, no artifact (new test) |
| Cancel probe | consistent (live-verified) |
| Audit metadata | content-free (19 rows, 0 problems; system enums exempt by construction) |

All Phase-5/6/7 authorization checks in the live section evaluated **true**;
1048-test suite includes the hermetic IDOR/RBAC/tenant-isolation tests.

## 7. Live results (local Qwen3, 8 runs, 32 checks all true, 0 problems)

| Run | Status | Latency | Result |
|---|---|---|---|
| Hindi auto-detect | succeeded | 4.05 s | 7/7 values verified, 1 translation recorded |
| Hindi explicit translation | succeeded | 4.05 s | 7/7 values verified |
| English | succeeded | 3.04 s | 8/8 values verified |
| Unsupported script | refused (expected) | 1.03 s | 0 artifacts |
| Triage — URLs | succeeded | 3.04 s | 3 URLs analyzed → 4 observations, 0 explanation failures |
| Triage — manifest | succeeded | 3.04 s | 3/3 manifest entries re-hashed + verified |
| Triage — unsupported format | refused (expected) | 1.03 s | 0 artifacts |
| Report audit | succeeded | 4.05 s | 273-char draft → 6 claims, findings **6 high / 0 medium / 1 info**, 3 counter-evidence matches, 1 artifact flagged |

Report-audit live honesty note: all 6 model claims were **span-flagged**
(alignment is stochastic against the real model; the eval gates only
deterministic properties by design). The fail-safe behaved correctly:
assessment was skipped, nothing was auto-trusted, and the deterministic layer
still produced the findings above — invalid extraction is rejected, never
believed. The draft is stored as **sha256 only**, never raw.

## 8. Performance / hardware

- **GPU:** NVIDIA RTX 3080 12 GB · llama-server full offload · **9 743 MiB / 12 288 MiB** used (after the 2× context fix).
- **Model:** `Qwen3-8B-Q4_K_M.gguf` (5 027 783 488 B, repo root, never re-fetched, no Ollama, no cloud).
- **Context:** `n_ctx_slot = 16384` (was 8192), `--parallel 2`, thinking disabled, temperature fixed 0.2.
- **Throughput:** ~178.8 tok/s measured; grounded turn ~1.1 s; analysis avg 1604 ms; Phase-5/6/7 live runs 1.0–4.1 s each.
- **Suite timing:** backend 1048 tests ~179 s · frontend 216 tests ~52 s · combined eval 213.4 s.
- All latency figures are **single-run measurements**, not statistical claims.

## 9. Stochastic failures and runtime defects (honest record)

1. **Phase-1 live analysis — two truncation walls (caught by the eval gate, fixed in `edae3ae`).** Two delivery runs failed `p1_analysis_all_pass`; it *looked* stochastic (answers differed), but llama-server slot logs exposed two distinct walls:
   - **Retained-prefix context wall** — failing runs ended at slot `n_tokens = 8191, truncated = 1` with exactly 963 generated tokens; the passing run finished at 8142 (49 tokens of headroom). A reused slot retains ~4.6k tokens of shared prefix, stealing generation room. **Fix:** per-slot ctx doubled `8192 → 16384` in `run_server.sh`.
   - **Output-budget truncation** — after the ctx fix, a verbose UUID-heavy answer hit exactly `max_tokens = 1024` and was cut mid-section-3 (sections 4–5 dropped). **Fix:** `ANALYSIS_MIN_MAX_TOKENS 1024 → 2048` in `service.py` (already raised once, 768 → 1024, for this reason).
   - **The eval gate was never weakened** — it correctly failed every defective run. Post-fix: phase-1 5/5, slot usage ≤ 7 956, zero truncation, full eval 147/147.
2. **Frontend test flake (not reproduced).** One frontend test failed in a single run executed concurrently with the full 1048-test backend suite; **4 subsequent standalone runs were green (216/216)**. The failing test name was lost to output truncation and did not reproduce.
3. **Known limitation:** the AI client does **not** inspect `finish_reason`, so a future context/budget hit would again surface as a short answer rather than an explicit truncation error.
4. **Live report-audit spans** are stochastic (0/6 valid in the live run); the harness deliberately gates only deterministic properties and reports span validity as a metric.

## 10. Pre-stated limits (not bugs — decided before implementation)

- **No OCR:** image-only/scanned PDFs are refused (`OCR_REQUIRED`).
- **No `.eml`/MIME parsing:** email triage uses header fields present in already-supported formats (csv/json/txt).
- **Hindi vs Marathi** (both Devanagari) cannot be separated deterministically; the model's label is used and **any disagreement with script evidence is flagged for review, never hidden**.
- **Translation quality** measured only as material-value preservation (numbers/identifiers/dates/negation) — **no BLEU or human-quality claim**; 3/6 live translations were lossy on non-material text (reported, not hidden).
- **Triage makes no malware/phishing verdicts:** structural observations only; **URLs are never fetched, nothing is executed**.
- **Report auditing covers draft text only.**
- **"Soup" fine-tuning: not attempted** — blocked (no Soup repo on this machine) and awaiting explicit authorization; it was never started.

## 11. Service start / stop

```bash
# Inference server (local llama.cpp, loopback only)
cd /home/xhroot/Documents/ai/CyberSaarthi
setsid nohup ./scripts/ai/run_server.sh < /dev/null & disown   # start
curl -s http://127.0.0.1:8081/health                            # 200 when ready
kill $(pgrep -f 'llama-server --model')                         # stop

# Unix-socket bridge (backend → llama-server), if not already running
./scripts/ai/socket_bridge.sh

# Backend + data services
docker compose up -d          # start postgres/redis/neo4j/minio/backend
docker compose restart backend # reload backend (after a code or server change)
docker compose down            # stop all

# Evaluation
./scripts/ai/eval_final.sh --report /path/report.json              # full (golden + live)
backend/.venv/bin/python -m scripts.eval_final --skip-live --report /path/report.json  # golden only
```

## 12. Manual acceptance test list

1. **Assistant:** open a case → floating assistant → ask a grounded question → answer cites real source ids; ask about a case you can't access → **403 abstention**; stream a response; generate a report draft.
2. **Evidence:** upload a txt evidence file → run extraction → artifact appears `pending_review`; run custody audit → gap case reports `custody.unacknowledged_transfer`, clean case reports 0 findings; tamper a stored file → hash verification reports mismatch.
3. **Entity / timeline / contradiction:** run each job on a showcase case → artifact `pending_review`; commit a timeline proposal manually; resolve a contradiction manually (never auto).
4. **Financial / cross-case:** run flow on a case with amounts → warnings match stored values; run cross-case discovery → candidates listed read-only; approve one → records a **reviewed relationship artifact, cases are not merged**.
5. **Multilingual:** upload a Hindi complaint → language auto-detected, values extracted with `pending_review`; upload a Latin-script-only artifact → **refused** (unsupported script); confirm translation record is stored with the original.
6. **Triage:** run on a manifest file → entries re-hashed against bytes; run on a URL-bearing record → observations only, **no network fetch**; run on an unsupported format → **refused, 0 artifacts**.
7. **Report audit:** submit a draft → job runs → artifact always `pending_review` + `flagged` with standing `model_claims_unreviewed`; submit while case is **closed** → **409 read-only**; submit **anonymously** → **401**; cancel a job → no partial artifact promoted.
8. **RBAC/tenant isolation:** log in as a non-member user → all case AI routes return **403**/404, never another tenant's data; audit log shows `report_audit.*` entries with **content-free metadata** (no draft text).
9. **Restart resilience:** restart llama-server + backend per §11 → `/api/v1/ai/status` reports `ready: true` again; a long multi-turn chat on one case completes without a truncated analysis section.

## 13. No-secrets confirmation (explicit)

- **Diff secret scan clean** across the full working diff and the commit range: no literal `password`/`secret`/`api_key`/`private_key`/`access_token` assignments, no key material (`AKIA…`, `ghp_…`, `sk-…`, `BEGIN … PRIVATE KEY`, `Bearer …`), no `.env`/`.pem`/`.key` files.
- The only credential-looking literals are **pre-existing local dev/eval fixture passwords** (e.g. `investigator-dev-password`), a convention inherited from `eval_phase3/4`; they exist only for users the harness itself creates in the local database and are not real secrets.
- **No evidence, case content, PII, or model output** is committed; report drafts are persisted as **sha256 only**; audit metadata is content-free.
- **No model weights, `.gguf`, or runtime artifacts** are tracked (gitignored); no secrets in logs or the report.
