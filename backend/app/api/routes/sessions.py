from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models import Artifact, ChatSession, Message
from app.schemas.artifact import ArtifactSummary
from app.schemas.session import MessageResponse, SessionCreateRequest, SessionResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(payload: SessionCreateRequest, db: AsyncSession = Depends(get_db)):
    session = ChatSession(title=payload.title, user_label=payload.user_label)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("", response_model=list[SessionResponse])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(100))
    return result.scalars().all()


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def get_session_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    result = await db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.created_at))
    return result.scalars().all()


@router.get("/{session_id}/artifacts/latest", response_model=ArtifactSummary)
async def get_latest_artifact(session_id: str, db: AsyncSession = Depends(get_db)):
    """Found missing during real browser QA: reopening a session with a
    previously-generated Ship 30 essay or HTML artifact reset the viewer to
    its empty state instead of restoring what that session actually
    produced. The frontend calls this on session switch so the most recent
    artifact comes back with it."""
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    result = await db.execute(
        select(Artifact).where(Artifact.session_id == session_id).order_by(Artifact.created_at.desc()).limit(1)
    )
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail="This session has no artifacts yet")
    return artifact
