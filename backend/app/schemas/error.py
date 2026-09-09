"""Structured error response schemas.

Every error surfaced to clients follows this shape so the frontend can render
errors uniformly. Raw driver exceptions are never exposed.
"""

from __future__ import annotations

from pydantic import BaseModel


class ApiError(BaseModel):
    code: str
    message: str


class ApiErrorResponse(BaseModel):
    error: ApiError
