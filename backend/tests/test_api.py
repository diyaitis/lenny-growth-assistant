"""API contract tests. These run against the real app wiring (sqlite +
an intentionally-unreachable Ollama, per conftest.py), so they exercise the
actual resilience path — no LLM mocking here, on purpose: it proves a
misconfigured/offline model degrades gracefully through the whole stack
instead of 500ing.
"""
from fastapi.testclient import TestClient

from app.db.base import SessionLocal
from app.db.models import Artifact
from app.main import create_app


def _client():
    return TestClient(create_app())


def test_health_reports_degraded_when_llm_unreachable():
    with _client() as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["llm_reachable"] is False
        assert body["db_reachable"] is True
        assert body["llm_provider"] == "ollama"


def test_create_session_returns_201_with_id():
    with _client() as client:
        resp = client.post("/sessions", json={"title": "test session"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "test session"
        assert body["id"]


def test_chat_with_unknown_session_returns_structured_404():
    with _client() as client:
        resp = client.post("/chat", json={"session_id": "nope", "message": "hi"})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == 404


def test_chat_rejects_empty_message_with_422():
    with _client() as client:
        session_id = client.post("/sessions", json={}).json()["id"]
        resp = client.post("/chat", json={"session_id": session_id, "message": ""})
        assert resp.status_code == 422


def test_chat_degrades_gracefully_and_persists_both_messages():
    with _client() as client:
        session_id = client.post("/sessions", json={}).json()["id"]

        resp = client.post("/chat", json={"session_id": session_id, "message": "What is activation?"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["degraded"] is True
        assert body["message"]["role"] == "assistant"
        assert body["message"]["provider"] == "none"

        history = client.get(f"/sessions/{session_id}/messages").json()
        assert [m["role"] for m in history] == ["user", "assistant"]
        assert history[0]["content"] == "What is activation?"


def test_get_unknown_artifact_returns_404():
    with _client() as client:
        resp = client.get("/artifacts/does-not-exist")
        assert resp.status_code == 404


def test_latest_artifact_returns_404_when_session_has_none():
    with _client() as client:
        session_id = client.post("/sessions", json={}).json()["id"]
        resp = client.get(f"/sessions/{session_id}/artifacts/latest")
        assert resp.status_code == 404


def test_latest_artifact_unknown_session_returns_404():
    with _client() as client:
        resp = client.get("/sessions/does-not-exist/artifacts/latest")
        assert resp.status_code == 404


def test_latest_artifact_returns_most_recent_one():
    # Found missing during real browser QA: reopening a session that had
    # already generated artifacts showed no artifact until you asked for a
    # new one. This is what the frontend calls on session switch to
    # restore it instead.
    import asyncio
    from datetime import datetime, timedelta, timezone

    with _client() as client:
        session_id = client.post("/sessions", json={}).json()["id"]

        async def seed():
            # Explicit timestamps, not two back-to-back func.now() calls:
            # sqlite's CURRENT_TIMESTAMP has only second-level resolution,
            # so two commits in the same test could otherwise tie and make
            # "most recent" ordering flaky.
            now = datetime.now(timezone.utc)
            async with SessionLocal() as db:
                db.add(
                    Artifact(
                        session_id=session_id,
                        kind="markdown",
                        title="Older",
                        content="# Older",
                        raw_content="# Older",
                        created_at=now - timedelta(minutes=5),
                    )
                )
                db.add(
                    Artifact(
                        session_id=session_id,
                        kind="html",
                        title="Newer",
                        content="<p>new</p>",
                        raw_content="<p>new</p>",
                        created_at=now,
                    )
                )
                await db.commit()

        asyncio.run(seed())

        resp = client.get(f"/sessions/{session_id}/artifacts/latest")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Newer"
