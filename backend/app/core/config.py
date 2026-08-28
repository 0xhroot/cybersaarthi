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
