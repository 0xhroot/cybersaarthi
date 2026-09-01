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

from app.schemas.error import ApiError, ApiErrorResponse

# Stable error codes (Phase 5). Frontend matches on these, not on prose.
CODE_INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
CODE_ACCOUNT_PENDING = "ACCOUNT_PENDING"
CODE_ACCOUNT_SUSPENDED = "ACCOUNT_SUSPENDED"
CODE_ACCOUNT_REJECTED = "ACCOUNT_REJECTED"
CODE_INSUFFICIENT_PERMISSION = "INSUFFICIENT_PERMISSION"
CODE_CASE_ACCESS_DENIED = "CASE_ACCESS_DENIED"
CODE_DUPLICATE_EMAIL = "DUPLICATE_EMAIL"

MESSAGES = {
    CODE_INVALID_CREDENTIALS: "invalid username or password",
    CODE_ACCOUNT_PENDING: "account is pending administrator approval",
    CODE_ACCOUNT_SUSPENDED: "account has been suspended",
    CODE_ACCOUNT_REJECTED: "account registration was rejected",
}


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
