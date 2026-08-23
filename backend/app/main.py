from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import artifacts, chat, health, sessions
from app.config import get_settings
from app.db.base import engine
from app.db.bootstrap import init_db
from app.logging_config import configure_logging
from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("starting_up", extra={"provider": settings.llm_provider.value, "environment": settings.environment})

    await init_db()

    from app.llm.factory import get_chat_provider

    app.state.settings = settings
    app.state.chat_provider = get_chat_provider(settings)
    app.state.embedder = EmbeddingService(settings)
    app.state.db_dialect = engine.dialect.name

    llm_ok = await app.state.chat_provider.health_check()
    if not llm_ok:
        logger.warning(
            "primary_llm_provider_not_ready_at_startup",
            extra={"provider": settings.llm_provider.value},
        )

    yield

    await engine.dispose()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Lenny Growth Assistant API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.status_code, "message": exc.detail}},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_exception", extra={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={"error": {"code": 500, "message": "Internal server error. This has been logged."}},
        )

    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(chat.router)
    app.include_router(artifacts.router)

    return app


app = create_app()
