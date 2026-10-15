"""Async client for the local llama.cpp OpenAI-compatible inference server.

Only ever pointed at a localhost URL configured by the backend — the browser
has no access to this client. Streaming completions are exposed as async
generators so callers can forward tokens to SSE and honour task cancellation
(close the response, stop paying for tokens).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.ai.runtime import InferenceRuntime

logger = logging.getLogger(__name__)

# Safety cap on any single completion request we forward.
MAX_PROMPT_CHARS = 24_000
MAX_MESSAGE_CHARS = 8_000


class InferenceUnavailableError(RuntimeError):
    """The local inference server is not ready or unreachable."""


class InferenceProtocolError(RuntimeError):
    """The server returned something that is not an OpenAI-style completion."""


@dataclass(slots=True)
class CompletionResult:
    """A non-streaming completion result."""

    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int = 0
    first_token_ms: int | None = None


@dataclass(slots=True)
class StreamStats:
    """Accumulated metrics for one streaming completion."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int = 0
    first_token_ms: int | None = None
    text_parts: list[str] = field(default_factory=list)


def _sanitize_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Enforce role/length caps before anything reaches the model."""
    cleaned: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role", "")
        if role not in {"system", "user", "assistant"}:
            continue
        content = str(message.get("content", ""))[:MAX_MESSAGE_CHARS]
        cleaned.append({"role": role, "content": content})
    return cleaned


class AIClient:
    """OpenAI-compatible chat client bound to the supervised runtime."""

    def __init__(self, runtime: InferenceRuntime) -> None:
        self._runtime = runtime

    def _headers(self) -> dict[str, str]:
        key = self._runtime.settings.AI_SERVER_API_KEY
        return {"Authorization": f"Bearer {key}"} if key else {}

    def _require_client(self) -> httpx.AsyncClient:
        if not self._runtime.ready or self._runtime.client is None:
            raise InferenceUnavailableError("local inference server is not ready")
        return self._runtime.client

    def _request_timeout(self) -> httpx.Timeout:
        """Configured budget: connections fail fast, reads allow one full generation."""
        total = float(self._runtime.settings.AI_REQUEST_TIMEOUT_SECONDS)
        return httpx.Timeout(connect=5.0, read=total, write=10.0, pool=5.0)

    async def health(self) -> bool:
        return await self._runtime.ensure_ready()

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float = 0.2,
        stop: list[str] | None = None,
    ) -> CompletionResult:
        """One non-streaming completion (tool-loop inner calls use this)."""
        client = self._require_client()
        payload: dict[str, Any] = {
            "model": "local",
            "messages": _sanitize_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            # Qwen3 ships a thinking chat template; the assistant answers
            # faster and stays inside the small context budget with it off.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if stop:
            payload["stop"] = stop[:4]
        started = time.monotonic()
        self._runtime.metrics.requests_total += 1
        self._runtime.metrics.generations_active += 1
        try:
            response = await client.post(
                "/v1/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self._request_timeout(),
            )
        except httpx.HTTPError as exc:
            self._runtime.metrics.errors_total += 1
            self._runtime.metrics.last_error = str(exc)[:200]
            raise InferenceUnavailableError(f"inference request failed: {exc}") from exc
        finally:
            self._runtime.metrics.generations_active -= 1
        duration_ms = int((time.monotonic() - started) * 1000)
        if response.status_code != 200:
            self._runtime.metrics.errors_total += 1
            self._runtime.metrics.last_error = f"HTTP {response.status_code}"
            logger.warning(
                "completion failed: HTTP %s body=%s",
                response.status_code,
                response.text[:300],
            )
            raise InferenceProtocolError(f"completion failed: HTTP {response.status_code}")
        try:
            data = response.json()
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
        except (ValueError, KeyError, IndexError) as exc:
            self._runtime.metrics.errors_total += 1
            raise InferenceProtocolError("malformed completion response") from exc
        usage = data.get("usage") or {}
        return CompletionResult(
            text=text,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            duration_ms=duration_ms,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float = 0.2,
        stop: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Stream assistant text deltas; raises InferenceUnavailable/Protocol."""
        client = self._require_client()
        payload: dict[str, Any] = {
            "model": "local",
            "messages": _sanitize_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if stop:
            payload["stop"] = stop[:4]
        started = time.monotonic()
        self._runtime.metrics.requests_total += 1
        self._runtime.metrics.generations_active += 1
        emitted = 0
        try:
            async with client.stream(
                "POST",
                "/v1/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self._request_timeout(),
            ) as response:
                if response.status_code != 200:
                    self._runtime.metrics.errors_total += 1
                    self._runtime.metrics.last_error = f"HTTP {response.status_code}"
                    raise InferenceProtocolError(f"completion failed: HTTP {response.status_code}")
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:") :].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except ValueError:
                        logger.debug("skipping malformed SSE chunk")
                        continue
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content")
                    if text:
                        emitted += 1
                        yield text
        except httpx.HTTPError as exc:
            self._runtime.metrics.errors_total += 1
            self._runtime.metrics.last_error = str(exc)[:200]
            raise InferenceUnavailableError(f"inference stream failed: {exc}") from exc
        finally:
            self._runtime.metrics.generations_active -= 1
            duration_ms = int((time.monotonic() - started) * 1000)
            if emitted:
                # rough tokens/s estimate for observability only
                self._runtime.metrics.extra["last_stream_tokens"] = emitted
                self._runtime.metrics.extra["last_stream_ms"] = duration_ms
