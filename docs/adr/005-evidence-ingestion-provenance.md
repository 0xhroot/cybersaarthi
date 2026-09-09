# ADR-005: Evidence ingestion with content-based provenance

- **Status:** Accepted
- **Date:** Phase 2 (SIH 26189)
- **Decision makers:** backend engineering

## Context

Phase 2 must accept investigation inputs of different shapes (structured CSV/JSON and
free-text TXT), turn them into entity/relationship data, and preserve exactly where every
fact came from. Investigators need to trust the pipeline: an uploaded file must be
recognisable later, re-uploads must not duplicate data, and every extracted entity and
relationship must trace back to a source file and record.

## Decision

Ingest one evidence file per run through a deterministic, idempotent pipeline:

- **Validation before storage.** `read_upload_with_cap` streams the body against
  `EVIDENCE_MAX_SIZE_BYTES`, computes a content SHA-256, detects format (extension-first,
  content-sniff fallback) and encoding (charset-normalizer).
- **Storage.** The validated blob goes to MinIO under `cases/{case_id}/evidence/{uuid}/{stem}`;
  the database never holds file bytes, only a `stored_key` and the digest.
- **Dedup by digest.** Re-uploading identical bytes for the same case returns `409`; the file
  is never stored twice.
- **Records keep order and raw form.** Parsing emits an ordered list of source records; the raw
  dict is persisted so extraction can always be explained or re-run.
- **Provenance everywhere.** Mentions carry source/offsets; relationships carry the originating
  source record; entity matches carry the candidate + score signals. `entity_mentions` and
  `relationships_data` are persisted per record for auditability.
- **Idempotent re-run.** Unique constraints on source records, candidates, entities, aliases
  and relationships mean re-ingesting a job cannot duplicate state.

## Consequences

- Every fact is traceable to a `source_record` and ultimately an `evidence_file` (SHA-256).
- Idempotency makes the seed script and retries safe to re-run.
- Cost: pipeline runtime is synchronous in the request (single-worker local mode); a
  Redis-backed worker queue is deferred to a later phase.
- Cost: raw `raw_data` is stored as JSONB, duplicating some information in columnar form; the
  provenance/audit win outweighs the storage overhead.