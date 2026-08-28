"""API tests for the readiness endpoint and structured errors."""

from __future__ import annotations

import app.main as main
import httpx
import pytest


class HealthyProbe:
    async def ping(self) -> None:
        return None


class FailingProbe:
    async def ping(self) -> None:
        raise ConnectionError("down")


async def test_readiness_reports_not_ready_when_dependency_down(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main.app.state, "graph_store", FailingProbe())
    monkeypatch.setattr(main.app.state, "database", HealthyProbe())
    monkeypatch.setattr(main.app.state, "cache", HealthyProbe())
    monkeypatch.setattr(main.app.state, "storage", HealthyProbe())

    response = await http_client.get("/api/v1/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["services"]["neo4j"] == "unavailable"
    assert body["services"]["postgres"] == "ok"


@pytest.mark.integration
async def test_readiness_ready_with_infrastructure(http_client: httpx.AsyncClient) -> None:
    response = await http_client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert all(value == "ok" for value in body["services"].values())


async def test_unknown_route_returns_structured_404(http_client: httpx.AsyncClient) -> None:
    response = await http_client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Not Found"}}
