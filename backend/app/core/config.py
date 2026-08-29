"""Application configuration loaded from environment variables.

All environment-specific values come from the environment (or a local `.env` file
during development). Real credentials must never be hard-coded here or committed.
"""

from functools import lru_cache
from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRETS = {"changeme", "change-me", "password", "secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "cybersaarthi"
    APP_ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    # PostgreSQL
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "cybersaarthi"
    POSTGRES_USER: str = "cybersaarthi"
    POSTGRES_PASSWORD: str = "cybersaarthi"

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "cybersaarthi"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Object storage (S3-compatible)
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "cybersaarthi"
    S3_SECRET_KEY: str = "cybersaarthi"
    S3_BUCKET: str = "cybersaarthi"
    S3_REGION: str = "us-east-1"

    # Evidence ingestion
    EVIDENCE_MAX_SIZE_BYTES: int = 5 * 1024 * 1024
    SPA_MODEL: str = "en_core_web_sm"

    # Entity resolution thresholds (0-100)
    RESOLUTION_AUTO_THRESHOLD: float = 92.0
    RESOLUTION_REVIEW_THRESHOLD: float = 78.0

    # Graph sync
    GRAPH_CHUNK_SIZE: int = 250

    # Analytics pipeline. Thresholds live here (not scattered through services)
    # so every analytical decision is configurable in one place.
    ANALYTICS_GRAPH_NODE_CAP: int = 2000  # full exact algorithms below this size
    ANALYTICS_PATH_MAX_HOPS: int = 4  # bounded multi-hop traversal (default)
    ANALYTICS_PATH_RESULT_LIMIT: int = 10
    ANALYTICS_COMMUNITY_QUALITY: float = 0.0  # greedy modularity stop threshold
    ANALYTICS_MAX_HYPOTHESES: int = 25
    ANALYTICS_PATTERN_SHARED_IDENTIFIER_MIN: int = 3  # entities sharing one identifier
    ANALYTICS_PATTERN_CONCENTRATION_MIN: int = 5  # fan-out to flag concentration
    ANALYTICS_PATTERN_BRIDGE_MIN_COMMUNITIES: int = 2
    ANALYTICS_PATTERN_ANOMALY_TAIL: float = 0.95  # degree >= this percentile is anomalous
    ANALYTICS_PATTERN_RAPID_SPREAD_SECONDS: int = 3600  # min timestamp spread for a growth signal

    # Resolution safety cap: how many existing entities per blocking key to
    # compare against. Guards against accidental O(N^2) behaviour.
    MAX_CANDIDATE_TARGETS_PER_KEY: int = 25

    # Security
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, value: str | list[str]) -> str:
        if isinstance(value, list):
            return ",".join(value)
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @model_validator(mode="after")
    def validate_secrets_in_production(self) -> Self:
        if self.APP_ENV != "production":
            return self

        secret_pairs = {
            "POSTGRES_PASSWORD": self.POSTGRES_PASSWORD,
            "NEO4J_PASSWORD": self.NEO4J_PASSWORD,
            "S3_SECRET_KEY": self.S3_SECRET_KEY,
            "SECRET_KEY": self.SECRET_KEY,
        }
        failing = [
            name
            for name, value in secret_pairs.items()
            if not value or value.lower() in PLACEHOLDER_SECRETS
        ]
        if failing:
            raise ValueError(
                f"Refusing to start in production: {', '.join(failing)} "
                "must be set to real, non-placeholder values."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
