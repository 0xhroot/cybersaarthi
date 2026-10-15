"""API package.

``api_router`` is exposed lazily: eagerly importing it here would make
``from app.api.errors import ...`` (used by the AI package) execute the whole
route tree and re-enter partially initialized modules.
"""

from __future__ import annotations

from typing import Any

__all__ = ["api_router"]


def __getattr__(name: str) -> Any:
    if name == "api_router":
        from app.api.router import api_router

        return api_router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
