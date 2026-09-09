# Contributing to CyberSaarthi

Thanks for your interest in contributing! CyberSaarthi is an investigation
intelligence platform. This guide keeps contributions consistent and safe.

## Getting set up

Everything runs through Docker Compose, so there is nothing to install on the
host except [Docker](https://docs.docker.com/engine/install/) (and its
[Compose plugin](https://docs.docker.com/compose/install/)).

```bash
git clone https://github.com/0xhroot/cybersaarthi.git
cd cybersaarthi
cp .env.example .env        # dev-safe defaults; never commit .env
docker compose up -d --build
make migrate                # apply migrations (auto-runs on startup too)
make seed                   # optional: deterministic demo case
```

## Development loop

| Action | Command |
| --- | --- |
| Backend tests (unit · api · integration) | `make test` |
| Backend tests without infrastructure | `make test-unit` |
| Lint | `make lint` |
| Format check | `make format-check` |
| Typecheck | `make typecheck` |
| New migration | `make migration MSG="describe change"` |
| Frontend tests | `cd frontend && npm test -- --run` |
| Frontend lint / typecheck / build | `npm run lint` · `npm run typecheck` · `npm run build` |

No `make` on Windows / Docker Desktop? Use the Docker equivalents, e.g.
`docker compose run --rm backend-dev pytest`.

## Making changes

- **Backend** — modular monolith under `backend/app`; mirror the existing
  module layout and add tests in `backend/tests/`.
- **Frontend** — pages under `frontend/src/app/pages`; reuse the typed API
  facade and query layer.
- Run the relevant gate before pushing (tests, lint, format, typecheck).

## Pull request workflow

1. Open an issue first for non-trivial changes, or reference an existing one.
2. Branch from `main`; keep changes focused on a single concern.
3. Use [Conventional Commits](https://www.conventionalcommits.org/) for commit
   messages (e.g. `feat(backend):`, `fix(frontend):`, `docs:`).
4. Ensure CI passes on your branch.
5. Describe your change in the PR template; include screenshots for UI changes
   and note any breaking changes.

## Do not

- Commit `.env`, secrets, `node_modules`, `.venv`, caches, or build output —
  these are gitignored.
- Hand-edit applied Alembic migrations (`backend/migrations/versions/`); always
  generate new ones with `make migration MSG=...`.
- Report security issues as public issues — see [SECURITY.md](SECURITY.md).
