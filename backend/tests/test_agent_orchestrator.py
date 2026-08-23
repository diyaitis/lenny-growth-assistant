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

    def __init__(
        self,
        responses: list[str] | None = None,
        raise_unavailable: bool = False,
        degraded_response: str | None = None,
    ):
        self.responses = list(responses or [])
        self.raise_unavailable = raise_unavailable
        # Simulates what AgentOrchestrator actually receives in production
        # when the real FallbackChatProvider's primary+fallback both fail:
        # a normal (non-raising) LLMResponse with degraded=True and canned
        # content, not an exception — the orchestrator never sees the
        # retry/fallback machinery itself, only its outcome.
        self.degraded_response = degraded_response
        self.calls: list[tuple[list[ChatMessage], str]] = []

    async def health_check(self) -> bool:
        return True

    async def chat(self, messages, system, max_tokens, temperature=0.4) -> LLMResponse:
        self.calls.append((messages, system))
        if self.raise_unavailable:
            raise LLMUnavailableError("simulated outage")
        if self.degraded_response is not None:
            return LLMResponse(content=self.degraded_response, provider="none", model="none", degraded=True)
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


async def _seed_chunks_same_transcript(
    contents: list[str], title: str = "Elena Verna 4.0", guest: str = "Elena Verna"
):
    """Like _seed_chunk, but multiple chunks under one transcript — the
    common real-world case (a top_k of 6-12 pulling several chunks from the
    same episode) that surfaced the citation-dedup bug in live testing."""
    settings = get_settings()
    embedder = EmbeddingService(settings)
    vectors = await embedder.embed(contents)
    async with SessionLocal() as db:
        transcript = Transcript(slug=title.lower().replace(" ", "-"), title=title, guest=guest)
        db.add(transcript)
        await db.flush()
        for i, (content, vector) in enumerate(zip(contents, vectors, strict=True)):
            db.add(Chunk(transcript_id=transcript.id, chunk_index=i, content=content, token_count=50, embedding=vector))
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
    # Real embeddings would score this pair ~0.7+ on semantic similarity alone
    # (verified against real corpus data — see RETRIEVAL_MIN_SCORE's comment
    # in config.py); the hash-based fallback used in tests only picks up
    # literal token overlap, so the query needs to actually share vocabulary
    # with the seeded chunk to clear the same real-world-calibrated threshold.
    result = await orchestrator.handle_message(
        [], "Tell me what Elena Verna says about activation beats acquisition for B2B growth teams."
    )

    assert result.skill == Skill.qa
    assert result.grounded is True
    assert len(result.citations) > 0
    assert result.citations[0]["guest"] == "Elena Verna"


@pytest.mark.asyncio
async def test_citations_are_deduped_per_transcript():
    # Found via real browser QA: an artifact/ship30 request (2x top_k) against
    # a corpus where several chunks come from the same episode rendered as
    # e.g. 8 near-identical "Elena Verna 4.0 — Elena Verna 4.0" source lines.
    # The context sent to the model should still see every chunk (more
    # grounding material is strictly better); the user-facing citation list
    # should show each transcript once.
    await _seed_chunks_same_transcript(
        [
            "Elena Verna says activation beats acquisition for B2B growth teams.",
            "Elena Verna also says B2B growth teams should measure activation weekly.",
            "Elena Verna adds that B2B growth teams often under-invest in activation.",
        ]
    )
    provider = FakeChatProvider(responses=["Activation matters more than acquisition, per Elena Verna."])
    orchestrator = await _make_orchestrator(provider)

    result = await orchestrator.handle_message(
        [], "Tell me what Elena Verna says about activation beats acquisition for B2B growth teams."
    )

    assert result.grounded is True
    transcript_ids = [c["transcript_id"] for c in result.citations]
    assert len(transcript_ids) == len(set(transcript_ids))  # no repeated transcript


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
async def test_ship30_skips_artifact_when_provider_degrades():
    # Found via live testing against real Ollama: when generation degrades
    # (times out on both primary and fallback), the canned "unavailable"
    # message was getting wrapped in a Markdown artifact and presented as
    # the essay — an artifact literally titled with an error message. The
    # fix: a degraded response short-circuits to a plain degraded reply,
    # same as the QA path, with no artifact at all.
    canned = "I couldn't reach the language model backing this assistant right now (ollama is unavailable)."
    provider = FakeChatProvider(degraded_response=canned)
    orchestrator = await _make_orchestrator(provider)

    result = await orchestrator.handle_message([], "turn this into a ship 30 for 30 essay")

    assert result.degraded is True
    assert result.artifact is None
    assert result.reply == canned


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
async def test_artifact_skill_skips_artifact_when_provider_degrades():
    canned = "I couldn't reach the language model backing this assistant right now (ollama is unavailable)."
    provider = FakeChatProvider(degraded_response=canned)
    orchestrator = await _make_orchestrator(provider)

    result = await orchestrator.handle_message([], "generate an html artifact for this")

    assert result.degraded is True
    assert result.artifact is None
    assert result.reply == canned


@pytest.mark.asyncio
async def test_provider_outage_surfaces_as_llm_unavailable_not_a_crash():
    provider = FakeChatProvider(raise_unavailable=True)
    orchestrator = await _make_orchestrator(provider)

    with pytest.raises(LLMUnavailableError):
        await orchestrator.handle_message([], "what is activation?")
