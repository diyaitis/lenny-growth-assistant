"""CLI entrypoint: ingest data/transcripts/*.md into the configured database.

Usage:
    python scripts/ingest.py                # ingest data/transcripts
    python scripts/ingest.py --dir some/dir # ingest a different directory

Run `bash scripts/fetch_transcripts.sh` first if data/transcripts is empty.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.db.bootstrap import init_db  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.services.embeddings import EmbeddingService  # noqa: E402
from app.services.ingestion import ingest_directory  # noqa: E402

logger = logging.getLogger(__name__)


async def main(directory: Path) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    await init_db()

    embedder = EmbeddingService(settings)
    if not await embedder.is_available():
        logger.warning(
            "ollama_unavailable_for_ingestion",
            extra={
                "message": (
                    f"Ollama not reachable at {settings.ollama_base_url}; falling back to a "
                    "low-quality hash embedding. Run `ollama serve` and "
                    f"`ollama pull {settings.ollama_embedding_model}` for real embeddings."
                )
            },
        )

    async with SessionLocal() as db:
        result = await ingest_directory(
            db,
            directory,
            embedder,
            target_tokens=settings.chunk_target_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        )

    print(f"Ingested {result['transcripts']} transcript(s), {result['chunks']} chunk(s).")
    if not result["files"]:
        print(f"No .md files found in {directory}. Run: bash scripts/fetch_transcripts.sh")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "transcripts")
    args = parser.parse_args()
    asyncio.run(main(args.dir))
