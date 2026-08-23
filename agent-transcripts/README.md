# Agent transcripts

This project was built end-to-end by Claude (Claude Code), directed by the
candidate through a single conversational session, rather than transcribing
a separate "coding agent" run after the fact. `session-log.md` is a condensed,
chronological account of that build — decisions made, commands run, and
(per the assignment's explicit ask) **failed attempts and how they were
corrected**, written from the actual tool-call history rather than
reconstructed from memory afterward.

No secrets or API keys appear anywhere in this session (the demo was built
and tested entirely against Ollama in its unreachable/degraded state plus a
sqlite fallback, precisely so no credentials were ever needed to validate
the resilience paths) — so nothing was redacted; the log is unedited aside
from trimming raw command output for length.
