"""Unit tests: inference client sanitization and protocol parsing.

Transport is stubbed with httpx.MockTransport — the parsing/sanitizing code
under test is the real client code.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.ai.client import (
    MAX_MESSAGE_CHARS,
    AIClient,
    CompletionResult,
    InferenceProtocolError,
    InferenceUnavailableError,
    _sanitize_messages,
)
from app.core.config import get_settings


class _FakeRuntime:
    """Minimal runtime stand-in exposing what AIClient touches."""

    def __init__(self, handler: Any) -> None:
        self.settings = get_settings()
        self.ready = True
        self.client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://test-inference"
        )
        self.metrics = _Metrics()


class _Metrics:
    def __init__(self) -> None:
        self.requests_total = 0
        self.errors_total = 0
        self.generations_active = 0
        self.last_error: str | None = None
        self.extra: dict[str, Any] = {}


def test_sanitize_drops_unknown_roles() -> None:
    cleaned = _sanitize_messages(
        [
            {"role": "system", "content": "s"},
            {"role": "tool", "content": "t"},
            {"role": "user", "content": "u"},
            {"role": "nonsense", "content": "n"},
        ]
    )
    assert [m["role"] for m in cleaned] == ["system", "user"]


def test_sanitize_truncates_long_content() -> None:
    cleaned = _sanitize_messages([{"role": "user", "content": "x" * (MAX_MESSAGE_CHARS + 500)}])
    assert len(cleaned[0]["content"]) == MAX_MESSAGE_CHARS


def test_sanitize_requires_role_default_empty() -> None:
    cleaned = _sanitize_messages([{"content": "no role here"}])
    assert cleaned == []


def _completion_body(text: str) -> bytes:
    return json.dumps(
        {
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
    ).encode()


async def test_chat_parses_completion_and_counts_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["stream"] is False
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        assert payload["model"] == "local"
        return httpx.Response(200, content=_completion_body("pong"))

    client = AIClient(_FakeRuntime(handler))  # type: ignore[arg-type]
    result = await client.chat([{"role": "user", "content": "ping"}], max_tokens=16)
    assert isinstance(result, CompletionResult)
    assert result.text == "pong"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.duration_ms >= 0


async def test_chat_http_error_raises_protocol_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=b'{"error":{"message":"context size"}}')

    client = AIClient(_FakeRuntime(handler))  # type: ignore[arg-type]
    with pytest.raises(InferenceProtocolError, match="HTTP 400"):
        await client.chat([{"role": "user", "content": "x"}], max_tokens=8)


async def test_chat_malformed_body_raises_protocol_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    client = AIClient(_FakeRuntime(handler))  # type: ignore[arg-type]
    with pytest.raises(InferenceProtocolError):
        await client.chat([{"role": "user", "content": "x"}], max_tokens=8)


async def test_chat_transport_error_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = AIClient(_FakeRuntime(handler))  # type: ignore[arg-type]
    with pytest.raises(InferenceUnavailableError):
        await client.chat([{"role": "user", "content": "x"}], max_tokens=8)


def _sse_body(*texts: str) -> bytes:
    lines = []
    for text in texts:
        chunk = {"choices": [{"delta": {"content": text}}]}
        lines.append(f"data: {json.dumps(chunk)}")
    lines.append("data: [DONE]")
    return ("\n".join(lines) + "\n").encode()


async def test_chat_stream_yields_deltas_in_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        return httpx.Response(200, content=_sse_body("Hel", "lo", "!"))

    client = AIClient(_FakeRuntime(handler))  # type: ignore[arg-type]
    stream = client.chat_stream([{"role": "user", "content": "x"}], max_tokens=8)
    parts = [part async for part in stream]
    assert "".join(parts) == "Hello!"


async def test_chat_stream_skips_malformed_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            b"data: {broken json\n\n"
            b'data: {"choices":[]}\n\n'
            b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body)

    client = AIClient(_FakeRuntime(handler))  # type: ignore[arg-type]
    stream = client.chat_stream([{"role": "user", "content": "x"}], max_tokens=8)
    parts = [part async for part in stream]
    assert parts == ["ok"]


async def test_chat_stream_non_200_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"")

    client = AIClient(_FakeRuntime(handler))  # type: ignore[arg-type]
    with pytest.raises(InferenceProtocolError, match="HTTP 503"):
        async for _ in client.chat_stream([{"role": "user", "content": "x"}], max_tokens=8):
            pass


async def test_not_ready_runtime_rejects_calls() -> None:
    runtime = _FakeRuntime(lambda request: httpx.Response(200))
    runtime.ready = False
    client = AIClient(runtime)  # type: ignore[arg-type]
    with pytest.raises(InferenceUnavailableError, match="not ready"):
        await client.chat([{"role": "user", "content": "x"}], max_tokens=8)
