"""API contract tests: request observability (correlation ids)."""

from __future__ import annotations

import uuid

from app.core.config import get_settings
from app.main import app
from httpx import ASGITransport, AsyncClient


async def test_responses_echo_a_generated_request_id(http_client) -> None:
    prefix = get_settings().API_V1_PREFIX
    response = await http_client.get(f"{prefix}/health")
    assert response.status_code == 200
    request_id = response.headers.get("x-request-id")
    assert request_id
    assert len(request_id) == 32  # generated hex uuid


async def test_client_supplied_request_id_is_honoured(http_client) -> None:
    prefix = get_settings().API_V1_PREFIX
    supplied = uuid.uuid4().hex
    transport = httpx_transport()
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"X-Request-Id": supplied},
    ) as client:
        response = await client.get(f"{prefix}/health")
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == supplied


async def test_correlation_is_echoed_even_on_errors(http_client) -> None:
    prefix = get_settings().API_V1_PREFIX
    async with AsyncClient(transport=httpx_transport(), base_url="http://testserver") as client:
        response = await client.get(f"{prefix}/cases/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.headers.get("x-request-id")


def httpx_transport() -> ASGITransport:
    return ASGITransport(app=app)
