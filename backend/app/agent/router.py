"""Routes a user message to one of three skills.

Design decision (documented in architecture.md > Agentic architecture &
grounding): routing is rule-based (keyword/regex), not an LLM tool-call
decision. The mandatory local-model path (Ollama, small models) has
inconsistent function-calling support, and a misrouted request is a worse
failure mode for a demo than a slightly-blunt keyword match. Grounded
retrieval always runs first regardless of skill, so even a misrouted message
still gets a grounded answer rather than a broken one. Precedence: explicit
artifact/HTML requests > explicit Ship 30 essay requests > default QA.
"""
from __future__ import annotations

import re
from enum import Enum


class Skill(str, Enum):
    qa = "qa"
    ship30_essay = "ship30_essay"
    artifact = "artifact"


_ARTIFACT_PATTERNS = [
    r"\bartifact\b",
    r"\bhtml\b",
    r"\blanding page\b",
    r"\bmarkdown (doc|document|file)\b",
    r"\brender(ed)?\b.*\b(page|doc|component|widget)\b",
    r"\bgenerate (a |an )?(doc|document|snippet|page)\b",
    r"\bturn this into (a )?(doc|document|page)\b",
]

_SHIP30_PATTERNS = [
    r"\bship\s?30\b",
    r"\batomic essay\b",
    r"\bturn (this|that|it) into an essay\b",
    r"\bwrite (me )?an essay\b",
    r"\bblog post\b",
]

_artifact_re = re.compile("|".join(_ARTIFACT_PATTERNS), re.IGNORECASE)
_ship30_re = re.compile("|".join(_SHIP30_PATTERNS), re.IGNORECASE)


def route(message: str) -> Skill:
    if _artifact_re.search(message):
        return Skill.artifact
    if _ship30_re.search(message):
        return Skill.ship30_essay
    return Skill.qa
