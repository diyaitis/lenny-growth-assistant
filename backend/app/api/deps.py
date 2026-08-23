from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import AgentOrchestrator
from app.db.base import SessionLocal
from app.services.retriever import Retriever


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def build_orchestrator(request: Request, db: AsyncSession) -> AgentOrchestrator:
    """Not a FastAPI dependency on purpose: routes already hold a `db` session
    (via `Depends(get_db)`) and must reuse that exact session so the messages
    they persist and the retrieval query the orchestrator runs share one
    transaction. Call this directly with that session instead of adding a
    second `Depends(get_db)` that would open a separate connection."""
    state = request.app.state
    retriever = Retriever(db)
    return AgentOrchestrator(state.chat_provider, state.embedder, retriever, state.settings)
