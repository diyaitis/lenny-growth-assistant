"""API contract tests. These run against the real app wiring (sqlite +
an intentionally-unreachable Ollama, per conftest.py), so they exercise the
actual resilience path — no LLM mocking here, on purpose: it proves a
misconfigured/offline model degrades gracefully through the whole stack
instead of 500ing.
"""
from fastapi.testclient import TestClient

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
