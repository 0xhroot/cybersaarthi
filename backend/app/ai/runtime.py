"""Supervision of the local llama.cpp inference server.

One shared ``llama-server`` process serves every AI feature. It is bound to
localhost, never exposed publicly, and can either be managed by the FastAPI
lifespan (``AI_MANAGE_SERVER=true``) or started out-of-band via
``scripts/ai/run_server.sh``. Health, readiness and coarse metrics live here;
request-level metrics are recorded by the service layer.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

GGUF_MAGIC = b"GGUF"


@dataclass(slots=True)
class RuntimeMetrics:
    """Coarse process/runtime observability (no secrets, no paths)."""

    started_at: float | None = None
    load_seconds: float | None = None
    healthy_since: float | None = None
    restarts: int = 0
    requests_total: int = 0
    errors_total: int = 0
    generations_active: int = 0
    last_error: str | None = None
    last_request_ms: int | None = None
    request_ms_total: int = 0
    request_ms_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class ModelValidationError(RuntimeError):
    """The configured GGUF file is missing or not a GGUF artifact."""


def validate_gguf(path: Path) -> None:
    """Cheap on-disk sanity check before the server ever loads the model."""
    if not path.is_file():
        raise ModelValidationError(f"model file not found: {path.name}")
    if path.stat().st_size < 1_000_000:
        raise ModelValidationError(f"model file looks truncated: {path.name}")
    with path.open("rb") as fh:
        magic = fh.read(4)
    if magic != GGUF_MAGIC:
        raise ModelValidationError(f"not a GGUF file: {path.name}")


class InferenceRuntime:
    """Owns the llama-server child process (optional) and its health state."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._process: asyncio.subprocess.Process | None = None
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._ready = False
        self.metrics = RuntimeMetrics()
        self._stderr_task: asyncio.Task[None] | None = None
        self._gpu_cache: dict[str, Any] | None = None
        self._gpu_cache_at: float = 0.0

    GPU_CACHE_TTL_SECONDS = 10.0

    @property
    def settings(self) -> Settings:
        return self._settings

    # -- state -----------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._settings.AI_ENABLED

    @property
    def ready(self) -> bool:
        return self.enabled and self._ready

    @property
    def base_url(self) -> str:
        return self._settings.ai_base_url

    def _headers(self) -> dict[str, str]:
        key = self._settings.AI_SERVER_API_KEY
        return {"Authorization": f"Bearer {key}"} if key else {}

    def _build_client(self) -> httpx.AsyncClient:
        """HTTP client over TCP or the Unix socket bridge, whichever is set."""
        settings = self._settings
        timeout = httpx.Timeout(5.0, read=30.0)
        if settings.AI_SERVER_SOCKET:
            return httpx.AsyncClient(
                base_url="http://localhost",
                transport=httpx.AsyncHTTPTransport(uds=settings.AI_SERVER_SOCKET),
                timeout=timeout,
            )
        return httpx.AsyncClient(base_url=settings.ai_base_url, timeout=timeout)

    def snapshot(self) -> dict[str, Any]:
        """Status payload safe for authenticated status endpoints."""
        s = self._settings
        return {
            "enabled": self.enabled,
            "ready": self.ready,
            "managed": s.AI_MANAGE_SERVER,
            "model_configured": s.AI_MODEL_PATH.split("/")[-1],
            "model_valid": s.ai_model_file.is_file(),
            "context_length": s.AI_CONTEXT_LENGTH,
            "max_output_tokens": s.AI_MAX_OUTPUT_TOKENS,
            "gpu_layers": s.AI_GPU_LAYERS,
            "started": self.metrics.started_at is not None,
            "load_seconds": self.metrics.load_seconds,
            "restarts": self.metrics.restarts,
            "requests_total": self.metrics.requests_total,
            "errors_total": self.metrics.errors_total,
            "generations_active": self.metrics.generations_active,
            "last_error": self.metrics.last_error,
            "last_request_ms": self.metrics.last_request_ms,
            "avg_request_ms": (
                round(self.metrics.request_ms_total / self.metrics.request_ms_count)
                if self.metrics.request_ms_count
                else None
            ),
            "prompt_version": None,  # filled by the service layer
        }

    def record_request(self, duration_ms: int) -> None:
        """Track per-request latency for the status endpoint."""
        self.metrics.last_request_ms = int(duration_ms)
        self.metrics.request_ms_total += int(duration_ms)
        self.metrics.request_ms_count += 1

    async def gpu_stats(self) -> dict[str, Any]:
        """VRAM/utilization via ``nvidia-smi`` when available (briefly cached).

        Returns an empty dict on machines without the NVIDIA tooling so the
        status endpoint degrades to nulls instead of failing.
        """
        now = time.monotonic()
        if self._gpu_cache is not None and (now - self._gpu_cache_at) < self.GPU_CACHE_TTL_SECONDS:
            return self._gpu_cache
        stats: dict[str, Any] = {}
        exe = shutil.which("nvidia-smi")
        if exe:
            try:
                proc = await asyncio.create_subprocess_exec(
                    exe,
                    "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                    "--format=csv,noheader,nounits",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
                if proc.returncode == 0:
                    parts = [part.strip() for part in out.decode().splitlines()[0].split(",")]
                    if len(parts) >= 4:
                        stats = {
                            "gpu_name": parts[0],
                            "vram_used_mb": int(parts[1]),
                            "vram_total_mb": int(parts[2]),
                            "gpu_util_percent": int(parts[3]),
                        }
            except (OSError, TimeoutError, ValueError):
                stats = {}
        self._gpu_cache = stats
        self._gpu_cache_at = now
        return stats

    # -- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        """Validate the model, start the server if managed, wait for health."""
        if not self.enabled:
            logger.info("AI disabled; inference runtime not started")
            return
        settings = self._settings
        try:
            validate_gguf(settings.ai_model_file)
        except ModelValidationError as exc:
            self.metrics.last_error = str(exc)
            logger.error("AI runtime unavailable: %s", exc)
            return

        self._client = self._build_client()
        if settings.AI_MANAGE_SERVER:
            await self._spawn_server()
            # Managed mode: block startup until the child is healthy so the
            # first request is served immediately.
            await self._wait_ready(deadline_seconds=300.0)
        else:
            # External mode (e.g. host-process inference behind Docker):
            # probe once, never block API startup on the model server.
            await self.ensure_ready()

    async def stop(self) -> None:
        """Graceful shutdown: terminate the child and close the HTTP client."""
        if self._process is not None and self._process.returncode is None:
            try:
                self._process.send_signal(signal.SIGTERM)
                await asyncio.wait_for(self._process.wait(), timeout=15.0)
            except (TimeoutError, ProcessLookupError):
                self._process.kill()
                await self._process.wait()
        self._process = None
        self._ready = False
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _spawn_server(self) -> None:
        settings = self._settings
        binary = settings.ai_server_binary_file
        if not binary.is_file():
            self.metrics.last_error = "inference binary missing (run scripts/ai/setup_runtime.sh)"
            logger.error("llama-server binary not found at %s", binary)
            return
        cmd = [
            str(binary),
            "--model",
            str(settings.ai_model_file),
            "--host",
            settings.AI_SERVER_HOST,
            "--port",
            str(settings.AI_SERVER_PORT),
            "--ctx-size",
            str(settings.AI_CONTEXT_LENGTH),
            "--parallel",
            str(max(1, settings.AI_MAX_CONCURRENT_GENERATIONS)),
            "--no-webui",
            "--jinja",
        ]
        if settings.AI_SERVER_API_KEY:
            cmd += ["--api-key", settings.AI_SERVER_API_KEY]
        if settings.AI_GPU_LAYERS != 0:
            cmd += ["--n-gpu-layers", str(settings.AI_GPU_LAYERS)]
        logger.info(
            "starting llama-server on %s:%s (gpu_layers=%s, ctx=%s)",
            settings.AI_SERVER_HOST,
            settings.AI_SERVER_PORT,
            settings.AI_GPU_LAYERS,
            settings.AI_CONTEXT_LENGTH,
        )
        # Prefer the CUDA 12.x runtime libs bundled next to the prebuilt
        # binary so inference works even when the system CUDA is newer.
        child_env = {
            **os.environ,
            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES", "0"),
        }
        lib_dir = binary.parent
        if lib_dir.is_dir():
            existing = child_env.get("LD_LIBRARY_PATH", "")
            child_env["LD_LIBRARY_PATH"] = f"{lib_dir}{':' + existing if existing else ''}"
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(settings.repo_root),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=child_env,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        self.metrics.started_at = time.time()
        self.metrics.restarts += 1

    async def _drain_stderr(self) -> None:
        """Keep the child's pipe from filling; log warnings, retain last error."""
        assert self._process is not None and self._process.stderr is not None
        while True:
            line = await self._process.stderr.readline()
            if not line:
                return
            text = line.decode(errors="replace").rstrip()
            low = text.lower()
            if "error" in low or "failed" in low:
                self.metrics.last_error = text[:300]
                logger.warning("llama-server: %s", text[:300])
            else:
                logger.debug("llama-server: %s", text[:300])

    async def _wait_ready(self, *, deadline_seconds: float) -> None:
        assert self._client is not None
        deadline = time.monotonic() + deadline_seconds
        boot_started = time.monotonic()
        while time.monotonic() < deadline:
            if self._process is not None and self._process.returncode is not None:
                self.metrics.last_error = self.metrics.last_error or "inference server exited"
                logger.error("llama-server exited with code %s", self._process.returncode)
                return
            try:
                response = await self._client.get("/health", headers=self._headers())
                if response.status_code == 200:
                    self._ready = True
                    self.metrics.healthy_since = time.time()
                    if self.metrics.load_seconds is None:
                        self.metrics.load_seconds = round(time.monotonic() - boot_started, 2)
                    logger.info("llama-server ready in %.1fs", self.metrics.load_seconds or 0)
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1.0)
        self.metrics.last_error = "inference server failed to become ready before timeout"
        logger.error("llama-server did not become ready in %.0fs", deadline_seconds)

    async def ensure_ready(self) -> bool:
        """Re-check health (external servers may restart independently)."""
        if not self.enabled or self._client is None:
            return False
        try:
            response = await self._client.get("/health", headers=self._headers())
            self._ready = response.status_code == 200
        except httpx.HTTPError:
            self._ready = False
        return self._ready

    @property
    def client(self) -> httpx.AsyncClient | None:
        return self._client
