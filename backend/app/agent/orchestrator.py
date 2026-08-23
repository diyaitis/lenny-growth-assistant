"""Agent orchestrator: ties routing, retrieval, generation, skills, and
artifact extraction into one call per user turn.

Flow for every message, regardless of which skill it routes to:
  1. Route the message to a skill (qa | ship30_essay | artifact) — rule-based,
     see agent/router.py for why.
  2. Always retrieve first (skill-independent): embed the message, pull the
     top-k transcript chunks, and decide if we have real "grounding" (best
     score above a floor) or not.
  3. Dispatch to the skill-specific prompt + generation step, which all share
     the same retrieved context and the same underlying chat provider.

This keeps grounding behavior identical across skills instead of each skill
reinventing "how do I talk to the model."
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.agent import prompts
from app.agent.router import Skill, route
from app.artifacts.generator import GeneratedArtifact, extract_artifact
from app.config import Settings
from app.db.models import Message
from app.llm.base import ChatMessage
from app.llm.factory import FallbackChatProvider
from app.services.embeddings import EmbeddingService
from app.services.retriever import Retriever, RetrievedChunk
from app.skills import ship30

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 20
ARTIFACT_MAX_TOKENS = 3500
SHIP30_MAX_TOKENS = 3000


@dataclass
class AgentResult:
    reply: str
    skill: Skill
    provider: str
    model: str
    degraded: bool
    grounded: bool
    citations: list[dict] = field(default_factory=list)
    artifact: GeneratedArtifact | None = None
    artifact_title: str | None = None
    debug: dict = field(default_factory=dict)


def _history_to_messages(history: list[Message]) -> list[ChatMessage]:
    recent = history[-MAX_HISTORY_MESSAGES:]
    return [ChatMessage(role=m.role, content=m.content) for m in recent if m.role in ("user", "assistant")]


def _build_context(chunks: list[RetrievedChunk]) -> tuple[str, list[dict]]:
    if not chunks:
        return "(no transcript excerpts retrieved)", []

    blocks = []
    citations = []
    for i, c in enumerate(chunks, start=1):
        label = f"[{i}] {c.guest or 'Unknown guest'} — \"{c.transcript_title}\""
        blocks.append(f"{label}\n{c.content}")
        citations.append(
            {
                "index": i,
                "transcript_id": c.transcript_id,
                "chunk_id": c.chunk_id,
                "guest": c.guest,
                "title": c.transcript_title,
                "source_url": c.source_url,
                "score": round(c.score, 4),
            }
        )
    return "\n\n---\n\n".join(blocks), citations


class AgentOrchestrator:
    def __init__(
        self,
        provider: FallbackChatProvider,
        embedder: EmbeddingService,
        retriever: Retriever,
        settings: Settings,
    ):
        self.provider = provider
        self.embedder = embedder
        self.retriever = retriever
        self.settings = settings

    async def handle_message(self, history: list[Message], user_message: str) -> AgentResult:
        skill = route(user_message)
        [query_embedding] = await self.embedder.embed([user_message])
        top_k = self.settings.retrieval_top_k * (2 if skill != Skill.qa else 1)
        chunks = await self.retriever.search(query_embedding, top_k)
        context, citations = _build_context(chunks)
        grounded = any(c.score >= self.settings.retrieval_min_score for c in chunks)

        logger.info(
            "agent_routed",
            extra={"skill": skill.value, "grounded": grounded, "retrieved_chunks": len(chunks)},
        )

        if skill == Skill.ship30_essay:
            return await self._handle_ship30(history, user_message, context, citations, grounded)
        if skill == Skill.artifact:
            return await self._handle_artifact(history, user_message, context, citations, grounded)
        return await self._handle_qa(history, user_message, context, citations, grounded)

    async def _handle_qa(self, history, user_message, context, citations, grounded) -> AgentResult:
        system = (
            prompts.QA_SYSTEM_PROMPT.format(context=context) if grounded else prompts.NO_CONTEXT_SYSTEM_PROMPT
        )
        messages = _history_to_messages(history) + [ChatMessage(role="user", content=user_message)]
        resp = await self.provider.chat(messages, system, max_tokens=self.settings.llm_max_output_tokens)

        return AgentResult(
            reply=resp.content,
            skill=Skill.qa,
            provider=resp.provider,
            model=resp.model,
            degraded=resp.degraded,
            grounded=grounded,
            citations=citations if grounded else [],
        )

    async def _handle_ship30(self, history, user_message, context, citations, grounded) -> AgentResult:
        target_words = self.settings.ship30_target_words
        system = ship30.build_system_prompt(target_words) + f"\n\nCONTEXT:\n{context}"
        messages = [ChatMessage(role="user", content=user_message)]

        resp = await self.provider.chat(messages, system, max_tokens=SHIP30_MAX_TOKENS)
        validation = ship30.validate_essay(resp.content, target_words)

        if not validation.ok and not resp.degraded:
            feedback = (
                f"{user_message}\n\nYour previous draft had issues: {'; '.join(validation.issues)}. "
                "Revise it to fix these while keeping everything else. Output only the corrected essay."
            )
            retry_messages = [ChatMessage(role="user", content=feedback)]
            resp = await self.provider.chat(retry_messages, system, max_tokens=SHIP30_MAX_TOKENS)
            validation = ship30.validate_essay(resp.content, target_words)

        title_match = resp.content.lstrip().splitlines()[0].lstrip("# ").strip() if resp.content.strip() else "Essay"
        artifact = GeneratedArtifact(
            kind="markdown",
            title=title_match[:200] or "Ship 30 for 30 Essay",
            raw_content=resp.content,
            sanitized_content=resp.content,
        )

        reply = prompts.SHIP30_INTRO
        if not validation.ok:
            reply += f" (Note: automated style check flagged: {'; '.join(validation.issues)}.)"

        return AgentResult(
            reply=reply,
            skill=Skill.ship30_essay,
            provider=resp.provider,
            model=resp.model,
            degraded=resp.degraded,
            grounded=grounded,
            citations=citations if grounded else [],
            artifact=artifact,
            artifact_title=artifact.title,
            debug={"word_count": validation.word_count, "validation_issues": validation.issues},
        )

    async def _handle_artifact(self, history, user_message, context, citations, grounded) -> AgentResult:
        system = prompts.ARTIFACT_SYSTEM_PROMPT.format(context=context)
        messages = _history_to_messages(history) + [ChatMessage(role="user", content=user_message)]
        resp = await self.provider.chat(messages, system, max_tokens=ARTIFACT_MAX_TOKENS)

        artifact = extract_artifact(resp.content, fallback_title="Generated artifact")
        if artifact is None:
            # Model didn't follow the fence format — degrade gracefully by
            # treating the whole reply as a Markdown artifact rather than
            # failing the request outright.
            logger.warning("artifact_fence_not_found", extra={"provider": resp.provider})
            artifact = GeneratedArtifact(
                kind="markdown",
                title="Generated artifact",
                raw_content=resp.content,
                sanitized_content=resp.content,
            )

        reply = f"Here's the {artifact.kind} artifact you asked for — open it in the viewer to the side."
        if resp.degraded:
            reply += " (Note: the model is currently in degraded/fallback mode.)"

        return AgentResult(
            reply=reply,
            skill=Skill.artifact,
            provider=resp.provider,
            model=resp.model,
            degraded=resp.degraded,
            grounded=grounded,
            citations=citations if grounded else [],
            artifact=artifact,
            artifact_title=artifact.title,
        )
