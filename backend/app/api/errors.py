"""Shared helpers for building structured API errors."""

from __future__ import annotations

from fastapi.responses import JSONResponse

from app.schemas.error import ApiError, ApiErrorResponse


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ApiErrorResponse(error=ApiError(code=code, message=message)).model_dump(),
        headers=headers,
    )
