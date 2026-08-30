"""Request schemas for findings review."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FindingStatusLiteral = Literal["NEW", "REVIEWED", "DISMISSED", "CONFIRMED"]


class FindingStatusUpdate(BaseModel):
    status: FindingStatusLiteral
    reason: str | None = Field(default=None, max_length=2000, description="Reviewer note")
