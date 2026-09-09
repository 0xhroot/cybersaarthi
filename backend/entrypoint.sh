#!/bin/sh
set -e

echo "[cybersaarthi] applying database migrations"
alembic upgrade head

exec "$@"