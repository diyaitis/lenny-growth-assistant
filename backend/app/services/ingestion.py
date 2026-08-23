"""Loads transcript markdown files from disk, chunks them, embeds the chunks,
and upserts everything into Postgres. Designed to be re-run safely: re-running
on the same files re-chunks and re-embeds (a transcript is deleted and
re-inserted), so ingestion is idempotent and there's no separate "refresh"
code path to keep in sync with "initial load".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Transcript
from app.services.chunker import chunk_transcript
from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass
class ParsedTranscript:
    slug: str
    title: str
    guest: str | None
    published_at: str | None
    source_url: str | None
    word_count: int | None
    body: str


def parse_transcript_file(path: Path) -> ParsedTranscript:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2]

    return ParsedTranscript(
        slug=path.stem,
        title=str(meta.get("title") or path.stem),
        guest=meta.get("guest"),
        published_at=str(meta.get("date")) if meta.get("date") else None,
        source_url=meta.get("post_url"),
        word_count=meta.get("word_count"),
        body=body.strip(),
    )


async def ingest_directory(
    db: AsyncSession,
    directory: Path,
    embedder: EmbeddingService,
    target_tokens: int,
    overlap_tokens: int,
) -> dict:
    files = sorted(directory.glob("*.md"))
    if not files:
        logger.warning("ingestion_no_files", extra={"directory": str(directory)})
        return {"transcripts": 0, "chunks": 0, "files": []}

    total_chunks = 0
    processed: list[str] = []

    for path in files:
        parsed = parse_transcript_file(path)

        existing = await db.execute(select(Transcript).where(Transcript.slug == parsed.slug))
        existing_transcript = existing.scalar_one_or_none()
        if existing_transcript is not None:
            await db.execute(delete(Chunk).where(Chunk.transcript_id == existing_transcript.id))
            await db.delete(existing_transcript)
            await db.flush()

        transcript = Transcript(
            slug=parsed.slug,
            title=parsed.title,
            guest=parsed.guest,
            published_at=parsed.published_at,
            source_url=parsed.source_url,
            word_count=parsed.word_count,
        )
        db.add(transcript)
        await db.flush()

        chunks = chunk_transcript(parsed.body, target_tokens=target_tokens, overlap_tokens=overlap_tokens)
        if not chunks:
            logger.warning("ingestion_empty_transcript", extra={"slug": parsed.slug})
            continue

        embeddings = await embedder.embed([c.content for c in chunks])

        for chunk, vector in zip(chunks, embeddings, strict=True):
            db.add(
                Chunk(
                    transcript_id=transcript.id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=vector,
                )
            )

        total_chunks += len(chunks)
        processed.append(parsed.slug)
        logger.info("ingested_transcript", extra={"slug": parsed.slug, "chunks": len(chunks)})

    await db.commit()
    return {"transcripts": len(processed), "chunks": total_chunks, "files": processed}
