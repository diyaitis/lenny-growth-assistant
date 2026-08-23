"""Splits a transcript's body text into overlapping chunks for retrieval.

Token counting: we approximate tokens as whitespace-split words * 1.3 (a
common rule of thumb for English text against BPE tokenizers). This avoids
pulling in a real tokenizer (tiktoken, etc.) as a dependency for something
that only needs to be "roughly right" to keep chunks a sane size for a small
local model's context window. Documented as a deliberate simplification.

Chunking is turn-aware: Lenny's transcripts are formatted as repeated
`**Speaker** (hh:mm:ss):` blocks. We split on those turn boundaries first,
then greedily pack whole turns into a chunk until the token budget is hit,
so a chunk never cuts a speaker mid-sentence. This keeps citations meaningful
("here's what Elena Verna said starting at 00:12:30") instead of arbitrary
character-offset slices.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

TURN_RE = re.compile(r"^\*\*(?P<speaker>[^*]+)\*\*\s*\(?(?P<timestamp>[\d:]+)?\)?:?\s*$", re.MULTILINE)


@dataclass
class TranscriptChunk:
    index: int
    content: str
    token_count: int
    start_speaker: str | None
    start_timestamp: str | None


def _approx_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.3))


def _split_into_turns(body: str) -> list[tuple[str | None, str | None, str]]:
    """Return [(speaker, timestamp, turn_text), ...]. Falls back to paragraph
    splitting if the transcript doesn't match the expected speaker-turn format."""
    matches = list(TURN_RE.finditer(body))
    if not matches:
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        return [(None, None, p) for p in paragraphs]

    turns: list[tuple[str | None, str | None, str]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[start:end].strip()
        if text:
            turns.append((m.group("speaker").strip(), m.group("timestamp"), text))
    return turns


def chunk_transcript(body: str, target_tokens: int = 280, overlap_tokens: int = 40) -> list[TranscriptChunk]:
    turns = _split_into_turns(body)
    if not turns:
        return []

    chunks: list[TranscriptChunk] = []
    current: list[str] = []
    current_tokens = 0
    current_start_speaker: str | None = None
    current_start_ts: str | None = None

    def flush():
        nonlocal current, current_tokens, current_start_speaker, current_start_ts
        if not current:
            return
        text = "\n\n".join(current)
        chunks.append(
            TranscriptChunk(
                index=len(chunks),
                content=text,
                token_count=_approx_tokens(text),
                start_speaker=current_start_speaker,
                start_timestamp=current_start_ts,
            )
        )

    for speaker, ts, text in turns:
        formatted = f"**{speaker}** ({ts}): {text}" if speaker else text
        turn_tokens = _approx_tokens(formatted)

        if current and current_tokens + turn_tokens > target_tokens:
            flush()
            # carry the tail of the previous chunk forward for overlap/context continuity
            overlap_text = current[-1] if current else ""
            current = [overlap_text] if _approx_tokens(overlap_text) <= overlap_tokens else []
            current_tokens = _approx_tokens("\n\n".join(current)) if current else 0
            current_start_speaker, current_start_ts = speaker, ts

        if not current:
            current_start_speaker, current_start_ts = speaker, ts

        current.append(formatted)
        current_tokens += turn_tokens

    flush()
    return chunks
