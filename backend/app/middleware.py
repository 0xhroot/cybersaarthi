"""ASGI middleware: security response headers and request observability."""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-XSS-Protection": "1; mode=block",
}

_REQUEST_ID_HEADERS = ("x-request-id", "x-correlation-id")


class SecurityHeadersMiddleware:
    """Adds baseline security headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (key.lower().encode(), value.encode())
                    for key, value in SECURITY_HEADERS.items()
                ] + list(message.get("headers", []))
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _request_id_from(headers: Mapping[bytes, bytes]) -> str | None:
    for name in _REQUEST_ID_HEADERS:
        value = headers.get(name.encode("ascii"))
        if value:
            return value.decode("ascii", errors="replace")[:64]
    return None


class RequestObservabilityMiddleware:
    """Correlate and log every HTTP request.

    Accepts a client-supplied ``X-Request-Id`` (or ``X-Correlation-Id``), or
    generates one. The id is stored on ``scope["state"]`` so handlers and the
    audit layer can read ``request.state.correlation_id``, and it is echoed on
    the response so a failed request can be traced end to end. Each request is
    logged with its method, path, status, duration and acting user once the
    response has been sent.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        request_id = _request_id_from(headers) or uuid.uuid4().hex
        state = scope.setdefault("state", {})
        state["correlation_id"] = request_id

        started = time.monotonic()
        status_holder: dict[str, int] = {"status": 500}

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message.get("status", 500)
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode("ascii"))
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            status_holder["status"] = 500
            raise
        finally:
            duration_ms = (time.monotonic() - started) * 1000
            try:
                actor_id = state.get("user_id")
                actor = str(actor_id) if actor_id is not None else None
            except Exception:  # noqa: BLE001 - never let logging break the response
                actor = None
            logger.info(
                "http request completed",
                extra={
                    "request_id": request_id,
                    "method": scope.get("method", "?"),
                    "path": scope.get("raw_path", b"?").decode("latin-1", errors="replace"),
                    "status": status_holder["status"],
                    "duration_ms": round(duration_ms, 3),
                    "actor_id": actor,
                },
            )
