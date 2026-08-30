# CyberSaarthi — Investigation Frontend

Premium dark investigation workspace for the CyberSaarthi Harmony backend.

## Stack

- **React 19 + Vite 6 + TypeScript (strict)**
- **TanStack Query** (server state) + **Zustand** (client state)
- **React Router 7** (lazy routes, auth guards)
- **Tailwind CSS v4** (design tokens in `src/styles/globals.css`)
- **Radix UI** primitives, **Cytoscape** graph, **Vitest + Testing Library**
- **ESLint 9** + Prettier

## Quick start

```bash
npm install
npm run dev          # http://localhost:5173
```

Demo accounts (mock mode) — shown on the login screen:

| Role           | Username     | Password                    |
| -------------- | ------------ | --------------------------- |
| Administrator  | `admin`      | `admin-dev-password`        |
| Investigator   | `investigator`| `investigator-dev-password` |
| Analyst        | `analyst`    | `analyst-demo-password`     |
| Viewer         | `viewer`     | `viewer-demo-password`      |

## Adapter configuration

```bash
# Mock (default) — deterministic seed data, no network needed
VITE_USE_MOCK_API=true

# Real Harmony backend
VITE_USE_MOCK_API=false
VITE_API_URL=http://localhost:8000
```

The UI talks to a single facade (`src/api/index.ts`). Nothing in the UI layer
imports the mock or real adapter directly; switching adapters changes nothing
in components or hooks. Copy `.env.example` to `.env.local` to override.

## Scripts

| Script               | Purpose                                |
| -------------------- | -------------------------------------- |
| `npm run dev`        | Vite dev server                        |
| `npm run build`      | `tsc -b && vite build` (type-checked)  |
| `npm run preview`    | Preview the production build           |
| `npm run test`       | Vitest + Testing Library (unit/guard)  |
| `npm run lint`       | ESLint                                 |
| `npm run typecheck`  | TypeScript project build (noEmit)      |
| `npm run format`     | Prettier write                         |

## Structure

```
src/
  api/            adapter facade (contract.ts, mock/, real/, client/)
  app/            router, providers, layouts, pages
  components/     ui primitives, status badges, command palette, graph
  config/         env configuration
  hooks/          query hooks (queries.ts) + ui helpers
  lib/            permissions, utils
  stores/         auth, ui (palette/sidebar), case navigation
  styles/         single design-token source
  test/           vitest setup
  types/          backend contract domain types
```

## Security notes

- Every screen respects the permission model (see `src/lib/permissions.ts`),
  and the backend re-validates authorization on every request.
- No API keys or secrets are shipped; tokens live in memory and
  `localStorage` (`authSession`), never in UI code, logs, or queries.
- Hypotheses are labelled as unverified candidate links — nothing is
  presented as fact before review.

Further reading: `docs/design-system.md`, `docs/frontend-final-report.md`,
`../backend/docs/frontend-contract.md`.