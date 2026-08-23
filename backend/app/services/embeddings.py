"""Embedding generation for ingestion and query time.

Embeddings are generated locally via Ollama (`nomic-embed-text`), independent
of whichever chat provider is currently toggled — retrieval quality shouldn't
depend on whether the demo is pointed at Claude or a local chat model.

If Ollama is unreachable (embedding model not pulled, daemon not running),
we fall back to a cheap deterministic hashing embedding so ingestion and
retrieval keep working end-to-end in a degraded-but-functional mode rather
than hard-failing. This is explicitly a quality trade-off, documented in
architecture.md and PRD.md > Risks.
"""
from __future__ import annotations

import hashlib
import logging
import math

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, settings: Settings):
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_embedding_model
        self.dimensions = settings.embedding_dimensions
        self.timeout = settings.llm_timeout_seconds

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            return await self._embed_ollama(texts)
        except httpx.HTTPError as exc:
            logger.warning(
                "embedding_fallback_hash",
                extra={"reason": str(exc), "model": self.model},
            )
            return [self._hash_embedding(t) for t in texts]

    async def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for text in texts:
                resp = await client.post(
                    f"{self.base_url}/api/embeddings", json={"model": self.model, "prompt": text}
                )
                resp.raise_for_status()
                data = resp.json()
                vector = data.get("embedding")
                if not vector:
                    raise httpx.HTTPError(f"Ollama returned no embedding for model {self.model}")
                vectors.append(vector)
        return vectors

    def _hash_embedding(self, text: str) -> list[float]:
        """Deterministic bag-of-hashed-tokens embedding. Not semantically rich,
        but stable and dependency-free — keeps retrieval degraded-functional
        (keyword-ish matching) instead of fully broken when Ollama is down."""
        vector = [0.0] * self.dimensions
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[idx] += sign
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]
