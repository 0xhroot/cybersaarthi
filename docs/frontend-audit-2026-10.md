# Frontend audit — Extreme UI/UX overhaul (2026-10-20)

Baseline captured with Playwright against the **real API** (`VITE_USE_MOCK_API=false`,
backend docker stack, SIH showcase case `d439fa9c-…`), at 1440×900 and 390×844.
Screenshots: `/tmp/opencode/audit/before/` (34 PNGs). Baseline checks before any edit:

| Check | Result |
| --- | --- |
| `npm run typecheck` | pass |
| `npm run lint` | pass (0 problems) |
| `npm run test` | 139 passed |
| `npm run build` | pass (tsc -b + vite build) |
| Console errors / failed requests (browser) | 0 / 0 |
| Horizontal overflow 1440 | none |
| Horizontal overflow 390 | **analytics: 1040px > 390px** |

No pre-existing failures were inherited by the redesign.

## Root causes of the serious defects

1. **No wrapping rule for machine-shaped text.** `font-mono` UUID/hash lists
   (`supporting records: 1860dccd-63a4-…, …`) have no `overflow-wrap`, so one long
   unbroken token forces its container wider than the viewport. This is what makes
   the mobile analytics page 1040px wide on a 390px screen (probed: the offending
   node is the financial-flow pattern card at 1007px).
2. **Analytics is a single 12,216px (desktop) / 22,838px (mobile) scroll.** Four
   heavyweight panels (AI analysis, contradictions, financial flow, cross-case) are
   stacked inline beneath five KPI cards and six structure cards, with no section
   navigation, no grouping, and no prioritization. Raw payloads are dumped with
   `JSON.stringify` (timeline, triage, report-audit, multilingual, entity/victim
   detail) instead of structured, labeled detail.
3. **Badges/headers can wrap per character.** `Badge` has no `whitespace-nowrap`,
   and `TH` has none either — squeezed columns wrap status labels and split words
   ("CONFIDENC E" in the entities register).
4. **Unbounded lists.** Audit log fetches 200 rows and renders them in one table
   (8,969px page); findings renders up to 100 rows with no pagination. The API
   supports `limit`/`offset` (audit) and filtering (findings) but the UI does not
   use it.
5. **Inconsistent date formatting.** `case-layout`, `victims`, `iot*` call
   `toLocaleDateString()/toLocaleString()` (US "10/20/2026") while every other page
   uses the shared `formatDate` ("20 Oct 2026").
6. **Repeated facts.** The dashboard shows open/in-progress/closed three times
   (Workspace pulse, KPI cards, Case status distribution).

## Prioritized defect list

| # | Sev | Route / component | Defect |
| --- | --- | --- | --- |
| D1 | P0 | analytics (mobile) | 1040px horizontal overflow from unwrapped UUID lines in financial-flow + cross-case panels |
| D2 | P0 | analytics page | 12k/22k-px unstructured scroll; no section nav; repeated cards; raw payload dumps |
| D3 | P0 | timeline | `JSON.stringify(payload)` per event exposes hashes/internal ids; 6,067px page |
| D4 | P0 | audit log | 200-row table, no pagination/total, 8,969px page |
| D5 | P1 | `Badge`, `TH` | missing `whitespace-nowrap` → per-character wrapping under pressure |
| D6 | P1 | findings | 34 rows, no pagination, no grouping; score vs confidence unclear |
| D7 | P1 | entities register | `CONFIDENCE` header splits mid-word; column sizing fragile |
| D8 | P1 | case-layout, victims, iot* | locale-dependent date strings (inconsistent with the rest of the app) |
| D9 | P1 | triage / report-audit / multilingual / detail drawers | raw JSON dumps instead of labeled key-value detail |
| D10 | P2 | dashboard | same case-status facts shown three times on one screen |
| D11 | P2 | hypotheses | 3,801/6,273px page; AI hypothesis cards carry long payload-ish bodies |
| D12 | P2 | shell/CSS | leftover shadcn dark-mode overrides (`.bg-white`…), spacing/page-padding drift between pages |

## What is already good (do not regress)

- App shell: sidebar grouping, active state, skip link, breadcrumbs, command
  palette (Ctrl+K), theme/language controls, responsive drawer nav.
- Case register: semantic table + intentional mobile card list, server-side
  pagination, URL-synced filters, showcase badge.
- Evidence page: KPI row, table, inspect drawer with provenance + per-evidence AI
  panels (extraction/multilingual/triage/integrity) behind disclosure.
- Graph page: filter chips, inspection pane, honest "layout is cosmetic" note.
- Reports, devices, settings, login/register: clean and consistent.
- RBAC is honest: investigator gets a real "No access" page for /app/users.

## Resolution (2026-10-20, after the overhaul)

All twelve defects resolved in four commits on top of baseline `12d3e2b`
(`4684eff`, `bce707f`, `0bf62ed`, `a459320`, `c8752ce`). Every claim below was
verified in the browser (Playwright, real API) plus tsc/eslint/vitest/build.

| # | Resolution |
| --- | --- |
| D1 | Root cause fixed at the source: `EvidenceList`'s implicit `auto` grid track took its minimum from a `nowrap` dd (964px). Now `grid-cols-1` (minmax(0,1fr)) + `wrap-anywhere` values; new shared `MonoId`/`IdList` primitives. All five analytics sections probe clean at 390px. |
| D2 | Analytics split into URL-driven section tabs (AI analysis / Contradictions / Financial flow / Cross-case / Network structure) with roving tabindex; only the active section mounts (removes four request bursts). Shared `TabBar` component extracted for reuse. |
| D3 | Timeline: labeled `key-value` disclosure per event (native `<details>`), day-grouped, server-side paging with honest counts ("Showing the newest 30 of 130 events"). Page 6,460 → verified no JSON dumps, 11 day groups. |
| D4 | Audit log: 50/page pagination with live "Showing 1–50 of 3,245", offset resets on filter, actor ids resolve to usernames via per-id lookups gated on `users.manage` (investigators never fire them — verified 0 `/admin/users` requests). Resource-type filter options replaced dead guesses with the backend's actual 21 values. |
| D5 | `Badge`/`TH` gained `whitespace-nowrap`. |
| D6 | Findings is now a ranked review queue: status tabs with live counts, 50/page URL-synced pagination, honest out-of-range state ("Back to newest"), and the score cell shows the score with a labelled `conf NN%` line — the header explains both 0–100 scales. |
| D7 | Verified fixed by D5's `TH` primitive: all five headers single-line at 1440/1024/768/390 (range-rect probe). |
| D8 | Shared `formatDate`/`formatDateTime` replace every `toLocale*` call. |
| D9 | New shared `ui/key-value.tsx` (`KeyValueList` + `PayloadDetail`); all six `JSON.stringify` dump sites (timeline, triage, report-audit, multilingual, entity context, victim accounts) render labeled rows. Nested objects stringify only as a last-resort value format. |
| D10 | Dashboard status facts appear once: pulse headline + one completion line ("X% · N of M closed") + three KPI cards. "Active workload" card, "Case status" bar card and the hero status gloss removed. |
| D11 | Hypotheses page 3,801 → 2,780px. Per-card trust warnings (×13) folded into the section subtitle; CardHeader merged into a compact row; raw rule codes humanized ("Shared neighbors") with the code kept in the chip title. |
| D12 | `html.dark .bg-white/.text-white/.border-white/.hover:bg-white` overrides removed (three were dead). Solid `-50/-700` palette chips across device pages → the `ui/badge` token recipe; QR plate baked into the SVG so it stays scannable in dark mode. Four pages' `mt-6` first blocks normalized to `mt-4`. |

### Latent bugs found and fixed along the way

- `queryKeys.audit()` returned `["audit", undefined]`; TanStack partial matching
  is strict per element, so it never matched the parameterized query — all ~46
  audit invalidations were silent no-ops. No-arg builders now return the bare
  prefix (`users` had the same shape).
- The pairing-QR dialog ran `generate()` on mount, always lost the race against
  the health query, toasted "Backend health unavailable" and never retried — the
  QR only appeared on a second open with a warm cache. The effect now waits for
  `health.data` (verified: first open renders the QR).

### Deliberately not changed

- Alpha-tint status maps (`bg-blue-500/15 …` in victims / IoT event kinds):
  legible in both themes and encode distinctions (purple vs blue) the token
  palette cannot express. Scrims (`bg-slate-900/35`) are theme-independent.
- `>500 kB` chunk-size build advisory (pre-existing; splitting the bundle is out
  of scope for a UI overhaul).

### Final verification

| Check | Result |
| --- | --- |
| tsc -b / eslint / build | 0 errors / 0 problems / pass |
| vitest | 227/227 (26 files); no test file removed — 2 assertions legitimately relaxed where a value now renders twice (labeled field added beside the existing render) |
| Browser console errors / failed requests | 0 / 0 across all 20 routes |
| Horizontal overflow 390px | none on any route (all 20 probe at exactly 390/390) |
| After screenshots | `/tmp/opencode/audit/after/` (36 PNGs, 1440 + 390) |
