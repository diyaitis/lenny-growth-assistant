from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import build_orchestrator, get_db
from app.db.models import Artifact, ChatSession, Message
from app.schemas.artifact import ArtifactSummary
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.session import MessageResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, db: AsyncSession = Depends(get_db)):
    session = await db.get(ChatSession, payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found. Create one with POST /sessions first.")

    history_result = await db.execute(
        select(Message).where(Message.session_id == session.id).order_by(Message.created_at)
    )
    history = list(history_result.scalars().all())

    user_message = Message(session_id=session.id, role="user", content=payload.message)
    db.add(user_message)
    await db.flush()

    orchestrator = build_orchestrator(request, db)

    try:
        result = await orchestrator.handle_message(history, payload.message)
    except Exception:
        logger.exception("agent_turn_failed", extra={"session_id": session.id})
        raise HTTPException(
            status_code=502,
            detail="The assistant failed to produce a response. This has been logged; please try again.",
        ) from None

    assistant_message = Message(
        session_id=session.id,
        role="assistant",
        content=result.reply,
        provider=result.provider,
        skill=result.skill.value,
        citations=result.citations,
    )
    db.add(assistant_message)
    await db.flush()

    artifact_out: ArtifactSummary | None = None
    if result.artifact is not None:
        artifact_row = Artifact(
            session_id=session.id,
            message_id=assistant_message.id,
            kind=result.artifact.kind,
            title=result.artifact_title,
            content=result.artifact.sanitized_content,
            raw_content=result.artifact.raw_content,
        )
        db.add(artifact_row)
        await db.flush()
        artifact_out = ArtifactSummary.model_validate(artifact_row)

    await db.commit()
    await db.refresh(assistant_message)

    return ChatResponse(
        message=MessageResponse.model_validate(assistant_message),
        artifact=artifact_out,
        grounded=result.grounded,
        degraded=result.degraded,
    )
