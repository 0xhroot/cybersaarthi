"""Unit tests for structured error formatting."""

from __future__ import annotations

import json

from app.api.errors import error_response


def test_error_response_shape() -> None:
    response = error_response(503, "SERVICE_UNAVAILABLE", "Database is unavailable")
    assert response.status_code == 503
    assert json.loads(response.body) == {
        "error": {"code": "SERVICE_UNAVAILABLE", "message": "Database is unavailable"}
    }


def test_error_response_accepts_headers() -> None:
    response = error_response(
        429, "TOO_MANY_REQUESTS", "Rate limit exceeded", headers={"Retry-After": "60"}
    )
    assert response.headers["Retry-After"] == "60"
