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
