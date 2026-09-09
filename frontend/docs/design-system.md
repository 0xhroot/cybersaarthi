# CyberSaarthi Frontend — Design System

Single-source design tokens live in `src/styles/globals.css`. Components consume
tokens for UI chrome; raw hex remains only where Cytoscape graph node colors and
dashboard stat-card tones require literal values (see `cyto-graph.tsx`,
`dashboard.tsx`).

## Colour tokens

| Token                    | Value       | Use                                            |
| ------------------------ | ----------- | ---------------------------------------------- |
| `--color-background`     | `#0a0c10`   | App canvas                                     |
| `--color-surface`        | `#10141a`   | Cards / panels                                 |
| `--color-surface-2`      | `#161b23`   | Nested wells, table rows                       |
| `--color-surface-3`      | `#1d232d`   | Raised chips, hover, active                    |
| `--color-border`         | `#242b36`   | Hairlines                                      |
| `--color-border-strong`  | `#303947`   | Emphasis borders, dividers                     |
| `--color-foreground`     | `#e9ebf1`   | Primary text                                   |
| `--color-muted`          | `#98a0ae`   | Secondary text                                 |
| `--color-dim`            | `#626c7d`   | Tertiary / captions                            |
| `--color-accent`         | `#d6a14e`   | Brand brass — single interactive accent        |
| `--color-accent-strong`  | `#e6b768`   | Accent text on dark                            |
| `--color-accent-soft`    | 14% brass   | Accent fills                                   |
| `--color-success`        | `#4cb782`   | Confirmed / ingested                           |
| `--color-info`           | `#6d9ec2`   | Informational                                  |
| `--color-critical`       | `#e03c43`   | Critical severity / failure                    |
| `--color-high`           | `#e5703a`   | High severity / caution                        |
| `--color-medium`         | `#c9933a`   | Medium severity                                |
| `--color-low`            | `#7e8a99`   | Low severity / passive                         |

Typeography: Inter Variable (self-hosted), numeric data uses `tabular-nums`
(`tabular` utility class).

## Motion

- `--duration-base` 180ms, `--duration-enter` 260ms, `--ease-standard`
  quadratic, `--ease-emphasized` spring-like easing.
- Animation utility classes: `animate-overlay-in/out`, `animate-scale-in/out`,
  `animate-drawer-in/out` (right-hand drawer), `animate-toast-in/out`,
  `animate-fade-in/out`.
- All motion honours `prefers-reduced-motion` (CSS media query disables
  non-essential animation).

## Z-layers

`--z-sidebar` (40) < `--z-topbar` (50) < `--z-drawer` (60) <
`--z-dialog` (80) < `--z-toast` (100) < `--z-palette` (120).

## Components (`src/components/ui`)

`button`, `input` (Input/Textarea/Label), `badge`, `card` (Card/Panel),
`dialog`, `drawer`, `select`, `dropdown-menu`, `tooltip`,
`loading` (Skeleton/Progress/SpinnerBlock), `table`, `toast`,
`empty-state`, `error-state`.

- `src/components/status.tsx` owns every enrichment map + badge: severity,
  finding status/type, case status, entity type/status, profile tier,
  priority, job status, graph sync, relationship type. Pages never hard-code
  badge mapping.
- `src/components/error-boundary.tsx` — boundary fallback panel.
- `src/components/commands/command-palette.tsx` — Ctrl/⌘K palette.
- `src/components/graph/cyto-graph.tsx` — Cytoscape wrapper. Node positions
  are cosmetic and explicitly framed as carrying no evidential meaning.

## Permission model

`src/lib/permissions.ts` centralises `Permission`, `ALL_PERMISSIONS`,
`ROLE_PERMISSIONS`, `hasPermission`, `hasAnyPermission`, `useCan`,
`useCanAny`. Guards, navigation links and buttons all derive visibility from
the authenticated grant set; the backend re-validates every request.

## Conventions

- Strict TS: no `any` (see lint rules); `noUncheckedIndexedAccess` on vars.
- State split: TanStack Query for server state, Zustand for client-only
  state (auth, palette/sidebar, active case).
- Lazy routes; every page is a code-split chunk.
- Toast for ephemeral feedback; dialogs for destructive/confirm; drawer for
  side-by-side inspection.
- `prefers-reduced-motion`, `focus-visible` rings, aria labels on graph,
  semantic `role` on alerts.