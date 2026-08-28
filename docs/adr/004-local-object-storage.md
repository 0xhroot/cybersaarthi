# ADR-004: Local object storage (MinIO) instead of filesystem volumes

- **Status:** Accepted
- **Date:** Phase 1 (SIH 26189)
- **Decision makers:** backend engineering, platform engineering

## Context

Evidence/artefact files (images, documents, extracted text) will be a first-class input in
later phases. Storing them on a plain Docker volume couples the application to the host
filesystem layout and makes "upload a file, later analyze it" untestable across machines and
in CI.

Phase 1 must: provision an S3-compatible API that the backend talks to over the network
(**not** localhost), keep the developer experience zero-config, and prove the connection and
round-trip in tests.

## Decision

Use **MinIO** as a local S3-compatible object store:

- `minio` service runs the MinIO server with a named volume.
- `minio-init` (one-shot `minio/mc`) creates the bucket declaratively at stack start.
- The backend wrapper `app/db/storage.py` is lazy, `boto3`-based, and exposes
  `exists/upload/download/delete` plus the readiness `ping` (which round-trips against the
  bucket).
- Credentials and bucket name are injected via Compose env (`S3_ACCESS_KEY`,
  `S3_SECRET_KEY`, `S3_BUCKET`), shared between MinIO and the backend from `.env`.

## Consequences

- The staging API is identical in shape to production object storage, so later swaps to
  another S3 implementation don't touch application code.
- Buckets initialise automatically (successful-exit dependency); no manual console steps.
- Integration tests (`tests/integration/test_storage.py`) run against real MinIO and are
  skipped with a clear message when the stack is down.
- Cost: an extra container and credential surface; accepted for the portability win.
- The strictest S3 policies are a deployment-time concern (ADR not yet written for
  production object-storage hardening).