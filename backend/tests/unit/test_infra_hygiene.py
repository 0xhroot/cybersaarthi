"""Regression guards for infra findings (A13, I01, C02, F11, dev-runtime split)."""

import os
from pathlib import Path


def _repo_root() -> Path:
    """Locate the repository root for this test file.

    Resolution order:
      1. CYBERSAARTHI_REPO_ROOT env var (set by the dev container, which mounts
         the live repository read-only at /repo).
      2. Walk up from this test file until a directory holding the repo marker
         (docker-compose.yml + backend/ + frontend/) is found (local & CI runs).

    This keeps the tests executing against the *actual* repository files whether
    pytest runs locally, inside backend-dev, via `make test`, or in CI.
    """
    override = os.environ.get("CYBERSAARTHI_REPO_ROOT")
    if override:
        return Path(override).resolve()

    for parent in Path(__file__).resolve().parents:
        if (
            (parent / "docker-compose.yml").is_file()
            and (parent / "backend").is_dir()
            and (parent / "frontend").is_dir()
        ):
            return parent

    raise RuntimeError("Could not locate repository root from " + str(Path(__file__).resolve()))


REPO_ROOT = _repo_root()
COMPOSE = REPO_ROOT / "docker-compose.yml"
DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
MAKEFILE = REPO_ROOT / "Makefile"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
README = REPO_ROOT / "README.md"
DESIGN_SYSTEM = REPO_ROOT / "frontend" / "docs" / "design-system.md"


def test_dockerfile_excludes_dev_tools_for_production(A13_fix=True):
    """A13: the production image must not install dev/tooling extras."""
    text = DOCKERFILE.read_text()
    assert ".[dev]" not in text, "production image ships dev extras (pytest/ruff/mypy/httpx)"


def test_compose_pins_minio_image_tags(I01_fix=True):
    """I01: MinIO images must be pinned to a release, not floating `latest`."""
    text = COMPOSE.read_text()
    assert "minio/minio:latest" not in text
    assert "minio/mc:latest" not in text
    assert "RELEASE." in text


LONG_RUNNING_SERVICES = {"backend", "postgres", "neo4j", "redis", "minio"}


def test_compose_sets_memory_and_cpu_limits_for_every_service(I01_fix=True):
    """I01: every long-running service declares resource limits and ulimits for DBs."""
    text = COMPOSE.read_text()
    for service in LONG_RUNNING_SERVICES:
        block = text.split(f"\n  {service}:\n", 1)[-1].split("\n\n", 1)[0]
        assert "deploy:" in block, f"{service} missing deploy.resources limit"
        assert "limits:" in block, f"{service} missing limits"
        assert "memory:" in block, f"{service} missing memory limit"
        assert "cpus:" in block, f"{service} missing cpu limit"


def test_neo4j_postgres_minio_ulimits_declared(I01_fix=True):
    """I01: filesystem-hungry services set an explicit nofile ulimit."""
    text = COMPOSE.read_text()
    for service in ("neo4j", "postgres", "minio", "backend"):
        block = text.split(f"\n  {service}:\n", 1)[-1].split("\n\n", 1)[0]
        assert "ulimits:" in block, f"{service} missing ulimits block"
        assert "nofile:" in block, f"{service} missing nofile ulimit"


def test_readme_no_longer_calls_frontend_a_placeholder(C02_fix=True):
    """C02: README must reflect the real shipped frontend, not an empty placeholder."""
    text = README.read_text()
    assert "empty placeholder" not in text
    assert "Vite + React 19 UI" in text


def test_design_system_drops_dead_components_and_fixes_hex_claim(F11_C03_fix=True):
    """F11/C03: doc no longer advertises removed components nor a false no-hex rule."""
    text = DESIGN_SYSTEM.read_text()
    for dead in ("`tabs`", "`switch`", "--z-sticky", "--z-tooltip", "--z-dropdown"):
        assert dead not in text, f"design-system.md still mentions removed/absent token: {dead}"
    assert "cyto-graph.tsx" in text
    assert "no raw hex values in JSX" not in text


def test_frontend_dead_switch_tabs_components_removed(F11_fix=True):
    """F11: the unused UI primitives must not exist in the source tree."""
    assert not (REPO_ROOT / "frontend/src/components/ui/switch.tsx").exists()
    assert not (REPO_ROOT / "frontend/src/components/ui/tabs.tsx").exists()


def test_dockerfile_has_separate_runtime_and_dev_targets():
    """The prod image must stay lean; dev tools must live in a dedicated stage."""
    text = DOCKERFILE.read_text()
    assert "AS runtime" in text
    assert "AS dev" in text
    # The runtime stage installs runtime deps only and never the dev extra.
    # (Uses a plain editable install - `--only main` is not a real pip flag and
    # is intentionally omitted; extras are excluded by default.)
    runtime_block = text.split("FROM base AS runtime", 1)[1].split("FROM base AS dev", 1)[0]
    assert "pip install" in runtime_block
    assert ".[dev]" not in runtime_block
    assert "pytest" not in runtime_block
    assert "ruff" not in runtime_block
    assert "mypy" not in runtime_block
    # The dev stage is the only place dev tooling is installed (via uv + lock).
    dev_block = text.split("FROM base AS dev", 1)[1]
    assert "uv sync" in dev_block
    assert "--all-extras" in dev_block


def test_compose_defines_backend_dev_service_building_the_dev_target():
    """`make test|lint|format-check|typecheck` must run in a dev container (not prod)."""
    text = COMPOSE.read_text()
    assert "backend-dev:" in text
    assert "target: dev" in text
    assert 'profiles: ["dev"]' in text


def test_makefile_dev_var_targets_backend_dev_and_exec_used_for_tools():
    """The `DEV` runner must target backend-dev; the prod backend must not run dev tools."""
    text = MAKEFILE.read_text()
    assert "DEV := $(COMPOSE) run --rm -T backend-dev" in text
    for target in ("test:", "lint:", "format:", "format-check:", "typecheck:"):
        body = text.split(target, 1)[1].split("\n", 1)[1]
        assert "$(DEV)" in body, f"target {target} must use the $(DEV) runner"


def test_ci_uses_uv_lockfile_for_dev_dependencies():
    """CI must install dev deps deterministically from uv.lock (same as dev image)."""
    ci = CI.read_text()
    assert "uv sync --frozen" in ci
    assert "astral-sh/setup-uv" in ci
