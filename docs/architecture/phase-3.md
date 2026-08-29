# Phase 3: Investigation intelligence engine

- **Status:** Implemented
- **Date:** Phase 3 (SIH 26189)
- **Scope:** deterministic network analytics (centrality, communities, bounded
  multi-hop paths), Network DNA profiles, relationship strength, structural /
  temporal pattern detection, missing-link hypotheses, investigation priority,
  explainable persisted findings, live summary and analytics APIs.
- **Out of scope (later phases):** large-language-model features, generative
  summaries, any form of probabilistic or learned scoring, evidence-based
  conclusion labels beyond the analytical signals defined here.

## Design principles

1. **No fake AI.** Every score is a deterministic function of real, present
   data. `random`, hardcoded confidence and look-up tables pretending to be
   intelligence are banned. All algorithms iterate nodes in sorted-id order so
   results reproduce exactly.
2. **Ever understood.** Each finding carries an explanation with the approach,
   the raw signals behind it, the weights used, and the affected entities,
   relationships and evidence IDs (provenance).
3. **No unsupported accusations.** A finding says *structurally unusual for this
   case*, never *guilty*. The term `suspicious`/`hypothesis` is an analytical
   signal about missing evidence, not a conclusion.
4. **Never fabricated timing.** The rapid-expansion detector only fires on real
   relationship `created_at` spread. A single-batch demo reports nothing rather
   than invent temporal data (documented honest behaviour).
5. **PostgreSQL is the source of truth.** All analytics read from it; Neo4j is
   used only for bounded `allShortestPaths` traversal. A persisted
   `POST /analytics/run` snapshot provides auditability; the read endpoints
   recompute deterministically so they never serve stale numbers.

## Pipeline overview

```
PostgreSQL (entities, relationships, relationship_evidence, evidence_files)
        │
        ▼  AnalyticsDataRepository (single bounded load, node cap 2000)
   in-memory Graph (deterministic, undirected + directed views)
        │
        ├── centrality        betweenness (Brandes), closeness, PageRank, degree
        ├── components        connected components, Tarjan articulation points
        ├── communities       greedy modularity agglomeration (sorted edges)
        ├── Network DNA       8-dimension profile + FOCAL..PERIPHERAL tier
        ├── strength          evidence-derived relationship strength
        ├── patterns          shared identifiers, bridges, concentration, loops,
        │                     location+identifier linkage, rapid expansion, triads
        ├── hypotheses        bounded missing-link candidates (never written back)
        ├── priority          DNA + pattern + hypothesis -> CRITICAL..LOW
        └── findings          explained finding drafts (status NEW)
                │
                ├── summary / communities / centrality / profiles / priorities / strengths
                │     ... live read endpoints (recompute on demand)
                └── POST /analytics/run  ─► findings + metrics persisted (audit trail)
                                            GET /analytics/runs
Neo4j (bounded allShortestPaths, case-scoped)  <── paths / paths/entity endpoints
```

## Scoring formulas

**Relationship strength** (`app/analytics/strength.py`) — all denominators are
the case's own maximums so scores are comparable inside a case:

```
strength = 0.30*coverage + 0.15*type_diversity + 0.20*record_coverage
         + 0.20*file_independence + 0.15*resolution_confidence

coverage          = log1p(evidence rows) / log1p(case max)
type_diversity    = evidence types over type-pair / co-occurrence
record_coverage   = distinct source records / case distinct records
file_independence = distinct evidence files / case distinct files
resolution_confidence = mean entity resolution confidence of both endpoints
```

**Network DNA** (`app/analytics/network_dna.py`) — a profile per entity over
eight dimensions, each normalized by the case maximum:

```
name        weight   raw measure
prominence   0.20    undirected degree
influence    0.15    PageRank authority
bridging     0.20    fraction of shortest paths through the entity
reach        0.10    closeness to the rest of the graph
anchorage    0.10    share of connections pointing into the entity
activity     0.10    directed-edge participation
evidence_depth 0.10  distinct source records behind its links
community_span   0.05  detected-community size

tiers: FOCAL ≥ 0.70 · SIGNIFICANT ≥ 0.45 · MONITORED ≥ 0.25 · PERIPHERAL
overall = Σ weight × normalized(dimension)
```

**Investigation priority** (`app/analytics/priority.py`):

```
priority = 0.25*prominence + 0.15*influence + 0.20*bridging + 0.10*reach
         + 0.15*pattern_weight + 0.15*hypothesis_weight
pattern_weight    = 0.5*(CRITICAL+HIGH) + 0.25*MEDIUM + 0.1*LOW (cap 1.0)
hypothesis_weight = min(1.0, count × 0.4)
tiers: CRITICAL ≥ 0.75 · HIGH ≥ 0.55 · MEDIUM ≥ 0.35 · LOW
```

**Patterns** (`app/analytics/patterns.py`) — each detector normalizes degree /
neighbour counts by the case maximums and produces a `PatternDraft` with
explicit `signals` and `metadata`. Examples: shared identifier (≥ 3 entities on
one phone/account/vehicle/org), bridge (Tarjan cut vertex), relationship
concentration (degree ≥ the 95th percentile tail, floor 5), closed loops
(3-cycles), location+identifier linkage, rapid expansion (real time spread
≥ 3600 s), and connected triads.

**Hypotheses** (`app/analytics/hypotheses.py`) — for non-adjacent actor pairs
that share neighbours (a traceable structural signal), a missing-link candidate
is drafted with the relationship types observed between the endpoints and the
shared neighbours as the suggested `candidate_relation_type`, scored by shared
neighbours and community membership. Hypotheses are **never written back** to
the graph or evidence.

## Determinism and explainability

- All graph algorithms (`app/analytics/graph.py`) iterate nodes/edges in sorted
  id order: components, Tarjan articulation, Brandes betweenness, closeness,
  power-iteration PageRank (30 iterations, damping 0.85), triangles,
  common neighbours.
- Communities use greedy modularity agglomeration over the sorted edge list
  with a stop threshold of `quality_threshold = max(ANALYTICS_COMMUNITY_QUALITY,
  1e-9)`; a positive-gain merge is applied only when it improves modularity.
- Every finding's `explanation` (built by `app/analytics/explanations.py`)
  carries `approach`, `signals`, `affected_entity`/`affected_relationship`
  IDs, `evidence_ids` and a `limitations` message; block-level `details`
  back the summary.

## Bounded Neo4j traversal (paths)

`app/analytics/paths.py` runs `allShortestPaths` for egocentric and pair paths
only:

- **Case-scoped on both endpoints** (`case_id` on every node pattern) so no
  cross-case data can leak into results.
- **Literal relationship-type allowlist** from `RELATIONSHIP_TYPES`
  (`called|owns|works_for|associated_with|located_at|visited|transferred_to`),
  never user-supplied Cypher fragments.
- **Hard bounds**: `max_hops` ≤ 8 (route-enforced), `limit` ≤ 50, single result
  batch per request. Ego paths materialize `other <> start` via `WITH` before
  the search; pair paths use `*1..max` because `allShortestPaths` only allows a
  minimal length of 0 or 1, then exclude direct edges (`hops >= 2`).

## Configuration thresholds (`app/core/config.py`)

| Setting | Default | Purpose |
|---|---|---|
| `ANALYTICS_GRAPH_NODE_CAP` | 2000 | load cap before sampled fallback |
| `ANALYTICS_PATH_MAX_HOPS` | 4 | default traversal depth |
| `ANALYTICS_PATH_RESULT_LIMIT` | 10 | default path result cap |
| `ANALYTICS_COMMUNITY_QUALITY` | 0.0 | modularity stop threshold |
| `ANALYTICS_MAX_HYPOTHESES` | 25 | capped hypothesis draft count |
| `ANALYTICS_PATTERN_SHARED_IDENTIFIER_MIN` | 3 | shared-identifier floor |
| `ANALYTICS_PATTERN_CONCENTRATION_MIN` | 5 | fan-out floor |
| `ANALYTICS_PATTERN_BRIDGE_MIN_COMMUNITIES` | 2 | bridge context floor |
| `ANALYTICS_PATTERN_ANOMALY_TAIL` | 0.95 | degree percentile tail |
| `ANALYTICS_PATTERN_RAPID_SPREAD_SECONDS` | 3600 | minimal timestamp spread |

### Approximate vs exact results (honest reporting)

All algorithms above the graph load cap are exact over the loaded graph. When a
case exceeds `ANALYTICS_GRAPH_NODE_CAP` (default 2000) the loader falls back to a
sampled subgraph, making results approximate. This is **always reported**: the
summary carries `exact_graph: true/false` and a human-readable
`approximation_notice`; the digest reports `entity_counts.exact`; Network DNA and
strength results carry a per-entity `exact` flag. Consumers are required to
surface the notice whenever an approximation is in effect. Predictable
consequence (also documented in README): fewer than 2000 nodes ⇒ `exact_graph`
is always true on the demo data.

## Findings persistence semantics (decision)

**Findings are intentional, append-only run snapshots (audit history).**

Each `POST /analytics/run` computes the full deterministic pipeline and persists
one `AnalyticsRun` with its own snapshot of findings, metrics, communities and
profiles — every row is linked to that run via `run_id`. Repeated runs therefore
accumulate findings rows; this is deliberate so that any past run can be
reconstructed. Consequences for consumers:

- `GET /cases/{id}/findings` and `GET /cases/{id}/findings/stats` return the
  **union across all runs** (newest first). This is intentional — it is the
  reviewable history, not just the last snapshot.
- Every finding payload carries `run_id` and `created_at`, so current and
  historical findings can always be distinguished by the client. To view a
  single run's snapshot, pass `?run_id=<id>` (findings and findings/stats).
- Status review is **per snapshot**: a finding from an older run can be
  `REVIEWED`/`DISMISSED`/`CONFIRMED` independently of newer runs. Analysts
  should default to filtering on the latest `completed` run (see
  `GET /analytics/runs`) for the "current" picture.
- Within a single run the pipeline emits each logical finding at most once
  (detectors deduplicate; the assembled list is capped at 200 findings), so no
  run accumulates duplicate snapshots by itself.
- Growth is linear in (runs × findings-per-run). That is acceptable for case
  work today; operational lifecycle/pruning of old runs is future work, not a
  Phase-3 defect.

## Findings lifecycle

Findings are created with `status=NEW` and an initially computed severity from
the producing detector. `CONFIRMED` is **never auto-assigned** — only an
investigator may set it via `PATCH /findings/{id}/status`. Status transitions
are single-field updates (`NEW / REVIEWED / DISMISSED / CONFIRMED`) and the
audit trail of who/when is preserved through existing case-level controls.

## Hypotheses are candidates, never facts

`app/analytics/hypotheses.py` and `GET /analytics/hypotheses` only ever propose
missing-link candidates for entity pairs with **no direct relationship**:

- A hypothesis reports candidate endpoints, a `candidate_relation_type`
  suggested by the relationship types on the existing shared-neighbour edges,
  the score, confidence, the exact shared signals (shared neighbours,
  community membership, supporting relationships) and the supporting
  relationships' evidence IDs.
- Hypotheses are **never written back** to the graph or the evidence layer —
  generating one creates/metastasizes no edge in PostgreSQL or Neo4j (covered
  by `test_hypotheses_are_candidates_not_facts` and
  `test_generate_hypotheses_never_mutates_graph`).
- Persisted hypothesis findings carry an explanation whose `limitations` state
  that a candidate edge is not evidence and never creates a graph edge.
- The API distinguishes observed edges (the graph) from inferred candidates
  (hypotheses) structurally: hypotheses are only listed under
  `/analytics/hypotheses` and `finding_type == "hypothesis"`, and the summary's
  `relationship_count` never counts them.

## Modules

| Module | Responsibility |
|---|---|
| `app/analytics/graph.py` | deterministic graph structure + exact algorithms |
| `app/analytics/communities.py` | greedy modularity, summary statistics |
| `app/analytics/centrality.py` | metric maps consumed by endpoints |
| `app/analytics/patterns.py` | structural/temporal pattern detectors |
| `app/analytics/hypotheses.py` | bounded missing-link candidates |
| `app/analytics/strength.py` | evidence-derived relationship strength |
| `app/analytics/network_dna.py` | per-entity profiles and tiers |
| `app/analytics/priority.py` | combined priority score and tiers |
| `app/analytics/paths.py` | bounded Neo4j `allShortestPaths` |
| `app/analytics/explanations.py` | explainability payload builder |
| `app/analytics/findings.py` | `AnalyticsService`: context, run, persistence |
| `app/repositories/analytics_repository.py` | bounded loads + run/finding persistence |
| `app/api/routes/analytics.py` | analytics API (summary, reads, run) |
| `app/api/routes/findings.py` | findings API (list, stats, status) |

## API surface

All under `/api/v1`:

| Endpoint | Purpose |
|---|---|
| `GET /cases/{id}/analytics/summary` | live case summary with finding/tier counts |
| `GET /cases/{id}/analytics/centrality?metric=&limit=` | degree / betweenness / closeness / pagerank |
| `GET /cases/{id}/analytics/communities` | communities with members, density, types |
| `GET /cases/{id}/analytics/entities/{eid}/analytics` | per-entity profile + priority + bridges |
| `GET /cases/{id}/analytics/network-dna?limit=` | Network DNA profiles |
| `GET /cases/{id}/analytics/priorities?limit=` | ranked priorities |
| `GET /cases/{id}/analytics/strength?limit=` | ranked relationship strengths |
| `GET /cases/{id}/analytics/paths/entity/{eid}?max_hops=&limit=` | egocentric paths |
| `GET /cases/{id}/analytics/paths?source_id=&target_id=&max_hops=` | pair paths |
| `GET /cases/{id}/analytics/patterns?limit=` | structural finding drafts |
| `GET /cases/{id}/analytics/hypotheses?limit=` | missing-link candidates |
| `POST /cases/{id}/analytics/run` | run + persist analytics run and findings |
| `GET /cases/{id}/analytics/runs` | run history |
| `GET /cases/{id}/findings` | persisted findings (type/status/severity filters) |
| `GET /cases/{id}/findings/stats` | findings statistics |
| `GET /cases/{id}/findings/{fid}` | single finding detail |
| `PATCH /cases/{id}/findings/{fid}/status` | status review |

## Demo results (clean seed, DEMO-2026-001)

Fresh `down -v → build → migrate → seed` with the 5-file demo corpus:

Deterministic analytics over **45 entities / 86 relationships**: **4 communities**,
**55 findings** (25 pattern, 25 hypothesis, 3 network insight, 2 relationship
insight; 29 MEDIUM / 23 LOW / 3 HIGH). Top profiles: `Mumbai` FOCAL 0.978,
`Bengaluru` 0.648, `Noida` 0.456; top priorities: `Mumbai` HIGH 0.704,
`Bengaluru` 0.538. Representative outputs: bridge findings for Bengaluru /
Kavita Rao / Noida / Rajesh Kumar / Sunita Sharma, closed loops, hypotheses
e.g. `Arjun Mehta ↔ Rajesh Kumar <- works_for (1.00)` and
`Priya Nair ↔ Sameer Bhat <- called (0.82)`, and 30 egocentric paths from
`Rajesh Kumar` (7 at depth 1, 23 at depth 2).

## Testing and quality gates

- Unit: `tests/unit/test_analytics_algorithms.py` — graph algorithms,
  communities threshold behaviour, pattern detectors, hypotheses, priority,
  Network DNA, strength formula (exact weights).
- API: `tests/api/test_analytics_api.py` — full lifecycle over ephemeral cases
  (summary, run persistence, findings status, paths, statistics, 404s, and
  cross-case isolation); includes regression coverage for the audit follow-ups:
  run-snapshot semantics via `run_id`, hypotheses-never-mutate, paths
  validation + OpenAPI contract, and exact-graph defaults.
- Cross-process determinism regression:
  `test_hypotheses_reproduce_across_hash_seeds` — runs the hypothesis generator
  in subprocesses under several `PYTHONHASHSEED` values and asserts identical
  candidate lists. This guards the two `sorted()` calls in
  `app/analytics/hypotheses.py` that keep set-iteration order out of the
  bounded candidate list.
- Gates in the backend container are all green: `pytest` (150 passed), `ruff
  check`, `ruff format --check`, `mypy app`, `alembic check` (no drift).

## Deferred items (intentionally out of scope)

Recorded so readers do not mistake them for defects:

- **Authentication / RBAC.** Phase-3 (and Phases 1–2) expose no authentication.
  `User`, `Role`, `UserRole` models, bcrypt helpers and the user
  service/repository scaffolding exist but **no auth endpoints or middleware
  are wired**. Every endpoint is currently unauthenticated. The intended
  injection point is `app/api/dependencies.py` (auth dependency + role gate).
- **Background ingestion.** `POST /ingest` executes the pipeline synchronously
  inside the request. Jobs are persisted and safe to retry, but there is no
  worker/queue (Celery/RQ) yet — that is a later-phase operational concern.
- **Frontend and deployment manifests.** `frontend/`, `infra/`, `ml/`, `data/`
  are empty placeholders by design.

## Phase 3 final verification

Clean-room check: `docker compose down -v` → fresh build → start → migrations →
`make seed` → `POST /analytics/run` on the demo case → full gate run.

- **Migrations:** single head `a4b9c7e16d20`; `alembic current` = `alembic
  heads`; `alembic check` reports no drift ("No new upgrade operations
  detected"); a downgrade to base followed by `upgrade head` was performed on
  the clean-room stack and reproduced the same head with no drift.
- **Tests:** `pytest` 150 passed (unit 121, api 17, integration 12) in the
  backend container.
- **Static gates:** `ruff check` clean, `ruff format --check` clean (116
  files), `mypy app` clean (83 source files).
- **Docker:** all five services healthy after cold start; ready endpoint `200`.
- **Determinism:** the seeded case summary (45 entities / 86 relationships /
  4 communities / 55 findings / priority tiers LOW 29 · MEDIUM 15 · HIGH 1)
  reproduced identically across repeated requests and across backend restarts;
  a cross-process `PYTHONHASHSEED` regression test covers the fixed
  hypothesis-ordering.
- **Demo analytics:** deterministic output for DEMO-2026-001 (45 entities /
  86 relationships / 4 communities / 55 findings / top profiles and paths as
  listed above) reproduced after the down -v cycle and after the migration
  round-trip.
- **Final commit:** `chore: finalize phase 3 audit and consistency cleanup`
  (single commit; hash in repo log).