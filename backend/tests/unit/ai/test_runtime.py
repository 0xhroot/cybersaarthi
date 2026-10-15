"""Unit tests: runtime validation and status snapshot."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.ai.runtime import (
    GGUF_MAGIC,
    InferenceRuntime,
    ModelValidationError,
    RuntimeMetrics,
    validate_gguf,
)
from app.core.config import get_settings


def test_validate_gguf_accepts_magic_and_size(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(GGUF_MAGIC + b"\x00" * 2_000_000)
    validate_gguf(model)  # no raise


def test_validate_gguf_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ModelValidationError, match="not found"):
        validate_gguf(tmp_path / "nope.gguf")


def test_validate_gguf_truncated(tmp_path: Path) -> None:
    model = tmp_path / "small.gguf"
    model.write_bytes(GGUF_MAGIC + b"\x00" * 10)
    with pytest.raises(ModelValidationError, match="truncated"):
        validate_gguf(model)


def test_validate_gguf_wrong_magic(tmp_path: Path) -> None:
    model = tmp_path / "fake.gguf"
    model.write_bytes(b"PK\x03\x04" + b"\x00" * 2_000_000)
    with pytest.raises(ModelValidationError, match="not a GGUF"):
        validate_gguf(model)


def test_snapshot_never_leaks_full_model_path() -> None:
    settings = get_settings()
    runtime = InferenceRuntime(settings)
    snapshot = runtime.snapshot()
    assert snapshot["model_configured"].endswith(".gguf")
    assert "/" not in snapshot["model_configured"]
    assert "api_key" not in str(snapshot).lower()
    assert "socket" not in str(snapshot).lower()


def test_snapshot_reports_flags_and_counters() -> None:
    settings = get_settings()
    runtime = InferenceRuntime(settings)
    snapshot = runtime.snapshot()
    assert snapshot["enabled"] is True
    assert snapshot["ready"] is False
    assert snapshot["managed"] is settings.AI_MANAGE_SERVER
    assert snapshot["requests_total"] == 0
    assert snapshot["restarts"] == 0


def test_metrics_defaults() -> None:
    metrics = RuntimeMetrics()
    assert metrics.requests_total == 0
    assert metrics.errors_total == 0
    assert metrics.restarts == 0
    assert metrics.last_error is None


def test_disabled_runtime_is_not_ready(tmp_path: Path) -> None:
    settings = get_settings().model_copy(update={"AI_ENABLED": False})
    runtime = InferenceRuntime(settings)
    assert runtime.enabled is False
    assert runtime.ready is False
    snapshot = runtime.snapshot()
    assert snapshot["enabled"] is False


def test_base_url_composition() -> None:
    settings = get_settings()
    runtime = InferenceRuntime(settings)
    assert runtime.base_url == f"http://{settings.AI_SERVER_HOST}:{settings.AI_SERVER_PORT}"


async def test_ensure_ready_disabled_returns_false() -> None:
    settings = get_settings().model_copy(update={"AI_ENABLED": False})
    runtime = InferenceRuntime(settings)
    assert await runtime.ensure_ready() is False
