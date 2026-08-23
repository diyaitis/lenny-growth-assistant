from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, db: AsyncSession = Depends(get_db)):
    state = request.app.state
    settings = state.settings

    db_reachable = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - health check must never 500
        db_reachable = False
        logger.error("health_db_check_failed", extra={"error": str(exc)})

    llm_reachable = await state.chat_provider.health_check()
    embedding_reachable = await state.embedder.is_available()

    status = "ok" if (db_reachable and llm_reachable) else "degraded"

    return HealthResponse(
        status=status,
        environment=settings.environment,
        db_dialect=state.db_dialect,
        db_reachable=db_reachable,
        llm_provider=settings.llm_provider.value,
        llm_fallback_provider=settings.llm_fallback_provider.value if settings.llm_fallback_provider else None,
        llm_reachable=llm_reachable,
        embedding_backend_reachable=embedding_reachable,
    )
