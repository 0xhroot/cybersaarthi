# Tests

Test layout:

- `tests/unit/`      - no infrastructure required, run anywhere.
- `tests/api/`       - exercises HTTP endpoints against the FastAPI app.
- `tests/integration/` - requires the Docker Compose infrastructure
  (PostgreSQL, Neo4j, Redis, MinIO). These are skipped automatically when the
  services are unreachable, e.g. when running outside the Compose stack.

Run everything with `make test` (executes inside the backend container, where
all infrastructure service names resolve).

Run the fast suite only with `make test-unit`.