from __future__ import annotations

import logging

import anthropic

from app.llm.base import ChatMessage, ChatProvider, LLMResponse, LLMUnavailableError

logger = logging.getLogger(__name__)


class AnthropicProvider(ChatProvider):
    """Cloud provider using the Anthropic Messages API."""

    name = "anthropic"

    def __init__(self, api_key: str | None, model: str, timeout: float = 60.0, max_retries: int = 2):
        self.api_key = api_key
        self.model = model
        self._client = (
            anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=max_retries) if api_key else None
        )

    async def health_check(self) -> bool:
        # A real completion is the only reliable health signal for a hosted
        # API; we only check that credentials are present to keep this cheap
        # and side-effect-free (no billed request on every health poll).
        return self._client is not None

    async def chat(
        self,
        messages: list[ChatMessage],
        system: str,
        max_tokens: int,
        temperature: float = 0.4,
    ) -> LLMResponse:
        if self._client is None:
            raise LLMUnavailableError("ANTHROPIC_API_KEY is not configured")

        try:
            resp = await self._client.messages.create(
                model=self.model,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": m.role, "content": m.content} for m in messages],
            )
        except anthropic.AuthenticationError as exc:
            raise LLMUnavailableError("Anthropic rejected the API key (401)") from exc
        except anthropic.RateLimitError as exc:
            raise LLMUnavailableError("Anthropic rate-limited this request (429)") from exc
        except anthropic.APITimeoutError as exc:
            raise LLMUnavailableError("Anthropic request timed out") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailableError("Could not reach the Anthropic API (network error)") from exc
        except anthropic.APIStatusError as exc:
            raise LLMUnavailableError(f"Anthropic returned {exc.status_code}: {exc.message}") from exc

        text = "".join(block.text for block in resp.content if block.type == "text")
        return LLMResponse(
            content=text,
            provider=self.name,
            model=self.model,
            usage={
                "prompt_tokens": resp.usage.input_tokens,
                "completion_tokens": resp.usage.output_tokens,
            },
        )
