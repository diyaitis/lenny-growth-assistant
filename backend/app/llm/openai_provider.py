from __future__ import annotations

import logging

import httpx

from app.llm.base import ChatMessage, ChatProvider, LLMResponse, LLMUnavailableError

logger = logging.getLogger(__name__)


class OpenAIProvider(ChatProvider):
    """Second cloud provider, wired directly against the Chat Completions HTTP
    API (no SDK dependency) to demonstrate the toggle is provider-agnostic and
    not just "two ways to call Anthropic"."""

    name = "openai"

    def __init__(self, api_key: str | None, model: str, base_url: str, timeout: float = 60.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def health_check(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        messages: list[ChatMessage],
        system: str,
        max_tokens: int,
        temperature: float = 0.4,
    ) -> LLMResponse:
        if not self.api_key:
            raise LLMUnavailableError("OPENAI_API_KEY is not configured")

        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError("OpenAI request timed out") from exc
        except httpx.ConnectError as exc:
            raise LLMUnavailableError("Could not reach the OpenAI API (network error)") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMUnavailableError(f"OpenAI returned {exc.response.status_code}: {exc.response.text[:300]}") from exc

        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(
            content=choice,
            provider=self.name,
            model=self.model,
            usage={"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")},
        )
