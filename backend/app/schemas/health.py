"""Response schemas for the health and readiness endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class ServiceStates(BaseModel):
    postgres: str
    neo4j: str
    redis: str
    object_storage: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    services: ServiceStates
