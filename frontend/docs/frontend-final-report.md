# CyberSaarthi — Frontend Final Report

Premium dark investigation workspace consuming the Harmony backend contract.

## What was built

A complete React 19 + TypeScript investigation frontend implement to
`backend/docs/frontend-contract.md`, with a mock-first adapter architecture
that runs the whole product deterministically without a backend, and swaps to
the real HTTP adapter by flipping one env var.

### Adapter layer (`src/api`)

- `contract.ts` — one `Api` interface describing every service the backend
  exposes (auth, cases, entities, evidence, graph, analytics, findings,
  audit, timeline). UI components and hooks only ever see this type.
- `mock/` — deterministic seed data (stable ids via `uid(seed)`, timestamps
  anchored to a fixed `now`), latency simulation, RBAC + owner-access
  enforcement and audit events mirroring the backend's rules.
- `real/` — HTTP client (`http.ts` bearer auth, request-id/correlation,
  `{error:{code,message}}` envelope decoding into `ApiError`) wired to the
  FastAPI routes.
- `src/api/index.ts` — the exported facade (`api`) plus `isMockMode`;
  selection via `VITE_USE_MOCK_API` / `VITE_API_URL` in `src/config/env.ts`.

### Application layer (`src/app`)

- Lazy-routed single-page app guarded by a boot screen + `RequireAuth` that
  redirects unauthenticated visitors to `/login` (preserving the destination).
- App shell with collapsible sidebar (permission-aware links), topbar search,
  Demo/Live adapter badge, logout, and the Ctrl/⌘K command palette.
- Pages:
  - **Login** — split-screen brand panel, demo-account quick fill.
  - **Dashboard** — case stats, featured/active/recent case lists, quick
    actions, honest "mock vs live" note.
  - **Cases** — searching, status filter, URL-driven pagination, create dialog.
  - **Case layout + Overview** — case header, status change + archive
    confirmation, tabs; overview shows analytics summary, severity bars,
    recent findings, top network-DNA, priority queue and recent activity.
  - **Entities + entity detail** — filterable table, aliases/context, network
    profile when analytics have run, ego-graph neighbour list; explicit note
    that unrecorded candidate links belong in Hypotheses, not here.
  - **Evidence** — upload dialog (source + file), checksummed record list,
    per-record drawer with provenance counts and re-ingest action.
  - **Graph** — Cytoscape canvas with entity/relationship type filters, focus
    + fit, inspector panel; layout explicitly framed as cosmetic.
  - **Analytics** — summary tiles, staged "run analysis" workflow, network
    DNA, communities, centrality (metric tabs), priorities, relationship
    strength, patterns, run history.
  - **Hypotheses** — candidate links framed as unverified prompts, never
    facts, with visible signal/path evidence and a standing caveat.
  - **Findings + finding detail** — filterable review queue, stats strip,
    and a detail page showing approach, signals, paths, evidence,
    limitations, plus Review/Confirm/Dismiss actions gated on
    `findings.review/confirm/dismiss` and closed-status immutability.
  - **Timeline** — case audit trail in chronological feed.
  - **Audit** — immutable action log, resource filter, role-scoped
    (`audit.read`).
  - **Settings** — profile, roles, permission grants vs. ALL_PERMISSIONS,
    data-source card.
  - **Not found** — styled 404.

### Design system

- Single token source `src/styles/globals.css`: dark palette
  (`--color-*`), brass accent, Inter Variable, z-layers, and motion/animation
  tokens that respect `prefers-reduced-motion`.
- Radix-based primitives (`src/components/ui`), centralized status/badge
  maps (`src/components/status.tsx`), error/empty states, toast system,
  command palette.
- Data/reality discipline: hypotheses and candidate relationships are always
  labelled as unverified; graph positions carry no evidential meaning; mock
  mode is labelled Demo everywhere.

## Test coverage

27 Vitest + Testing Library tests across 8 files:

- `permissions` — role matrix mirrors backend; grants reflect the
  authenticated user.
- `auth` — boot/anonymous, demo login, bad credentials, logout.
- `mock-adapter` — facade shape, case filters, finding status transitions +
  immutable-closed rule, evidence upload, RBAC enforcement (403s).
- `queries` — `useUpdateFindingStatus` transitions NEW→CONFIRMED with
  reviewer/comment, denies missing permission (403), rejects re-opening a
  CONFIRMED finding without ADMIN (422).
- `router` — unauthenticated redirect to login, boot to login, authenticated
  dashboard renders, audit blocked for viewers.
- `command-palette` — case search surfaces results through the active adapter.
- `ui` — empty/error states (incl. 401/403 mapping), badges.
- `api` — adapter facade stability and default mock selection.

## Quality gates

- `npx tsc -p tsconfig.app.json --noEmit` → clean (strict, no `any`).
- `npm run lint` → 0 problems (ESLint 9 + typescript-eslint).
- `npm run test` → 34 passed (unit + guards, jsdom, Testing Library).
- `npm run build` → production build succeeds (code-split pages; graph chunk
  carries the Cytoscape bundle).

---

## FRONTEND STATUS

- **STATUS**: COMPLETE
- **BUILD**: `npm run build` passes (tsc -b + vite build; 16+ lazy route chunks,
  35 JS assets total; Cytoscape isolated to the graph chunk).
- **TESTS**: 34 passed across 10 files (`npm run test`)
- **LINT**: 0 problems (`npm run lint`)
- **TYPECHECK**: clean (`npx tsc -p tsconfig.app.json --noEmit`)
- **MOCK MODE**: default (`VITE_USE_MOCK_API=true`) — deterministic seed data, demo creds on login
- **REAL API ADAPTER**: implemented (`src/api/real` via `VITE_API_URL`, `VITE_USE_MOCK_API=false`); same contract/facade
- **ROUTES**: /login, /app (dashboard, cases, cases/:id + overview/entities + entity-detail/evidence/graph/analytics/hypotheses/findings + finding-detail/timeline), /app/audit, /app/settings, /* → 404; all guarded by RequireAuth
- **BACKEND MODIFIED**: no — backend untouched (Phase 4 commit `f9de243` intact)
- **COMMIT**: `feat: build premium CyberSaarthi investigation frontend` (no push)
- **GIT STATUS**: only frontend additions/modifications staged in that commit