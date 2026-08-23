from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    degraded: bool = False  # True when this is a canned fallback, not a real model response
    usage: dict = field(default_factory=dict)


class LLMUnavailableError(RuntimeError):
    """Raised when a provider cannot serve a request (down, misconfigured, timed out)."""


class ChatProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def health_check(self) -> bool:
        """Cheap, fast check of whether this provider can currently serve requests."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        system: str,
        max_tokens: int,
        temperature: float = 0.4,
    ) -> LLMResponse:
        """Send a chat completion request. Must raise LLMUnavailableError on failure
        (timeout, connection error, auth error) rather than letting raw exceptions
        propagate, so the caller (agent orchestrator) can apply fallback logic."""
