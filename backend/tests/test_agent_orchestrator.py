"""Orchestrator-level tests: routing, grounding, ship30 retry-on-validation-
failure, and artifact extraction/sanitization — all with a scripted fake chat
provider so these run instantly and deterministically with no network calls.

Embeddings use the real EmbeddingService, which automatically falls back to a
deterministic hash-based embedding because OLLAMA_BASE_URL in tests points at
an unreachable address (see conftest.py). That fallback is bag-of-hashed-
tokens, so chunks that share vocabulary with the query score higher than
unrelated ones — enough to meaningfully test "grounded vs not grounded"
without needing a real embedding model in CI.
"""
from __future__ import annotations

import pytest

from app.agent.orchestrator import AgentOrchestrator
from app.agent.router import Skill
from app.config import get_settings
from app.db.base import SessionLocal
from app.db.models import Chunk, Transcript
from app.llm.base import ChatMessage, ChatProvider, LLMResponse, LLMUnavailableError
from app.services.embeddings import EmbeddingService
from app.services.retriever import Retriever

GOOD_ESSAY = (
    "# Activation Beats Acquisition\n\n"
    + ("Most teams over-invest in acquisition. " * 30)
    + "\n\n## Why it happens\n\n- Acquisition is easy to chart\n- Activation is slower to show up\n\n"
    + ("**Activation is the real lever** for durable growth, Elena Verna argues. " * 40)
    + "\n\n## Takeaway\n\nAudit your activation funnel this week. "
    + ("More words to hit target length. " * 120)
)

BAD_ESSAY = "no structure, no bold, no bullets, way too short"


class FakeChatProvider(ChatProvider):
    name = "fake"
    model = "fake-model"

    def __init__(self, responses: list[str] | None = None, raise_unavailable: bool = False):
        self.responses = list(responses or [])
        self.raise_unavailable = raise_unavailable
        self.calls: list[tuple[list[ChatMessage], str]] = []

    async def health_check(self) -> bool:
        return True

    async def chat(self, messages, system, max_tokens, temperature=0.4) -> LLMResponse:
        self.calls.append((messages, system))
        if self.raise_unavailable:
            raise LLMUnavailableError("simulated outage")
        content = self.responses.pop(0) if self.responses else "default fake response"
        return LLMResponse(content=content, provider=self.name, model=self.model)


async def _seed_chunk(content: str, title: str = "Elena Verna 4.0", guest: str = "Elena Verna"):
    settings = get_settings()
    embedder = EmbeddingService(settings)
    [vector] = await embedder.embed([content])
    async with SessionLocal() as db:
        transcript = Transcript(slug=title.lower().replace(" ", "-"), title=title, guest=guest)
        db.add(transcript)
        await db.flush()
        db.add(Chunk(transcript_id=transcript.id, chunk_index=0, content=content, token_count=50, embedding=vector))
        await db.commit()


async def _make_orchestrator(provider: ChatProvider) -> AgentOrchestrator:
    # Intentionally not `async with`: the session must outlive this function,
    # since retrieval happens later inside orchestrator.handle_message(). It's
    # closed implicitly at test-process exit — fine for a short-lived test run.
    settings = get_settings()
    embedder = EmbeddingService(settings)
    db = SessionLocal()
    retriever = Retriever(db)
    return AgentOrchestrator(provider, embedder, retriever, settings)


@pytest.mark.asyncio
async def test_qa_is_grounded_when_relevant_chunk_exists():
    await _seed_chunk("Elena Verna says activation beats acquisition for B2B growth teams.")
    provider = FakeChatProvider(responses=["Activation matters more than acquisition, per Elena Verna."])
    orchestrator = await _make_orchestrator(provider)
    result = await orchestrator.handle_message([], "What did Elena Verna say about activation acquisition?")

    assert result.skill == Skill.qa
    assert result.grounded is True
    assert len(result.citations) > 0
    assert result.citations[0]["guest"] == "Elena Verna"


@pytest.mark.asyncio
async def test_qa_is_not_grounded_for_unrelated_query():
    await _seed_chunk("Elena Verna says activation beats acquisition for B2B growth teams.")
    provider = FakeChatProvider(responses=["I don't have grounding for that."])
    orchestrator = await _make_orchestrator(provider)

    result = await orchestrator.handle_message([], "zzqx flibbertigibbet nonsense query unrelated to anything")

    assert result.grounded is False
    assert result.citations == []


@pytest.mark.asyncio
async def test_ship30_retries_once_when_validation_fails_then_succeeds():
    provider = FakeChatProvider(responses=[BAD_ESSAY, GOOD_ESSAY])
    orchestrator = await _make_orchestrator(provider)

    result = await orchestrator.handle_message([], "turn this into a ship 30 for 30 essay")

    assert result.skill == Skill.ship30_essay
    assert len(provider.calls) == 2  # first draft failed validation, triggered one retry
    assert result.artifact is not None
    assert result.artifact.kind == "markdown"
    assert "Activation Beats Acquisition" in result.artifact.raw_content
    assert result.debug["validation_issues"] == []


@pytest.mark.asyncio
async def test_ship30_does_not_retry_when_first_draft_is_good():
    provider = FakeChatProvider(responses=[GOOD_ESSAY])
    orchestrator = await _make_orchestrator(provider)

    result = await orchestrator.handle_message([], "write me an essay about this")

    assert len(provider.calls) == 1
    assert result.debug["validation_issues"] == []


@pytest.mark.asyncio
async def test_artifact_skill_extracts_and_sanitizes_html():
    html_response = (
        '```html\n<html><head></head><body><script src="https://evil.example/x.js">'
        "</script><h1>Report</h1></body></html>\n```"
    )
    provider = FakeChatProvider(responses=[html_response])
    orchestrator = await _make_orchestrator(provider)

    result = await orchestrator.handle_message([], "generate an html artifact summarizing this")

    assert result.skill == Skill.artifact
    assert result.artifact.kind == "html"
    assert "evil.example" not in result.artifact.sanitized_content
    assert "evil.example" in result.artifact.raw_content  # audit trail keeps the original


@pytest.mark.asyncio
async def test_artifact_skill_falls_back_to_markdown_when_model_ignores_fence_format():
    provider = FakeChatProvider(responses=["I forgot to use a fenced code block, oops."])
    orchestrator = await _make_orchestrator(provider)

    result = await orchestrator.handle_message([], "please generate a markdown document for me")

    assert result.artifact is not None
    assert result.artifact.kind == "markdown"
    assert "oops" in result.artifact.raw_content


@pytest.mark.asyncio
async def test_provider_outage_surfaces_as_llm_unavailable_not_a_crash():
    provider = FakeChatProvider(raise_unavailable=True)
    orchestrator = await _make_orchestrator(provider)

    with pytest.raises(LLMUnavailableError):
        await orchestrator.handle_message([], "what is activation?")
