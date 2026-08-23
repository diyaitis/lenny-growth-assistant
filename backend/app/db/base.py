from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

_connect_args = {}
if settings.database_url.startswith("sqlite"):
    # SQLite is only used for fast local dev/tests without Docker; it can't do
    # pgvector similarity search, so retrieval degrades to a Python fallback
    # (see app/services/retriever.py). Real deployments must use Postgres.
    _connect_args = {"check_same_thread": False}

engine = create_async_engine(settings.database_url, echo=False, connect_args=_connect_args)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def is_postgres() -> bool:
    return engine.dialect.name == "postgresql"
