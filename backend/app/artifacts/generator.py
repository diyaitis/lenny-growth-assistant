"""Extracts a generated artifact (Markdown doc or HTML/CSS snippet) out of a
raw LLM completion and prepares it for storage + rendering.

The model is instructed (see agent/prompts.py) to wrap the artifact in a
single fenced code block (```html ... ``` or ```markdown ... ```). We parse
that fence rather than trusting the whole completion as the artifact, so any
conversational preamble the model adds ("Sure, here's your doc:") doesn't end
up rendered inside the viewer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.artifacts.sanitizer import sanitize_html_artifact

_FENCE_RE = re.compile(r"```(?P<lang>html|markdown|md)\s*\n(?P<body>.*?)```", re.IGNORECASE | re.DOTALL)


@dataclass
class GeneratedArtifact:
    kind: str  # "html" | "markdown"
    title: str
    raw_content: str
    sanitized_content: str


def extract_artifact(llm_output: str, fallback_title: str) -> GeneratedArtifact | None:
    match = _FENCE_RE.search(llm_output)
    if not match:
        return None

    lang = match.group("lang").lower()
    body = match.group("body").strip()
    kind = "html" if lang == "html" else "markdown"

    title = fallback_title
    if kind == "markdown":
        heading = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        if heading:
            title = heading.group(1).strip()
    else:
        heading = re.search(r"<title>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
        if heading:
            title = heading.group(1).strip()

    sanitized = sanitize_html_artifact(body) if kind == "html" else body
    return GeneratedArtifact(kind=kind, title=title[:200], raw_content=body, sanitized_content=sanitized)
