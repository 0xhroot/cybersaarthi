# Phase 2: Evidence ingestion, entity resolution and graph projection

- **Status:** Implemented
- **Date:** Phase 2 (SIH 26189)
- **Scope:** evidence upload + provenance, parsing, extraction, entity resolution,
  relationship extraction, PostgreSQL source of truth, idempotent Neo4j projection,
  graph query APIs.
- **Out of scope (later phases):** network analytics (centrality, communities, suspicious
  patterns, Network DNA, missing-link engines), scoring, LLM/AI features, frontend UI,
  token-based auth/RBAC, audit automation, cloud/Kubernetes deployment.

## Pipeline overview

```
                        ┌────────────────────────────────────────────────┐
                        │                    Evidences                    │
                        └───────────────┬────────────────────────────────┘
                                        │  POST /cases/{id}/evidence
                                        v
                    ┌─────────────────────────────────────┐
                    │  validation  (size cap, sha256, fmt) │───► MinIO (object)
                    └─────────────────────┬───────────────┘
                                          v
                    ┌────────────  POST /cases/{id}/ingest  ────────────┐
                    │                                                   │
                    │  parse (CSV / JSON / TXT)                         │
                    │  extract mentions (field / rule / NER)            │
                    │  resolve mentions (blocking + fuzzy + context)    │
                    │  extract relationships (field pairs / co-occur)   │
                    │                        │                           │
                    │                        v                           │
                    │          PostgreSQL  (source of truth)            │
                    └───────────────────────┬───────────────────────────┘
                                            │  GraphSyncService.sync_case (MERGE)
                                            v
                                        Neo4j  (projection)
                                            │  GET /cases/{id}/graph
                                            v
                                        Graph APIs
```

Every step is deterministic and idempotent:

- Evidence files are deduplicated by content SHA-256 within a case (`409` on re-upload).
- Source records, candidates, entities, aliases, relationships and evidence rows all use
  PostgreSQL unique constraints; re-running a job never duplicates state.
- The Neo4j projection uses `MERGE` keyed by PostgreSQL ids, so re-syncing a case is stable.

## Modules

| Layer | Module | Responsibility |
|---|---|---|
| Validation | `app/services/validation.py` | `read_upload_with_cap` (streaming size cap), `detect_format` (extension-first, content-sniff fallback), `detect_encoding` (charset-normalizer), `fingerprint` (SHA-256) |
| Parsing | `app/services/parsing.py` | CSV (header-driven), JSON (object/array/scalar list), TXT (paragraphs) → ordered source records |
| Extraction | `app/services/extraction.py` | Field-alias + substring-hint mentions, rule extracts (phone, vehicle, Aadhaar, labelled account/document), spaCy NER (offline-safe), provenance per mention |
| Normalisation | `app/services/normalization.py` | `(valid, canonical, display)` per entity type; India-specific phone `+91` rule; blocking keys |
| NLP | `app/services/nlp.py` | Lazy spaCy loading (`en_core_web_sm`); returns no mentions if the model is unavailable |
| Resolution | `app/services/resolution.py` | Blocking → fuzzy (`rapidfuzz`) + shared-context overlap → AUTO / REVIEW / NO_MATCH |
| Relationships | `app/services/relationships.py` | Type-pair rules for structured records; sentence-window co-occurrence for free text; per-record cap |
| Graph sync | `app/services/graph_sync.py` | `MERGE` nodes/edges into Neo4j; uniqueness constraints; read-back |
| Ingestion | `app/services/ingestion.py` | Orchestrates one evidence file end-to-end; job lifecycle + graph status |
| Query | `app/services/entity_service.py` | Entities, aliases, relationships, review candidates, graph + stats + ego-graph projection |
| API | `app/api/routes/{evidence,entities,graph}.py` | HTTP surface (see below) |

## Entity resolution

Resolution is per-case and deterministic.

1. **Blocking** — only entities sharing the mention's blocking key are compared.
   Person keys use the surname prefix plus first initial (`arjun mehra` → `meh_a`), so
   spelling variants land in the same bucket and review can fire.
2. **Signals** — exact canonical equality, RapidFuzz `ratio`, and shared-context overlap
   (co-mentioned values from source records).
3. **Score** — `0.85 × fuzzy_ratio + 0.15 × context_overlap`, exact matches score 100.
4. **Decision** — `AUTO_MATCH` (≥92, link + alias + match row), `REVIEW` (78–92, recorded for
   analyst review), `NO_MATCH` (new entity created).

## Relationships

- Structured sources (CSV/JSON): typed field pairs within a record, e.g.
  person→phone `CALLED`, person→vehicle `OWNS`, person→org `WORKS_FOR`, person→location
  `LOCATED_AT`, phone→location `VISITED`, account↔account `TRANSFERRED_TO`, person↔person
  `ASSOCIATED_WITH`. Same-type pairs collapse as undirected edges; self-pairs are skipped.
- Free text (TXT): mentions co-occurring in one sentence window.
- Only mentions resolved to entities participate; review candidates do not.
- Per-record cap: `MAX_RELATIONSHIPS_PER_RECORD = 15`.

## API surface (Phase 2)

All under `/api/v1`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/cases/{id}/evidence` | Upload evidence (multipart), validate + hash, store in MinIO, dedup by SHA-256 |
| GET | `/cases/{id}/evidence` | List evidence files |
| POST | `/cases/{id}/ingest` | Run the ingestion pipeline for one evidence file |
| GET | `/cases/{id}/ingest-jobs` | List ingestion jobs |
| POST | `/cases/{id}/ingest/{job_id}/retry-graph-sync` | Re-project a job's case to Neo4j |
| GET | `/cases/{id}/entities` | List entities (filter by type/status/text, paginated) |
| GET | `/cases/{id}/entities/{entity_id}` | Entity detail + aliases + context |
| GET | `/cases/{id}/relationships` | List relationships |
| GET | `/cases/{id}/resolution/review` | Candidates awaiting analyst decision |
| GET | `/cases/{id}/graph` | Full case graph (nodes + edges) |
| GET | `/cases/{id}/graph/stats` | Node/edge counts and type breakdowns |
| GET | `/cases/{id}/graph/entity/{entity_id}` | Ego-graph for one entity |

## Schema

Phase 2 adds to `backend/migrations/versions/081a88d02574_phase_2_data_intelligence_pipeline.py`:

- `evidence_files` — stored object key, SHA-256, detected format/encoding, record count, status.
- `ingestion_jobs` — per-file run: status/stage/progress, summary, graph sync status + error.
- `source_records` — per-source record (ordered), `raw_data` + extracted `entity_mentions`,
  `relationships_data`, status.
- `entities` — canonical/display value, blocking key, type, confidence, status, context.
- `entity_aliases` — variant spellings for auto-matched entities.
- `entity_candidates` — every mention (idempotent `(record, type, value)`), resolution link.
- `entity_matches` — AUTO / REVIEW decisions with score + signals.
- `relationships` — typed edges with confidence, explanation, provenance source record.
- `relationship_evidence` — per-evidence rows for each relationship.

  ```mermaid
  erDiagram
      CASES ||--o{ EVIDENCE_FILES : contains
      EVIDENCE_FILES ||--o{ INGESTION_JOBS : processed_by
      EVIDENCE_FILES ||--o{ SOURCE_RECORDS : has
      SOURCE_RECORDS ||--o{ ENTITY_CANDIDATES : yields
      SOURCE_RECORDS ||--o{ RELATIONSHIPS : evidence_of
      SOURCE_RECORDS ||--o{ RELATIONSHIP_EVIDENCE : cited_by
      ENTITY_CANDIDATES }o..|| ENTITIES : resolves_to
      ENTITIES ||--o{ ENTITY_ALIASES : aliased_by
      ENTITY_CANDIDATES ||--o{ ENTITY_MATCHES : matched_by
      ENTITIES ||--o{ RELATIONSHIPS : source_or_target
      RELATIONSHIPS ||--o{ RELATIONSHIP_EVIDENCE : documented_by
      CASES ||--o{ ENTITIES : scopes
  ```

## Tests

- `tests/unit/test_normalization.py`, `test_parsing.py`, `test_validation.py`,
  `test_extraction.py`, `test_resolution.py`, `test_relationships.py` — pure unit coverage
  (no infrastructure required).
- `tests/integration/test_entity_pipeline.py` — end-to-end ingest against the real stack,
  incl. graph-sync idempotency and free-text ingestion; each test creates and removes its own case.
- `tests/api/test_phase2_api.py` — contract tests for the new endpoints via the ASGI test client.

Full suite: `make test` (requires `make up`). Lint/type: `make lint format-check typecheck`.