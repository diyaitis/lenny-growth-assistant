"""Retrieval over the transcript knowledge base.

On Postgres, similarity search is pushed down to pgvector via the `<=>`
cosine-distance operator (indexed with HNSW — see db/bootstrap.py), so it
scales past what fits comfortably in Python. On SQLite (local dev/tests
without Docker), we fall back to computing cosine similarity in Python over
all stored chunks. That fallback is intentionally isolated in
`rank_chunks_by_similarity`, a pure function with no DB or I/O dependency, so
retrieval *ranking logic* is unit-testable without any database at all.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import is_postgres
from app.db.models import Chunk, Transcript


@dataclass
class RetrievedChunk:
    chunk_id: str
    transcript_id: str
    transcript_title: str
    guest: str | None
    source_url: str | None
    chunk_index: int
    content: str
    score: float


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1e-9
    norm_b = math.sqrt(sum(y * y for y in b)) or 1e-9
    return dot / (norm_a * norm_b)


def rank_chunks_by_similarity(
    query_embedding: list[float],
    candidates: list[tuple[str, list[float]]],
    top_k: int,
) -> list[tuple[str, float]]:
    """Pure ranking function: given a query vector and [(id, vector), ...],
    return the top_k ids with their cosine similarity score, descending."""
    scored = [(cid, cosine_similarity(query_embedding, vec)) for cid, vec in candidates if vec]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]


class Retriever:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        if is_postgres():
            return await self._search_postgres(query_embedding, top_k)
        return await self._search_fallback(query_embedding, top_k)

    async def _search_postgres(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        from sqlalchemy import text as sa_text

        vector_literal = "[" + ",".join(repr(float(v)) for v in query_embedding) + "]"
        rows = await self.db.execute(
            sa_text(
                """
                SELECT c.id, c.transcript_id, c.chunk_index, c.content,
                       t.title, t.guest, t.source_url,
                       1 - (c.embedding <=> :qvec) AS score
                FROM chunks c
                JOIN transcripts t ON t.id = c.transcript_id
                WHERE c.embedding IS NOT NULL
                ORDER BY c.embedding <=> :qvec
                LIMIT :k
                """
            ),
            {"qvec": vector_literal, "k": top_k},
        )
        return [
            RetrievedChunk(
                chunk_id=r.id,
                transcript_id=r.transcript_id,
                transcript_title=r.title,
                guest=r.guest,
                source_url=r.source_url,
                chunk_index=r.chunk_index,
                content=r.content,
                score=float(r.score),
            )
            for r in rows
        ]

    async def _search_fallback(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        result = await self.db.execute(select(Chunk).where(Chunk.embedding.is_not(None)))
        chunks = result.scalars().all()
        candidates = [(c.id, c.embedding) for c in chunks]
        ranked = rank_chunks_by_similarity(query_embedding, candidates, top_k)
        by_id = {c.id: c for c in chunks}

        transcripts_result = await self.db.execute(select(Transcript))
        transcripts_by_id = {t.id: t for t in transcripts_result.scalars().all()}

        out: list[RetrievedChunk] = []
        for chunk_id, score in ranked:
            c = by_id[chunk_id]
            t = transcripts_by_id[c.transcript_id]
            out.append(
                RetrievedChunk(
                    chunk_id=c.id,
                    transcript_id=c.transcript_id,
                    transcript_title=t.title,
                    guest=t.guest,
                    source_url=t.source_url,
                    chunk_index=c.chunk_index,
                    content=c.content,
                    score=score,
                )
            )
        return out
