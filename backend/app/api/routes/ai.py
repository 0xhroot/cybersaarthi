"""Routes: local AI assistant (status, conversations, chat, streaming, draft).

Every endpoint authenticates through the shared JWT dependency. Case-scoped
endpoints resolve the case with ``get_case_or_404`` so ownership checks run
before any retrieval or inference. The model never decides access.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.service import AIService
from app.api.dependencies import get_case_or_404, get_current_user
from app.api.errors import ApiHTTPException
from app.core.codes import CODE_AI_CONVERSATION_NOT_FOUND, CODE_AI_MESSAGE_INVALID
from app.db.postgres import get_db_session
from app.models import AIConversation, AIMessage, Case, User
from app.schemas.ai import (
    AiChatRequest,
    AiChatResponse,
    AiConversationListResponse,
    AiConversationOut,
    AiConversationRenameRequest,
    AiMessageListResponse,
    AiMessageOut,
    AiReportDraftRequest,
    AiReportDraftResponse,
    AiSourceOut,
    AiStatusResponse,
    AiToolEventOut,
)

router = APIRouter(prefix="/ai", tags=["ai"])


def _service(request: Request) -> AIService:
    return request.app.state.ai_service


@router.get("/status", response_model=AiStatusResponse)
async def ai_status(
    request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Runtime readiness + feature flags for the current deployment.

    Authenticated: runtime state is operational information, and every AI
    surface in this router requires an authenticated server-side session.
    """
    service = _service(request)
    # Probe live so readiness reflects the inference server's real state,
    # not a stale flag from application startup.
    await service.runtime.ensure_ready()
    snapshot = service.status()
    snapshot.update(await service.runtime.gpu_stats())
    return snapshot


@router.get("/conversations", response_model=AiConversationListResponse)
async def list_conversations(
    request: Request,
    case_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    service = _service(request)
    if case_id is not None:
        await get_case_or_404(case_id, request, session)
    items = await service.list_conversations(session, user, case_id=case_id, limit=limit)
    total = int(
        (
            await session.execute(
                select(func.count(AIConversation.id)).where(AIConversation.user_id == user.id)
            )
        ).scalar_one()
    )
    return AiConversationListResponse(
        items=[AiConversationOut.model_validate(item) for item in items], total=total
    )


@router.post("/conversations", response_model=AiConversationOut, status_code=201)
async def create_conversation(
    request: Request,
    mode: str = Query(default="general", max_length=32),
    case_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    service = _service(request)
    case = await get_case_or_404(case_id, request, session) if case_id else None
    conversation = await service.create_conversation(
        session, user, mode=mode, case_id=case.id if case else None
    )
    await session.commit()
    return AiConversationOut.model_validate(conversation)


@router.get("/conversations/{conversation_id}", response_model=AiMessageListResponse)
async def list_messages(
    request: Request,
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    service = _service(request)
    messages = await service.list_messages(session, user, conversation_id)
    return AiMessageListResponse(
        items=[AiMessageOut.model_validate(message) for message in messages]
    )


@router.patch("/conversations/{conversation_id}", response_model=AiConversationOut)
async def rename_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    payload: AiConversationRenameRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Rename an owned conversation (404 for foreign or unknown ids)."""
    service = _service(request)
    conversation = await service.rename_conversation(
        session, user, conversation_id, payload.title
    )
    await session.commit()
    return AiConversationOut.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    service = _service(request)
    await service.delete_conversation(session, user, conversation_id)
    await session.commit()


@router.post("/chat", response_model=AiChatResponse)
async def chat(
    request: Request,
    payload: AiChatRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """One grounded completion (non-streaming). Case modes enforce ownership."""
    service = _service(request)
    case = await _resolve_case(request, session, payload)
    conversation = await _resolve_conversation(session, user, payload, case)
    if conversation is None:
        conversation = await service.create_conversation(
            session,
            user,
            mode=payload.mode,
            case_id=case.id if case else None,
            title=payload.question[:80],
        )
    outcome = await service.ask(
        request,
        session,
        user,
        question=payload.question,
        mode=payload.mode,
        case=case,
        conversation=conversation,
        profile=payload.profile,
    )
    await session.commit()
    return AiChatResponse(
        answer=outcome.text,
        conversation_id=conversation.id,
        message_id=await _latest_assistant_message_id(session, conversation),
        sources=[AiSourceOut(**source.model_dump()) for source in outcome.sources],
        tool_events=[
            AiToolEventOut(
                tool=event.get("tool", "unknown"),
                ok=bool(event.get("ok")),
                arguments=event.get("arguments") or {},
                error=event.get("error"),
                status=event.get("status"),
                duration_ms=event.get("duration_ms"),
            )
            for event in outcome.tool_events
        ],
        grounded=outcome.grounded,
        prompt_version="1.0.0",
        duration_ms=outcome.duration_ms,
        first_token_ms=outcome.first_token_ms,
        prompt_tokens=outcome.prompt_tokens,
        completion_tokens=outcome.completion_tokens,
    )


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    payload: AiChatRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Server-sent events stream: sources | tool | token | done | error."""
    service = _service(request)
    case = await _resolve_case(request, session, payload)
    conversation = await _resolve_conversation(session, user, payload, case)

    async def event_gen() -> AsyncIterator[str]:
        async for event in service.ask_stream(
            request,
            session,
            user,
            question=payload.question,
            mode=payload.mode,
            case=case,
            conversation=conversation,
            profile=payload.profile,
        ):
            yield f"data: {json.dumps(event, default=str)}\n\n"
        try:
            await session.commit()
        except Exception:  # noqa: BLE001 - stream already delivered
            await session.rollback()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/report-draft", response_model=AiReportDraftResponse)
async def report_draft(
    request: Request,
    payload: AiReportDraftRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Draft proposal for a report section — human review required."""
    service = _service(request)
    case = await get_case_or_404(payload.case_id, request, session)
    outcome = await service.draft_report(request, session, user, case)
    await session.commit()
    return AiReportDraftResponse(
        draft=outcome.text,
        sources=[AiSourceOut(**source.model_dump()) for source in outcome.sources],
        grounded=outcome.grounded,
        prompt_version="1.0.0",
        duration_ms=outcome.duration_ms,
    )


# -- helpers -------------------------------------------------------------


async def _resolve_case(
    request: Request, session: AsyncSession, payload: AiChatRequest
) -> Case | None:
    if payload.case_id is None:
        return None
    return await get_case_or_404(payload.case_id, request, session)


async def _resolve_conversation(
    session: AsyncSession,
    user: User,
    payload: AiChatRequest,
    case: Case | None,
) -> AIConversation | None:
    if payload.conversation_id is None:
        return None
    conversation = await session.get(AIConversation, payload.conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise ApiHTTPException(404, CODE_AI_CONVERSATION_NOT_FOUND, "conversation not found")
    if case is not None and conversation.case_id is not None and conversation.case_id != case.id:
        raise ApiHTTPException(400, CODE_AI_MESSAGE_INVALID, "conversation belongs to another case")
    return conversation


async def _latest_assistant_message_id(
    session: AsyncSession, conversation: AIConversation | None
) -> uuid.UUID | None:
    if conversation is None:
        return None
    return (
        await session.execute(
            select(AIMessage.id)
            .where(AIMessage.conversation_id == conversation.id, AIMessage.role == "assistant")
            .order_by(AIMessage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
