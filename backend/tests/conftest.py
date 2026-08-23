from __future__ import annotations

import os
import tempfile

# Must run before any `app.*` module is imported anywhere in the test session,
# since app.config.get_settings() is lru_cached — whichever env vars are set
# the first time it's called are what every test gets. Point at an isolated
# temp sqlite file (not :memory:, so multiple connections in the same test
# still see the same data) and a deliberately-unreachable Ollama endpoint so
# tests never depend on external services.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="lenny_growth_test_")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TEST_DB_DIR}/test.db")
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:1")  # unreachable on purpose
os.environ.setdefault("ENVIRONMENT", "test")

import pytest_asyncio  # noqa: E402

from app.db.base import Base, engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset_schema():
    """Fresh tables for every test — cheap on sqlite, keeps tests independent."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Some orchestrator tests intentionally open a session that outlives a
    # helper function (see test_agent_orchestrator._make_orchestrator);
    # disposing the pool here reclaims those connections cleanly instead of
    # letting the garbage collector warn about it mid-suite.
    await engine.dispose()
