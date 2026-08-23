"""Idempotent schema bootstrap, run on app startup and by tests.

Deliberately NOT Alembic: this project has one linear schema with no migration
history to preserve yet, so a single idempotent `create_all` + a couple of
`IF NOT EXISTS` statements is less ceremony than a migrations directory for a
take-home. If this app grew past the demo stage, introducing Alembic here
would be the very next thing to do (called out in architecture.md).
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from app.db.base import Base, engine, is_postgres

logger = logging.getLogger(__name__)


async def init_db() -> None:
    async with engine.begin() as conn:
        if is_postgres():
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        await conn.run_sync(Base.metadata.create_all)

        if is_postgres():
            # HNSW needs no pre-training data (unlike IVFFlat), so it's safe
            # to create up front even against an empty table.
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw "
                    "ON chunks USING hnsw (embedding vector_cosine_ops)"
                )
            )
    logger.info("db_initialized", extra={"dialect": engine.dialect.name})
