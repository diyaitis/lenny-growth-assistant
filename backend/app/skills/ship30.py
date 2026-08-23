"""The "Ship 30 for 30" content skill.

Ship 30 for 30 (Dickie Bush & Nicolas Cole) teaches atomic essay writing:
short, single-idea, high-signal essays optimized for skimming and a single
clear takeaway. This module encodes those principles as structured, checkable
skill metadata rather than a one-off prompt string, so:

  1. The system prompt is generated from an explicit, versioned principles
     list (auditable — you can read exactly what "the skill" believes good
     writing looks like), and
  2. `validate_essay` can mechanically check a generated draft against the
     same principles the prompt asked for, so the orchestrator can retry with
     targeted feedback if a draft misses (e.g. no bold emphasis, way under
     word count) instead of silently shipping a weak draft.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PRINCIPLES = [
    "Open with a strong hook in the first 1-2 sentences: a bold claim, a surprising "
    "fact, or a specific tension — never a generic throat-clear like 'In this essay...'.",
    "Give the essay a clear narrative progression: hook -> tension/problem -> grounded "
    "insight (from the source material) -> specific takeaway. One throughline, not a list of loosely related ideas.",
    "Write for skimmability: short paragraphs (2-4 sentences), descriptive subheadings, "
    "bullet lists for anything enumerable, and selective **bold** on the single most important "
    "phrase per section — not every sentence.",
    "Every non-obvious claim must be grounded in the provided transcript context, and the "
    "essay must make clear which source(s) the ideas come from (e.g. 'as Elena Verna put it...').",
    "End with one specific, actionable takeaway the reader can apply this week — not a vague "
    "'in conclusion, growth is important' close.",
    "Target length: approximately 1,250 words. Do not pad to hit the count; cut anything that "
    "doesn't serve the single throughline instead.",
]

TARGET_WORDS_DEFAULT = 1250
WORD_COUNT_TOLERANCE = 0.35  # accept 65%-135% of target before flagging


def build_system_prompt(target_words: int = TARGET_WORDS_DEFAULT) -> str:
    numbered = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(PRINCIPLES))
    return (
        "You are writing a Ship 30 for 30-style atomic essay: a short, single-idea, "
        "high-signal essay meant to be read in one sitting.\n\n"
        "Follow these principles:\n"
        f"{numbered}\n\n"
        f"Target length: ~{target_words} words.\n"
        "Ground every non-trivial claim in the provided transcript excerpts — do not "
        "invent facts, statistics, or quotes that are not present in the context.\n"
        "Output *only* the essay in Markdown (a single H1 title, then the body with "
        "H2/H3 subheadings, bullets, and bold emphasis as appropriate). No preamble, "
        "no 'here is your essay', no meta-commentary."
    )


@dataclass
class EssayValidation:
    ok: bool
    word_count: int
    issues: list[str]


def validate_essay(markdown: str, target_words: int = TARGET_WORDS_DEFAULT) -> EssayValidation:
    issues: list[str] = []
    word_count = len(markdown.split())

    lower, upper = target_words * (1 - WORD_COUNT_TOLERANCE), target_words * (1 + WORD_COUNT_TOLERANCE)
    if not (lower <= word_count <= upper):
        issues.append(f"word count {word_count} is outside the expected range ({int(lower)}-{int(upper)})")

    if not re.search(r"^#{1,2}\s", markdown, re.MULTILINE):
        issues.append("missing a title/H1 or section headings")

    # Found live against a real (small) local model: it produced a genuinely
    # well-structured bullet list using "•" instead of Markdown "-"/"*". That's
    # valid skimmable formatting, not a formatting failure, so the bullet
    # glyphs recognized here intentionally aren't limited to strict
    # CommonMark list markers.
    if len(re.findall(r"^\s*[-*•·]\s", markdown, re.MULTILINE)) == 0:
        issues.append("no bullet list found (skimmable formatting expects at least one)")

    if "**" not in markdown:
        issues.append("no bold emphasis found")

    return EssayValidation(ok=not issues, word_count=word_count, issues=issues)
