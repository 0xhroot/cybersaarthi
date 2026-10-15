"""Live integration tests: real llama.cpp inference through the AI gateway.

Unlike `tests/api/test_ai_api.py` (which stubs the HTTP client to the model),
these tests exercise the **real** local inference server end-to-end: the actual
`AIService`, the real OpenAI-compatible client, real retrieval and the real SSE
stream. They are marked `integration` and skip cleanly when the model runtime
is not running, so the default suite stays hermetic.

They deliberately run the runtime in *external* mode (``AI_MANAGE_SERVER`` is
forced off) so importing them can never spawn a second llama-server.

Run with the server up:

    ./scripts/ai/run_server.sh &          # or scripts/ai/socket_bridge.sh
    pytest -m integration tests/integration/test_ai_live.py -q
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest
from app.ai.client import AIClient
from app.ai.service import AIService
from app.core.auth import create_access_token
from app.core.config import Settings, get_settings
from app.db.neo4j import GraphStore
from app.db.postgres import Database
from app.db.redis import Cache
from app.db.storage import Storage
from app.main import app
from app.models import AIConversation, AIMessage, Case, CaseMember, User
from app.repositories.user_repository import UserRepository
from app.services.users import UserService
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

pytestmark = pytest.mark.integration


def _live_settings() -> Settings:
    """Settings for talking to the host-run server from the test process.

    The test venv does not load the repository-root ``.env``, so the API key is
    read from there when it is not already in the environment. Managed mode is
    forced off: tests must attach to the running server, never spawn one.
    """
    settings = get_settings()
    key = settings.AI_SERVER_API_KEY
    if not key:
        env_file = Path(settings.repo_root) / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("AI_SERVER_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        pytest.skip(
            "AI_SERVER_API_KEY not available (set it in the environment or "
            "repository-root .env; see docs/ai/LOCAL_MODEL_SETUP.md)"
        )
    return settings.model_copy(
        update={"AI_SERVER_API_KEY": key, "AI_MANAGE_SERVER": False}
    )


async def _server_reachable(settings: Settings) -> bool:
    """Probe /health on the live server directly - never starts anything."""
    timeout = httpx.Timeout(5.0)
    try:
        if settings.AI_SERVER_SOCKET:
            client = httpx.AsyncClient(
                base_url="http://localhost",
                transport=httpx.AsyncHTTPTransport(uds=settings.AI_SERVER_SOCKET),
                timeout=timeout,
            )
        else:
            client = httpx.AsyncClient(base_url=settings.ai_base_url, timeout=timeout)
        async with client:
            response = await client.get("/health")
            return response.status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture
async def live_env(
    database: Database,
    graph_store: GraphStore,
    cache: Cache,
    storage: Storage,
    settings: Settings,
):
    """Two real users (owner + outsider), one owned case, real AIService.

    ASGITransport never runs the lifespan, so the infrastructure clients and
    the AI service are wired onto ``app.state`` explicitly (as the API suite
    does). Skips entirely when the inference server is not running.
    """
    app.state.database = database
    app.state.graph_store = graph_store
    app.state.cache = cache
    app.state.storage = storage
    app.state.settings = settings

    live = _live_settings()
    if not await _server_reachable(live):
        pytest.skip(
            "local inference server not reachable - start it with "
            "`./scripts/ai/run_server.sh` (see docs/ai/LOCAL_MODEL_SETUP.md)"
        )

    # Real service in external mode: builds the HTTP client and probes health,
    # never spawns a child process.
    service = AIService(live)
    await service.start()
    if not service.runtime.ready:
        await service.stop()
        pytest.fail(
            "inference server answered /health but the AI runtime is not ready: "
            f"{service.runtime.metrics.last_error or 'unknown error'}"
        )

    factory = database.session_factory()
    created: list[uuid.UUID] = []

    async def _make_user(role: str) -> tuple[uuid.UUID, str]:
        username = f"liv{role.lower()[:3]}-{uuid.uuid4().hex[:8]}"
        async with factory() as session:
            user_service = UserService(UserRepository(session))
            user = await user_service.create_user_with_role(
                username=username,
                email=f"{username}@cybersaarthi.test",
                password="live-integration-pw-1",
                role=role,
            )
            await session.commit()
            user_id = user.id
        created.append(user_id)
        token = create_access_token(
            user_id,
            secret=settings.SECRET_KEY,
            expires_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )
        return user_id, token

    owner_id, owner_token = await _make_user("INVESTIGATOR")
    _, outsider_token = await _make_user("INVESTIGATOR")

    # Ownership alone grants access (assert_case_access); no CaseMember row is
    # needed for the owner, and the outsider deliberately has none.
    case_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            Case(
                id=case_id,
                case_number=f"LIVE-{uuid.uuid4().hex[:8]}",
                title="live integration case (synthetic)",
                description="A synthetic case used only by live AI integration tests.",
                status="open",
                owner_id=owner_id,
            )
        )
        await session.commit()

    app.state.ai_service = service

    yield {
        "service": service,
        "owner_token": owner_token,
        "outsider_token": outsider_token,
        "case_id": str(case_id),
        "prefix": settings.API_V1_PREFIX,
    }

    del app.state.ai_service
    await service.stop()
    async with factory() as session:
        await session.execute(delete(AIMessage).where(AIMessage.case_id == case_id))
        await session.execute(
            delete(AIConversation).where(AIConversation.case_id == case_id)
        )
        await session.execute(delete(CaseMember).where(CaseMember.case_id == case_id))
        await session.execute(delete(Case).where(Case.id == case_id))
        for user_id in created:
            await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


def _client(token: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://liveserver",
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_real_completion_roundtrip(live_env) -> None:
    """A real completion flows through the gateway and returns real content."""
    prefix = live_env["prefix"]
    async with _client(live_env["owner_token"]) as client:
        resp = await client.post(
            f"{prefix}/ai/chat",
            json={"question": "Reply with exactly: pong"},
            timeout=180,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"].strip(), "real completion must return non-empty content"
    assert "pong" in body["answer"].lower()
    assert body["conversation_id"]


async def test_real_grounded_case_chat_cites_sources(live_env) -> None:
    """A case-scoped question returns grounded, real retrieval sources."""
    prefix = live_env["prefix"]
    async with _client(live_env["owner_token"]) as client:
        resp = await client.post(
            f"{prefix}/ai/chat",
            json={
                "question": "Summarize this case in one sentence and cite what you used.",
                "mode": "case",
                "case_id": live_env["case_id"],
            },
            timeout=300,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"].strip()
    assert body["sources"], "grounded case chat must attach real sources"
    assert body["grounded"] is True
    labels = " ".join(json.dumps(s) for s in body["sources"])
    assert live_env["case_id"] in labels or "case" in labels.lower()


async def test_real_stream_emits_tokens_then_done(live_env) -> None:
    """The live SSE stream carries real token events and a done frame."""
    prefix = live_env["prefix"]
    events: list[dict] = []
    async with _client(live_env["owner_token"]) as client:
        async with client.stream(
            "POST",
            f"{prefix}/ai/chat/stream",
            json={"question": "Count from 1 to 5, one number per line."},
            timeout=300,
        ) as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[len("data: "):]))
    types = [e["type"] for e in events]
    assert "token" in types, f"expected real token events, got {types}"
    assert types[-1] == "done", f"stream must end with done, got {types}"
    done = events[-1]
    assert done["answer"].strip()
    assert done["conversation_id"]


async def test_real_outsider_denied_case_chat(live_env) -> None:
    """Live isolation: a non-member gets 403 and the model is never consulted."""
    prefix = live_env["prefix"]
    async with _client(live_env["outsider_token"]) as client:
        resp = await client.post(
            f"{prefix}/ai/chat",
            json={
                "question": "What is in this case?",
                "mode": "case",
                "case_id": live_env["case_id"],
            },
            timeout=120,
        )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CASE_ACCESS_DENIED"


async def test_real_foreign_conversation_is_404(live_env) -> None:
    """Live isolation: the outsider cannot read or rename the owner's thread."""
    prefix = live_env["prefix"]
    async with _client(live_env["owner_token"]) as client:
        created = await client.post(
            f"{prefix}/ai/chat",
            json={"question": "Private thread for isolation check."},
            timeout=180,
        )
    assert created.status_code == 200, created.text
    conv_id = created.json()["conversation_id"]
    async with _client(live_env["outsider_token"]) as client:
        read = await client.get(f"{prefix}/ai/conversations/{conv_id}")
        rename = await client.patch(
            f"{prefix}/ai/conversations/{conv_id}", json={"title": "hijack"}
        )
    assert read.status_code == 404
    assert rename.status_code == 404


async def test_real_owner_messages_are_stored_on_their_thread(
    live_env, database: Database
) -> None:
    """Persistence: the owner's thread holds both user and assistant messages."""
    prefix = live_env["prefix"]
    async with _client(live_env["owner_token"]) as client:
        created = await client.post(
            f"{prefix}/ai/chat",
            json={"question": "Say OK and nothing else."},
            timeout=180,
        )
    assert created.status_code == 200, created.text
    conv_id = uuid.UUID(created.json()["conversation_id"])

    factory = database.session_factory()
    async with factory() as session:
        rows = (
            await session.execute(select(AIMessage).where(AIMessage.conversation_id == conv_id))
        ).scalars().all()
    assert len(rows) >= 2, "user + assistant messages must be persisted"
    assert {row.role for row in rows} == {"user", "assistant"}


async def test_client_requires_api_key(live_env) -> None:
    """The inference client always authenticates to the model server."""
    client = AIClient(live_env["service"].runtime)
    headers = client._headers()  # noqa: SLF001 - asserting the auth contract
    assert headers.get("Authorization", "").startswith("Bearer ")
    assert len(headers["Authorization"]) > len("Bearer ")
