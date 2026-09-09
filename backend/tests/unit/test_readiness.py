"""Unit tests for the readiness aggregation service using fake probes."""

from __future__ import annotations

import pytest
from app.services.readiness import ReadinessService


class HealthyProbe:
    async def ping(self) -> None:
        return None


class FailingProbe:
    async def ping(self) -> None:
        raise ConnectionError("down")


@pytest.fixture
def healthy_service() -> ReadinessService:
    return ReadinessService(HealthyProbe(), HealthyProbe(), HealthyProbe(), HealthyProbe())


@pytest.fixture
def unhealthy_service() -> ReadinessService:
    return ReadinessService(FailingProbe(), FailingProbe(), FailingProbe(), FailingProbe())


async def test_all_healthy_reports_ready(healthy_service: ReadinessService) -> None:
    response, ready = await healthy_service.check()
    assert ready is True
    assert response.status == "ready"
    states = response.services.model_dump()
    assert set(states) == {"postgres", "neo4j", "redis", "object_storage"}
    assert all(value == "ok" for value in states.values())


async def test_all_down_reports_not_ready(unhealthy_service: ReadinessService) -> None:
    response, ready = await unhealthy_service.check()
    assert ready is False
    assert response.status == "not_ready"
    assert response.services.postgres == "unavailable"


async def test_single_failure_flips_status() -> None:
    service = ReadinessService(HealthyProbe(), FailingProbe(), HealthyProbe(), HealthyProbe())
    response, ready = await service.check()
    assert ready is False
    assert response.status == "not_ready"
    assert response.services.neo4j == "unavailable"
    assert response.services.postgres == "ok"
