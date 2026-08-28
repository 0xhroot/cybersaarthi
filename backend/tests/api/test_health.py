"""API tests for the health endpoint (process liveness)."""

from __future__ import annotations

import httpx
import pytest


class FailingProbe:
    async def ping(self) -> None:
        raise ConnectionError("down")


async def test_health_returns_ok(http_client: httpx.AsyncClient) -> None:
    response = await http_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "cybersaarthi"
    assert isinstance(body["version"], str)


async def test_health_does_not_probe_infrastructure(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Health must stay green even when every dependency client would fail.
    import app.main as main

    monkeypatch.setattr(main.app.state, "database", FailingProbe())
    monkeypatch.setattr(main.app.state, "graph_store", FailingProbe())
    monkeypatch.setattr(main.app.state, "cache", FailingProbe())
    monkeypatch.setattr(main.app.state, "storage", FailingProbe())

    response = await http_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_security_headers_present(http_client: httpx.AsyncClient) -> None:
    response = await http_client.get("/api/v1/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


async def test_docs_are_available(http_client: httpx.AsyncClient) -> None:
    response = await http_client.get("/docs")
    assert response.status_code == 200
