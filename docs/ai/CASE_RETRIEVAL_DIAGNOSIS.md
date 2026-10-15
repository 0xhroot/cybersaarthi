# AI Case-Retrieval Failure — Diagnostic Report

**Status:** root cause confirmed by execution (not hypothesis).
**Date:** 2026-10-15 · **HEAD:** `00d7b8f` (clean tree at audit)
**Symptom:** general chatbot answers general questions fine, but "summarize case
<id-or-name>" replies the case does not exist, and appears to see only a couple
of empty cases.

---

## 1. Confirmed root cause

The failure is entirely in the **general-mode case-finding → summarize tool
path**. The database, tenant scoping, environment and the LLM are all correct.
Four compounding defects, all in `backend/app/ai/`:

### A. `search_cases` argument-name mismatch → the user's filter is silently dropped
- Declared schema (`tools.py` ToolSpec): parameter is **`query`**.
- The model emits **`case_id`** (verified live: `args={"case_id":"SHOW-2026-001"}`),
  generalizing from every other case tool, which is named `case_id`.
- Handler `tool_search_cases` reads `arguments.get("query", "")` → gets `""`.
- `retrieval.accessible_cases(query=None)` therefore applies **no filter** and
  returns the **10 most-recently-updated** cases (`CASE_SEARCH_LIMIT = 10`) —
  which in this environment are recent `heartbeat …` test cases.
- The model, seeing unrelated cases, correctly concludes "none match
  SHOW-2026-001" and reports the case does not exist.

**This is where the records disappear** — not in the DB. The correct case is
present but never returned because the search keyword never reaches the query.

### B. No resolution by case number or name — UUID only
- `_authorize_case` does `uuid.UUID(str(raw))`. A case number
  (`SHOW-2026-001`) or a title raises `ValueError` → "case_id is not a valid
  identifier". There is **no resolver** from public case number / title to the
  internal UUID anywhere in `app/ai/`.

### C. `get_case_summary` is disabled in general mode
- `service.py` `_run` pops `get_case_summary` (and `list_evidence`,
  `get_timeline`, `get_analytics_summary`, `rank_entities`) when `case is None`.
- So in general mode the model **cannot** call `get_case_summary` at all
  (verified live: `err=unknown tool: get_case_summary`). Even after a
  successful search, there is no summarize tool to call.

### D. Tool results do not distinguish not-found vs empty vs error
- `ToolExecutionResult` has only `ok`/`error`/`payload`. There is no structured
  status, so an empty search result, a permission denial and a genuine
  "no such case" are indistinguishable to the model — and the model turns all
  three into "the case does not exist."

---

## 2. Environment: UI vs AI — **identical** (ruled out)

| Axis | Normal case API | AI tools | Same? |
|---|---|---|---|
| Backend | `cybersaarthi-backend` FastAPI | same process, `app.ai.service` | ✅ |
| Database | `postgres:5432/cybersaarthi` | `postgres:5432/cybersaarthi` | ✅ |
| Principal | JWT → `User` | same JWT → `ctx.user` | ✅ |
| Scoping | `_case_filters`: admin all; else owner OR member | `accessible_cases`: identical predicate | ✅ |

Verified by direct call against the live DB as `admin`:
`accessible_cases(query=None)` → **10** (admin bypass works, capped at 10);
`accessible_cases(query="SHOW-2026-001")` → **1** correct case. Admin role
detection returns `['ADMIN']` → `is_admin_role → True`. **No DB/tenant bug.**

## 3. Case counts visible to the authenticated user (`admin`)

- Normal `GET /api/v1/cases`: **117** cases.
- AI `search_cases` with a working keyword: returns the matching case.
- AI `search_cases` as the model actually called it (`case_id` arg): **10
  unrelated recent cases** (the "couple of empty cases" the user saw are recent
  `heartbeat` test cases in that default window).

## 4. Are the two AI-visible cases genuinely empty? — **No, they are unrelated**

The default unfiltered window surfaces recently-updated test/heartbeat cases.
The case the user actually asked about (`SHOW-2026-001`) is **fully populated**:
**5 evidence files, 247 entities, 6 timeline events.** Its associations are
intact. Proof: binding it by UUID (`mode=case`) returns a correct, grounded
summary with **37 sources**. Nothing is broken in storage — the lookup path is.

## 5. The exact failing request

`POST /api/v1/ai/chat {"question":"Summarize case SHOW-2026-001"}` (general
mode). Tool trace:
1. model → `search_cases {"case_id":"SHOW-2026-001"}` → handler reads `query=""`
   → returns 10 unrelated cases → model: "does not appear."
2. model → `get_case_summary {"case_number":"SHOW-2026-001"}` → **unknown tool**
   (disabled in general mode).

Conclusion: "the case does not exist" is produced by a **broken tool contract**,
not by a missing record. Fix belongs in the tool layer (Phases 3–4).

---

## 6. Phase 3 — The fix (smallest correct change in the existing architecture)

All changes are in `backend/app/` and preserve the existing models, services and
authorization. Nothing was rewritten; no new service was added.

### A. `search_cases` accepts the reference the model actually sends
`tool_search_cases` now reads the query from any of
`query | case_id | case_number | case_name | q | name | title` via a shared
`_first_str` helper (`app/ai/tools.py`). The tool schema advertises `case_id`
too. A filter can no longer be silently dropped. `accessible_cases`
(`app/ai/retrieval.py`) also matches a UUID query against `Case.id`.

### B. Authorization-first resolver by UUID / case number / name
New `resolve_case_reference()` + `CaseResolution` (`app/ai/retrieval.py`).
Resolution order: exact UUID → exact (case-insensitive) case number → exact
(case-insensitive) title. Visibility is applied *before* any case is returned,
using a new `_visibility_condition()` that is the **single source of truth**
shared with `accessible_cases` (owner/member/admin — identical to the normal
case API). Statuses: `found` / `ambiguous` / `not_found` / `error`. `not_found`
merges "no such case" with "not visible to this user" (anti-enumeration).
`_lookup_case()` (`tools.py`) wraps it, re-runs `assert_case_access` as defense
in depth, and accepts `case_id | case_number | case_name | case | name`.

### C. Case tools available in general mode
`app/ai/service.py` no longer pops `get_case_summary`, `list_evidence`,
`get_timeline`, `get_analytics_summary`, `rank_entities` when there is no
route-bound case — each now resolves and authorizes its own reference, so the
general chatbot can find a case by name/number and then summarize/drill in.

### D. Structured statuses (`app/ai/schemas.py`)
`ToolExecutionResult.status` carries `case_not_found_or_not_accessible` /
`case_found_but_empty` / `case_found_with_data` / `case_ambiguous` /
`lookup_error`. `get_case_summary` distinguishes **empty** (case exists, zero
records) from **missing** via record counts returned by `case_summary()`. A
database failure surfaces as `lookup_error` (never "does not exist"); the model
is told the status so it cannot invent a summary. `search_cases` sets
`match_count` and a not-found status + note when nothing matches.

### E. Honest prompt + surfaced status
`app/ai/prompts.py` (general mode) instructs the model to resolve via tools and
interpret each status literally. `app/ai/service.py` + `app/api/routes/ai.py` +
`app/schemas/ai.py` surface `status` to the client and in the model-facing
`TOOL_RESULT`.

## 7. Phase 4 — Regression tests
`backend/tests/api/test_ai_case_resolution.py` (14 tests, isolated synthetic
fixtures) proves: resolve by UUID / case number / name; ambiguous name returns
authorized candidates (not a guess); case with evidence returns evidence
sources; empty case ≠ missing case; a stranger's case is never disclosed by
UUID/number/name (no payload, no sources, no id leak); search honors the
`case_id` alias; tool search agrees with the normal case API for the same
principal; a DB failure yields `lookup_error` (both injected and via the
resolver's own guard); end-to-end general-mode chat summarizes by number with
only authorized citations and reports a bogus number honestly. The `ai_service`
fixture moved to `tests/api/conftest.py` (shared).

## 8. Phase 5 — Validation (measured)
- Backend hermetic: **576 passed** (562 existing + 14 new), 8 deselected.
- Integration: **8 passed**. Frontend: see final run.
- `ruff` + `mypy` clean (141 files).
- **Eval harness: 33/33, exit 0** — fact recall **1.0**, groundedness **1.0**,
  abstention **4/4**, gates all pass.
- **Live repro (after `docker compose restart backend` — uvicorn has no
  `--reload`):**
  - "Summarize case SHOW-2026-001" (was "does not exist") → now summarizes the
    real case; `search_cases`→`case_found_with_data`, `get_case_summary`
    (UUID)→`case_found_with_data`, source `SHOW-2026-001`.
  - "Summarize case SHOW-2026-003" as investigator → real summary (243
    entities, 5 evidence).
  - "Which cases do I have access to?" → lists the 5 showcase cases (was "you
    have no cases").
  - Cross-tenant probe (investigator → `CS-CF503AE6`) →
    `case_not_found_or_not_accessible` and an honest "not accessible to your
    account… does not prove it does not exist." **No leak.**

## 9. Remaining limitations
- Title-based resolution is *exact, case-insensitive*; a partial name falls back
  to `search_cases` substring matching (by design — ambiguity is surfaced, never
  guessed).
- The 104 `CS-*` NULL-owner cases are empty shells (owner_id NULL → invisible to
  non-admins, never populated). That is a **data-provisioning** concern outside
  the AI tool path and is flagged here for the ingestion owner.

