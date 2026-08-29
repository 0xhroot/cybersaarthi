"""Request schemas for findings review."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

FindingStatusLiteral = Literal["NEW", "REVIEWED", "DISMISSED", "CONFIRMED"]


class FindingStatusUpdate(BaseModel):
    status: FindingStatusLiteral
