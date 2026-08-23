"""
Central runtime configuration.

Everything an evaluator needs to change behavior (which LLM provider, which
model, how retrieval behaves, where the DB lives) is an environment variable
read here — never hardcoded deeper in the app. See ../../.env.example for the
full list with comments.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderName(str, Enum):
    anthropic = "anthropic"
    ollama = "ollama"
    openai = "openai"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "Lenny Growth Assistant"
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    cors_origins: str = Field(default="http://localhost:5173")

    # --- Database ---
    # postgresql+asyncpg://user:pass@host:port/db  (or sqlite+aiosqlite:///./dev.db for a
    # dependency-free local run; pgvector-backed retrieval requires real Postgres)
    database_url: str = Field(default="postgresql+asyncpg://lenny:lenny@localhost:5432/lenny_growth")

    # --- LLM provider toggle ---
    # Primary provider actually used to answer requests. This is the one knob
    # an evaluator flips to satisfy "run the submitted demo using Ollama".
    llm_provider: LLMProviderName = Field(default=LLMProviderName.ollama)
    # If the primary provider is unreachable / misconfigured, fall back here
    # instead of hard-failing the request (see app/llm/factory.py).
    llm_fallback_provider: LLMProviderName | None = Field(default=None)

    anthropic_api_key: str | None = Field(default=None)
    anthropic_model: str = Field(default="claude-sonnet-4-5-20250929")

    openai_api_key: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-4o-mini")
    openai_base_url: str = Field(default="https://api.openai.com/v1")

    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.1:8b")
    ollama_embedding_model: str = Field(default="nomic-embed-text")

    llm_timeout_seconds: float = Field(default=60.0)
    llm_max_output_tokens: int = Field(default=2000)

    # --- Retrieval ---
    retrieval_top_k: int = Field(default=6)
    retrieval_min_score: float = Field(default=0.15)
    chunk_target_tokens: int = Field(default=280)
    chunk_overlap_tokens: int = Field(default=40)
    embedding_dimensions: int = Field(default=768)  # nomic-embed-text output size

    # --- Ship 30/30 skill ---
    ship30_target_words: int = Field(default=1250)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
