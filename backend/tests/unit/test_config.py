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


def _staging(**overrides) -> Settings:
    base = dict(
        POSTGRES_PASSWORD="p-strong-1a",
        NEO4J_PASSWORD="n-strong-1a",
        S3_SECRET_KEY="s-strong-1a",
        SECRET_KEY="secret-strong-1a",
        CORS_ORIGINS="https://app.example",
    )
    base.update(overrides)
    return Settings(_env_file=None, APP_ENV="staging", **base)


def test_staging_rejects_placeholder_secrets() -> None:
    """A05: the guard is not production-only — any non-dev/test env must
    already hold real secrets."""
    with pytest.raises(ValueError, match="SECRET_KEY"):
        _staging(SECRET_KEY="change-me")


def test_redis_url_placeholder_credentials_rejected() -> None:
    """A05: REDIS_URL credentials are validated like the other secrets."""
    with pytest.raises(ValueError, match="REDIS_URL"):
        _staging(REDIS_URL="redis://:secret@redis:6379/0")


def test_redis_url_real_credentials_accepted() -> None:
    settings = _staging(REDIS_URL="redis://:r-strong-9d@redis:6379/0")
    assert settings.REDIS_URL.startswith("redis://")


def test_cors_wildcard_rejected_outside_dev() -> None:
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _staging(CORS_ORIGINS="*")


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
