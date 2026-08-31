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
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"


async def test_production_headers_only_when_strict() -> None:
    """A12: HSTS + CSP are added only in production (strict mode).

    In the dev/test environment the SecurityHeadersMiddleware must stay
    non-strict so browsers do not cache HSTS/CSP while iterating locally.
    """
    from app.middleware import SecurityHeadersMiddleware
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def _endpoint(request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    async def _fetch(strict: bool) -> dict[str, str]:
        inner = Starlette(routes=[Route("/", _endpoint)])
        app = SecurityHeadersMiddleware(inner, strict=strict)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/")
            return dict(response.headers)

    dev_headers = await _fetch(strict=False)
    assert "strict-transport-security" not in dev_headers
    assert "content-security-policy" not in dev_headers

    prod_headers = await _fetch(strict=True)
    assert prod_headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
    assert "frame-ancestors 'none'" in prod_headers["content-security-policy"]


async def test_docs_are_available(http_client: httpx.AsyncClient) -> None:
    response = await http_client.get("/docs")
    assert response.status_code == 200
