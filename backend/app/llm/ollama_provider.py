from __future__ import annotations

import logging

import httpx

from app.llm.base import ChatMessage, ChatProvider, LLMResponse, LLMUnavailableError

logger = logging.getLogger(__name__)


class OllamaProvider(ChatProvider):
    """Local model provider — mandatory for the demo per the assignment brief.

    Talks to a locally running `ollama serve` over HTTP. No API key, no
    network egress, which is exactly the point: this is the provider an
    evaluator can run with zero cloud credentials.
    """

    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def chat(
        self,
        messages: list[ChatMessage],
        system: str,
        max_tokens: int,
        temperature: float = 0.4,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.ConnectError as exc:
            raise LLMUnavailableError(
                f"Ollama unreachable at {self.base_url}. Is `ollama serve` running "
                f"and has `ollama pull {self.model}` been run?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError(f"Ollama timed out after {self.timeout}s") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMUnavailableError(f"Ollama returned {exc.response.status_code}: {exc.response.text[:300]}") from exc

        content = data.get("message", {}).get("content", "")
        if not content:
            raise LLMUnavailableError("Ollama returned an empty response")

        return LLMResponse(
            content=content,
            provider=self.name,
            model=self.model,
            usage={
                "prompt_tokens": data.get("prompt_eval_count"),
                "completion_tokens": data.get("eval_count"),
            },
        )
