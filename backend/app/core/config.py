"""Application configuration loaded from environment variables.

All environment-specific values come from the environment (or a local `.env` file
during development). Real credentials must never be hard-coded here or committed.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRETS = {"changeme", "change-me", "password", "secret"}
# Environments that are allowed to run with the development defaults below.
DEV_ENVIRONMENTS = {"development", "test"}


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

    # Object storage (S3-compatible). STORAGE_* aliases are the canonical
    # Phase 5 names; S3_* remain accepted for backward compatibility.
    STORAGE_ENDPOINT: str = "http://localhost:9000"
    STORAGE_ACCESS_KEY: str = "cybersaarthi"
    STORAGE_SECRET_KEY: str = "cybersaarthi"
    STORAGE_BUCKET: str = "cybersaarthi"
    STORAGE_REGION: str = "us-east-1"

    S3_ENDPOINT: str = Field(
        default="http://localhost:9000",
        validation_alias=AliasChoices("STORAGE_ENDPOINT", "S3_ENDPOINT"),
    )
    S3_ACCESS_KEY: str = Field(
        default="cybersaarthi", validation_alias=AliasChoices("STORAGE_ACCESS_KEY", "S3_ACCESS_KEY")
    )
    S3_SECRET_KEY: str = Field(
        default="cybersaarthi", validation_alias=AliasChoices("STORAGE_SECRET_KEY", "S3_SECRET_KEY")
    )
    S3_BUCKET: str = Field(
        default="cybersaarthi", validation_alias=AliasChoices("STORAGE_BUCKET", "S3_BUCKET")
    )
    S3_REGION: str = Field(
        default="us-east-1", validation_alias=AliasChoices("STORAGE_REGION", "S3_REGION")
    )

    # Evidence ingestion
    EVIDENCE_MAX_SIZE_BYTES: int = 5 * 1024 * 1024
    EVIDENCE_PDF_MAX_PAGES: int = 200  # hard page cap; larger PDFs are rejected
    EVIDENCE_PDF_PAGE_MAX_CHARS: int = 12000  # per-page text cap in stored records
    SPA_MODEL: str = "en_core_web_sm"

    # Smart ingestion copilot (feature 1): bounded, page-aware LLM extraction.
    EXTRACTION_MAX_PAGES: int = 25  # max records processed per extraction job
    EXTRACTION_CONTEXT_MAX_CHARS: int = 4000  # bounded context window per model call
    EXTRACTION_MAX_OUTPUT_TOKENS: int = 768  # room for a full JSON reply
    EXTRACTION_TIMEOUT_SECONDS: int = 600  # AnalysisJob timeout for one extraction run

    # Chain-of-custody auditor (feature 9): bounded, deterministic audit runs.
    CUSTODY_AUDIT_MAX_EVIDENCE: int = 50  # evidence items per case-wide audit
    CUSTODY_FUTURE_SKEW_SECONDS: int = 300  # tolerated clock skew for occurred_at
    CUSTODY_TIMEOUT_SECONDS: int = 300  # AnalysisJob timeout for one audit run

    # Entity resolution thresholds (0-100)
    RESOLUTION_AUTO_THRESHOLD: float = 92.0
    RESOLUTION_REVIEW_THRESHOLD: float = 78.0

    # Phase 3 feature A: entity-pair resolution jobs (bounded pair generation).
    RESOLUTION_MAX_ENTITIES: int = 500  # entities scanned per case-wide run
    RESOLUTION_MAX_PER_BUCKET: int = 25  # pairs generated inside one blocking bucket
    RESOLUTION_MAX_PAIRS: int = 150  # candidate pairs evaluated per run
    RESOLUTION_MAX_LLM_PAIRS: int = 10  # ambiguous pairs sent to the local model
    RESOLUTION_TIMEOUT_SECONDS: int = 300  # AnalysisJob timeout for one run

    # Phase 3 feature B: timeline reconstruction (deterministic extraction).
    TIMELINE_MAX_RECORDS: int = 500  # source records scanned per run
    TIMELINE_MAX_ARTIFACTS: int = 50  # extraction artifacts scanned per run
    TIMELINE_TIMEOUT_SECONDS: int = 300  # AnalysisJob timeout for one run

    # Phase 3 feature C: contradiction detection (bounded comparisons).
    CONTRADICTION_MAX_RECORDS: int = 200  # source records scanned per run
    CONTRADICTION_MAX_RECORDS_PER_ANCHOR: int = 8  # pairs per anchor group are O(n^2)
    CONTRADICTION_MAX_PAIR_EVALS: int = 2000  # deterministic pair-evaluation budget
    CONTRADICTION_MAX_LLM_PAIRS: int = 10  # statement pairs sent to the local model
    CONTRADICTION_TIMEOUT_SECONDS: int = 300  # AnalysisJob timeout for one run

    # Phase 4 feature A: financial flow intelligence (deterministic extraction
    # + aggregates + structure network + pattern rules).
    FLOW_MAX_RECORDS: int = 1000  # source records scanned per run
    FLOW_MAX_FACTS: int = 2000  # extracted facts kept in the artifact payload
    FLOW_MAX_EDGES: int = 500  # structure-network edges per run
    FLOW_MAX_SUPPORTING_IDS: int = 100  # supporting ids kept per aggregate
    FLOW_AMOUNT_THRESHOLD: str = "5000"  # investigation default (exact Decimal)
    FLOW_TIMEOUT_SECONDS: int = 300  # AnalysisJob timeout for one run

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

    # Local AI platform (llama.cpp server + Qwen3 GGUF). Inference is
    # localhost-only; the browser never talks to the model server.
    AI_ENABLED: bool = True
    AI_MODEL_PATH: str = "Qwen3-8B-Q4_K_M.gguf"  # absolute, or relative to repo root
    AI_SERVER_BINARY: str = "ai_runtime/llama.cpp/llama-server"  # relative to repo root
    AI_SERVER_HOST: str = "127.0.0.1"
    AI_SERVER_PORT: int = 8081
    # Shared secret sent to llama-server (--api-key). Required whenever the
    # inference server listens on a non-loopback interface (e.g. the Docker
    # bridge); empty disables the header (loopback-only deployments).
    AI_SERVER_API_KEY: str = ""
    # Optional Unix domain socket path (see scripts/ai/socket_bridge.sh).
    # When set, the backend talks to llama-server over the socket instead of
    # TCP — used when host firewalls block Docker bridge → host traffic.
    AI_SERVER_SOCKET: str = ""
    AI_MANAGE_SERVER: bool = True  # spawn llama-server from the app lifespan
    AI_CONTEXT_LENGTH: int = 8192
    AI_MAX_OUTPUT_TOKENS: int = 512
    AI_GPU_LAYERS: int = -1  # -1 offloads every layer; set >=0 for partial/CPU
    AI_REQUEST_TIMEOUT_SECONDS: float = 180.0
    AI_MAX_CONCURRENT_GENERATIONS: int = 2
    # Answer profile: which latency/quality trade-off a plain chat turn uses
    # when the client does not send an explicit ``profile``. The per-profile
    # token/iteration budgets below are floors and ceilings, not exact values.
    AI_DEFAULT_PROFILE: Literal["quick", "standard", "deep"] = "standard"
    AI_PROFILE_QUICK_MAX_TOKENS: int = 160
    AI_PROFILE_QUICK_TOOL_ITERATIONS: int = 2
    AI_PROFILE_STANDARD_MAX_TOKENS: int = 384
    AI_PROFILE_STANDARD_TOOL_ITERATIONS: int = 3
    AI_PROFILE_DEEP_MAX_TOKENS: int = 768
    AI_PROFILE_DEEP_TOOL_ITERATIONS: int = 4
    AI_PER_USER_RATE_LIMIT: int = 20  # chat requests per minute; 0 disables
    AI_MAX_HISTORY_MESSAGES: int = 12
    AI_TOOL_MAX_ITERATIONS: int = 3
    AI_CONVERSATION_RETENTION_DAYS: int = 90
    AI_KNOWLEDGE_ENABLED: bool = True
    AI_FEATURE_CASE: bool = True
    AI_FEATURE_EVIDENCE: bool = True
    AI_FEATURE_GRAPH: bool = True
    AI_FEATURE_COPILOT: bool = True
    AI_FEATURE_REPORT_DRAFT: bool = True
    AI_FEATURE_EXTRACTION: bool = True  # smart ingestion copilot (feature 1)
    AI_FEATURE_INTEGRITY_EXPLAIN: bool = True  # custody AI explanations (feature 9)
    AI_FEATURE_RESOLUTION: bool = True  # ambiguous entity-pair comparison (phase 3 A)
    AI_FEATURE_CONTRADICTION: bool = True  # semantic statement comparison (phase 3 C)
    AI_LOG_PROMPTS: bool = False  # prompt/answer content is never logged by default

    # Security
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    # Login throttling (Redis-backed). Set LOGIN_MAX_ATTEMPTS to 0 to disable.
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_IP_MAX_ATTEMPTS: int = 20
    LOGIN_LOCKOUT_SECONDS: int = 300
    LOGIN_MAX_LOCKOUT_SECONDS: int = 3600
    LOGIN_THROTTLE_FAIL_CLOSED: bool = True
    # Server-side token revocation (A07). Enabled by default: logout/revoke
    # semantics are backed by Redis at a small per-request cost, and a Redis
    # outage fails *closed* for reads so a revoked token is never trusted again.
    TOKEN_REVOCATION_ENABLED: bool = True

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
    def repo_root(self) -> Path:
        """Repository root for AI artifacts and docs.

        Honors ``CYBERSAARTHI_REPO_ROOT`` (set by the dev container, which
        mounts the whole repo at /repo); otherwise walks up from this file
        (``backend/app/core`` → repo root).
        """
        override = os.environ.get("CYBERSAARTHI_REPO_ROOT")
        if override:
            return Path(override).resolve()
        return Path(__file__).resolve().parents[3]

    def resolve_path(self, value: str) -> Path:
        """Resolve a configured path; relative paths anchor at the repo root."""
        path = Path(value).expanduser()
        return path if path.is_absolute() else (self.repo_root / path).resolve()

    @property
    def ai_model_file(self) -> Path:
        return self.resolve_path(self.AI_MODEL_PATH)

    @property
    def ai_server_binary_file(self) -> Path:
        return self.resolve_path(self.AI_SERVER_BINARY)

    @property
    def ai_base_url(self) -> str:
        return f"http://{self.AI_SERVER_HOST}:{self.AI_SERVER_PORT}"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @model_validator(mode="after")
    def validate_secrets_outside_dev(self) -> Self:
        """A05: refuse obvious deployment foot-guns outside development/test.

        Previously the guard only fired for APP_ENV == "production", so an
        operator running "staging"/"qa" (or a production that never set the
        flag) silently shipped with a known signing secret. Now any environment
        other than development/test must set real secrets — and that check now
        covers REDIS_URL credentials and the CORS allowlist too.
        """
        if self.APP_ENV in DEV_ENVIRONMENTS:
            return self

        def is_placeholder(value: str) -> bool:
            return not value or value.lower() in PLACEHOLDER_SECRETS

        def redis_creds_placeholder(url: str) -> bool:
            try:
                netloc = urlsplit(url).netloc
            except ValueError:
                netloc = url
            if "@" not in netloc:
                return False
            userinfo = netloc.split("@", 1)[0]
            password_part = userinfo.split(":", 1)[1] if ":" in userinfo else userinfo
            return not password_part or password_part.lower() in PLACEHOLDER_SECRETS

        failing = [
            name
            for name, value in {
                "POSTGRES_PASSWORD": self.POSTGRES_PASSWORD,
                "NEO4J_PASSWORD": self.NEO4J_PASSWORD,
                "S3_SECRET_KEY": self.S3_SECRET_KEY,
                "SECRET_KEY": self.SECRET_KEY,
                "REDIS_URL": self.REDIS_URL,
            }.items()
            if (is_placeholder(value) if name != "REDIS_URL" else redis_creds_placeholder(value))
        ]
        if not self.cors_origins or "*" in self.cors_origins:
            failing.append("CORS_ORIGINS")
        if failing:
            raise ValueError(
                f"Refusing to start in environment {self.APP_ENV!r}: {', '.join(failing)} "
                "must be set to real, non-placeholder values."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
