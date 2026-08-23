from __future__ import annotations

import logging

from app.config import LLMProviderName, Settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import ChatMessage, ChatProvider, LLMResponse, LLMUnavailableError
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


def build_provider(name: LLMProviderName, settings: Settings) -> ChatProvider:
    if name == LLMProviderName.anthropic:
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model, settings.llm_timeout_seconds)
    if name == LLMProviderName.ollama:
        return OllamaProvider(settings.ollama_base_url, settings.ollama_model, settings.llm_timeout_seconds)
    if name == LLMProviderName.openai:
        return OpenAIProvider(
            settings.openai_api_key, settings.openai_model, settings.openai_base_url, settings.llm_timeout_seconds
        )
    raise ValueError(f"Unknown provider: {name}")


class FallbackChatProvider(ChatProvider):
    """Wraps a primary provider with an optional secondary, and a last-resort
    canned response so a chat request never crashes the API — it degrades
    into a clearly-labeled message instead (see architecture.md > Resilience).
    """

    def __init__(self, primary: ChatProvider, fallback: ChatProvider | None):
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name
        self.model = primary.model

    async def health_check(self) -> bool:
        return await self.primary.health_check()

    async def chat(
        self,
        messages: list[ChatMessage],
        system: str,
        max_tokens: int,
        temperature: float = 0.4,
    ) -> LLMResponse:
        try:
            return await self.primary.chat(messages, system, max_tokens, temperature)
        except LLMUnavailableError as primary_error:
            logger.warning(
                "primary_provider_failed",
                extra={"provider": self.primary.name, "error": str(primary_error)},
            )
            if self.fallback is not None:
                try:
                    resp = await self.fallback.chat(messages, system, max_tokens, temperature)
                    resp.degraded = True
                    return resp
                except LLMUnavailableError as fallback_error:
                    logger.error(
                        "fallback_provider_failed",
                        extra={"provider": self.fallback.name, "error": str(fallback_error)},
                    )
            return LLMResponse(
                content=(
                    "I couldn't reach the language model backing this assistant right now "
                    f"({self.primary.name} is unavailable"
                    + (f", and the fallback {self.fallback.name} also failed" if self.fallback else "")
                    + "). Your message was saved. Please check the model configuration "
                    "(is Ollama running? Is the API key set?) and try again."
                ),
                provider="none",
                model="none",
                degraded=True,
            )


def get_chat_provider(settings: Settings) -> FallbackChatProvider:
    primary = build_provider(settings.llm_provider, settings)
    fallback = build_provider(settings.llm_fallback_provider, settings) if settings.llm_fallback_provider else None
    return FallbackChatProvider(primary, fallback)
