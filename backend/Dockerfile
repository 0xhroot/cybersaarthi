# syntax=docker/dockerfile:1

# ---- base: shared Python environment (no packages installed) ----
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY entrypoint.sh /entrypoint.sh

# ---- dev: adds verification tooling (pytest, ruff, mypy) ----
#
# Used only by the development/verification workflow (`make test`, `make lint`,
# `make format-check`, `make typecheck`). It installs EVERY dependency group
# deterministically from backend/uv.lock via uv into /opt/venv. /opt/venv lives
# outside the source tree so the `./backend:/src` bind mount never hides it,
# while the editable `app` package resolves from the mounted working directory
# (/src), so uncommitted edits are picked up without a rebuild.
FROM base AS dev

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

COPY uv.lock ./

RUN mkdir -p /src \
    && cp pyproject.toml alembic.ini uv.lock /src/ \
    && cp -r app migrations /src/ \
    && cd /src \
    && uv sync --frozen --all-extras \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /opt/venv /src /app \
    && chmod +x /entrypoint.sh

USER appuser

EXPOSE 8000

WORKDIR /src
CMD ["tail", "-f", "/dev/null"]

# ---- runtime: lean production image (runtime deps only, no dev tools) ----
#
# This is the image used by `docker compose up -d`. It must remain the FINAL
# stage so that a plain `docker compose build backend` (no explicit target)
# produces the lean runtime image. It installs ONLY the runtime dependencies
# (`--only main`) so pytest/ruff/mypy never ship in production. Dependencies go
# into the system site-packages rather than a `.venv` so the `./backend:/app`
# bind mount does not hide them at runtime.
FROM base AS runtime

RUN pip install --no-cache-dir -e . \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app \
    && chmod +x /entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
