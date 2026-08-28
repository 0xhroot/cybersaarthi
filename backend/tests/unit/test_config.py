"""Unit tests for configuration loading and validation."""

from __future__ import annotations

import pytest
from app.core.config import Settings


def test_development_defaults_are_safe() -> None:
    settings = Settings(_env_file=None)
    assert settings.APP_ENV == "development"
    assert settings.LOG_LEVEL == "INFO"


def test_production_rejects_placeholder_secrets() -> None:
    with pytest.raises(ValueError, match="production"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            POSTGRES_PASSWORD="changeme",
            NEO4J_PASSWORD="not-a-placeholder",
            S3_SECRET_KEY="not-a-placeholder",
            SECRET_KEY="not-a-placeholder",
        )


def test_production_accepts_strong_secrets() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        POSTGRES_PASSWORD="p-strong-1a",
        NEO4J_PASSWORD="n-strong-1a",
        S3_SECRET_KEY="s-strong-1a",
        SECRET_KEY="secret-strong-1a",
    )
    assert settings.is_production


def test_production_rejects_missing_secret() -> None:
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            APP_ENV="production",
            POSTGRES_PASSWORD="p-strong-1a",
            NEO4J_PASSWORD="n-strong-1a",
            S3_SECRET_KEY="",
            SECRET_KEY="secret-strong-1a",
        )


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(_env_file=None, CORS_ORIGINS="http://a.example, http://b.example")
    assert settings.cors_origins == ["http://a.example", "http://b.example"]


def test_postgres_dsn_is_built_from_parts() -> None:
    settings = Settings(
        _env_file=None,
        POSTGRES_HOST="postgres",
        POSTGRES_PORT=5432,
        POSTGRES_USER="cybersaarthi",
        POSTGRES_PASSWORD="secret",
        POSTGRES_DB="cybersaarthi",
    )
    assert (
        settings.postgres_dsn
        == "postgresql+psycopg://cybersaarthi:secret@postgres:5432/cybersaarthi"
    )
