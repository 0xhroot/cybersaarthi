"""Shared helpers for building structured API errors.

Phase 5 exposes stable, machine-readable error codes so the frontend can map
specific account-lifecycle conditions (PENDING/SUSPENDED/REJECTED, bad
credentials, insufficient permission, case access denied, duplicate account)
without parsing prose. ``ApiHTTPException`` lets handlers attach a code to
any status they raise; the app-level handler renders it in the standard
``{"error": {"code", "message"}}`` envelope.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.core.codes import (  # noqa: F401  (re-exported for API callers)
    CODE_ACCOUNT_NOT_ACTIVE,
    CODE_ACCOUNT_PENDING,
    CODE_ACCOUNT_REJECTED,
    CODE_ACCOUNT_SUSPENDED,
    CODE_ACCOUNT_TRANSITION_INVALID,
    CODE_CASE_ACCESS_DENIED,
    CODE_CASE_READ_ONLY,
    CODE_DUPLICATE_DEVICE_SERIAL,
    CODE_DUPLICATE_EMAIL,
    CODE_INSUFFICIENT_PERMISSION,
    CODE_INVALID_CREDENTIALS,
    MESSAGES,
)
from app.schemas.error import ApiError, ApiErrorResponse


class ApiHTTPException(HTTPException):
    """An HTTP error carrying a stable machine-readable ``code``."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ApiErrorResponse(error=ApiError(code=code, message=message)).model_dump(),
        headers=headers,
    )
