# PRD — The Lenny Growth Assistant

## 1. Forward Deployment Brief

### User and problem

**Primary user:** a PM, growth lead, or founder at a company evaluating this
internally — someone who has heard Lenny's Podcast covers exactly the
decision they're facing (activation vs. acquisition, pricing, PMF signals)
but doesn't want to scrub through a 90-minute episode to find it, and can't
verify a plain ChatGPT answer against what a guest *actually* said.

**Job to be done:** "Give me a specific, sourced answer to a product/growth
question, in the language of people who've actually done it — and let me
turn that into something I can ship (an essay, a doc, a one-pager) without
leaving this tool."

**Pain removed:** the search cost of finding the right 3-minute segment
across hundreds of hours of podcast content, and the trust cost of an
ungrounded LLM answer that sounds plausible but isn't traceable to a source.

### Success metric

Primary (product): **% of answered questions where the user does not
immediately re-ask a rephrased version of the same question** — a proxy for
"the grounded answer was actually useful," trackable from `messages` alone
(same session, next user turn, high text-similarity to the prior user turn).
Target: <15% re-ask rate once corpus coverage is reasonable.

Secondary (operational): **grounded-answer rate** — % of QA turns where
`grounded = true` (at least one retrieved chunk clears the similarity floor).
This is a leading indicator of corpus coverage gaps and is logged on every
turn (see `architecture.md` > Observability) so it can be tracked from day one
without waiting on the harder-to-measure re-ask metric.

### Assumptions

The client brief said "Lenny's Podcast transcripts" without specifying a
source, size, or license. Assumptions made to fill that gap:

1. **Data source**: the official free starter pack
   ([`LennysNewsletter/lennys-newsletterpodcastdata`](https://github.com/LennysNewsletter/lennys-newsletterpodcastdata)),
   not a scraped/unofficial archive — it's real, current, and has an explicit
   license rather than an ambiguous one.
2. **Demo corpus size**: 10 curated growth/PM-relevant episodes (~186k
   words), not all 50 free episodes or the full paid archive (313 episodes).
   Enough to demonstrate real multi-episode retrieval and cross-guest
   synthesis without ingestion/embedding time dominating the demo. The
   ingestion pipeline is not hardcoded to this subset — swapping in more
   episodes (including the full paid archive, same file format) is a
   `fetch_transcripts.sh --all` + `ingest.py` re-run, no code change.
3. **No user auth**: "user metadata" is a free-text label stored per session,
   not a real identity system. A take-home demo has one evaluator, not a
   multi-tenant user base; adding real auth would be premature scope for what
   this needs to prove.
4. **Single active model per session, not per-message**: the provider is a
   deployment-time toggle (env var + restart), not a per-message user choice,
   because the brief frames it as "let the evaluator switch the model," not
   "let end users pick a model." A UI toggle is a reasonable v2 (see Scope).
5. **"Grounded" means "from these transcripts," not "from Lenny's Newsletter
   posts too"** — newsletter essays are in the same source dataset but are
   out of scope for this build (see Scope) to keep ingestion/citation format
   uniform (podcast transcripts have speaker+timestamp structure; newsletter
   posts don't).

### Scope choices

**In scope:**
- Grounded conversational QA over podcast transcripts, with citations and an
  explicit "I don't have grounding for that" path.
- Ship 30 for 30 essay skill, encoded as a structured, checkable skill (not a
  one-off prompt) with an automated retry-on-validation-failure loop.
- Ad hoc Markdown/HTML artifact generation with an in-app, sandboxed viewer.
- Three-way LLM provider toggle (Anthropic / OpenAI / Ollama) with fallback
  and degraded-mode handling.
- Postgres+pgvector persistence for sessions, messages, transcripts, chunks,
  artifacts.
- Structured JSON logging, a `/health` endpoint, and a documented resilience
  story for every major failure mode named in the brief.

**Explicitly excluded** (and why):
- **User auth / multi-tenancy** — no product requirement stated it, and it's
  orthogonal to what's being evaluated (retrieval, grounding, agent
  architecture, artifact safety).
- **Streaming token-by-token responses** — meaningfully improves perceived
  latency but adds real complexity (SSE/WebSocket plumbing, partial-message
  persistence) for a take-home; the orchestrator returns one complete
  response per turn. Documented as the first thing to add post-demo.
- **Newsletter posts as a second corpus** — different structure (no
  speaker/timestamp), would need a separate chunking strategy; podcast
  transcripts alone already prove the RAG architecture.
- **Per-message model switching in the UI** — see Assumption 4.
- **Real content moderation / prompt-injection defense beyond artifact
  sandboxing** — the artifact security model (sanitization + sandboxed
  iframe) is real and load-bearing; broader adversarial-input hardening
  (jailbreak resistance, etc.) is out of scope for a v1 internal tool.
- **Alembic migrations** — one linear schema, no migration history to
  preserve yet; `db/bootstrap.py` does an idempotent `create_all`. Documented
  in `architecture.md` as the first thing to introduce if this grows past
  demo stage.

### Risks and trade-offs

| Risk | Mitigation / trade-off made |
|---|---|
| **Hallucination** | System prompt restricts QA to provided context only, instructs the model to say when context is insufficient rather than guess, and a similarity floor (`RETRIEVAL_MIN_SCORE`) forces the "not grounded" path when no chunk is actually relevant. Not a hard technical guarantee — a determined jailbreak could still get an ungrounded answer — but the default path is honest. |
| **Latency** | Small local Ollama models are slow for ~1,250-word essay generation. Mitigated with a generous `LLM_TIMEOUT_SECONDS` default and a chat UI that shows a typing indicator rather than appearing frozen; no server-side streaming (see Scope) means the user waits for the full response. |
| **Cost** | Ollama is free/local. Cloud providers (Anthropic/OpenAI) are pay-per-token; `LLM_MAX_OUTPUT_TOKENS` caps runaway generations, and the fallback chain (see `architecture.md`) avoids silently retrying a paid call in a loop on failure. |
| **Local-model quality** | An 8B local model grounds and cites less reliably than Claude/GPT-4-class models, especially on the Ship 30 essay's style requirements. `skills/ship30.py`'s validator + one automatic retry compensates partially; it's not a guarantee of a great essay from a small model, just a guardrail against an obviously-broken one. |
| **Data licensing** | The starter-pack license permits personal/non-commercial use and building projects on it, but forbids redistributing the raw dataset files. Solved by fetching transcripts at setup time (`scripts/fetch_transcripts.sh`) instead of committing them — see `data/README.md`. |
| **Unsafe artifact rendering** | LLM-generated HTML is untrusted by construction (possible prompt injection via retrieved transcript content). Two-layer defense: backend sanitization (strip remote scripts/stylesheets, `<base>`, meta-refresh, event-handler attributes; inject a CSP blocking outbound network requests) + a sandboxed iframe with `allow-scripts` only (no same-origin, no top-nav, no forms, no popups). Full writeup in `architecture.md` > Security. |
| **Retrieval drift on embedding-service outage** | If Ollama's embedding model is unavailable, the app falls back to a deterministic hash-based embedding rather than failing ingestion/retrieval outright. Explicitly lower quality (roughly keyword-ish matching); logged loudly (`embedding_fallback_hash`) so it's never a silent quality regression. |

## 2. Flows

**QA flow:** user sends a message → router classifies as `qa` (default) →
embed query → pgvector top-k retrieval → grounded? → answer with citations,
or explicit "not covered" message → both messages persisted.

**Ship 30 flow:** user asks for an essay → router matches ship30 keywords →
broader retrieval (2x top-k) → essay generated against the Ship 30 system
prompt → validated (word count, headings, bullets, bold, present) → one
automatic retry with specific feedback if invalid → saved as a Markdown
artifact, chat gets a short pointer message, not the full essay inline.

**Artifact flow:** user asks for a doc/page/artifact → router matches →
model asked to emit one fenced ` ```html ` or ` ```markdown ` block → parsed,
HTML sanitized → saved as an artifact → chat gets a pointer message; artifact
viewer fetches and renders it beside the chat.

**Provider-degraded flow:** any of the above, but the primary provider is
unreachable → optional configured fallback provider is tried → if that also
fails (or none configured), a clearly-labeled degraded message is returned
and still persisted as a normal assistant message (so the conversation
history stays coherent) with `provider: "none"`.

## 3. Acceptance criteria

- [ ] A fresh clone + `docker compose up` (+ ingestion command) produces a
      working chat at `localhost:5173` with **no cloud API key required**.
- [ ] Switching `LLM_PROVIDER` in `.env` and restarting changes which model
      answers, visibly reflected in the UI's status bar.
- [ ] A QA answer about a topic actually covered in the ingested transcripts
      includes at least one citation naming a guest and episode.
- [ ] A QA question clearly outside the corpus gets an explicit "not covered"
      answer, not a fabricated one.
- [ ] Asking for a Ship 30 essay produces a Markdown artifact rendered in the
      viewer, not dumped as raw text in the chat bubble.
- [ ] Asking for an HTML artifact renders inside a sandboxed iframe; a
      crafted attempt at a remote `<script src>` is stripped server-side
      (covered by `test_artifact_sanitizer.py`).
- [ ] Stopping Ollama mid-session causes chat requests to degrade gracefully
      (a clear message, HTTP 200, not a 500) — covered by `test_api.py`.
- [ ] `pytest` passes with no network access and no real Postgres (sqlite +
      unreachable Ollama), proving the resilience paths are real, not
      theoretical.

## 4. Implementation plan (as executed)

1. Source and license-check a real transcript corpus; build a
   fetch-not-commit pipeline respecting its license.
2. Backend skeleton: config (provider toggle), structured logging, DB models
   with a dialect-portable vector column (pgvector on Postgres, JSON
   fallback on sqlite for dependency-free tests).
3. RAG pipeline: turn-aware chunker → Ollama-embedding service with a
   deterministic fallback → pgvector retriever (with a pure-function ranking
   core that's unit-testable without a DB).
4. LLM provider abstraction (Anthropic / Ollama / OpenAI) + fallback wrapper
   with a degraded-mode response, never a raw 5xx.
5. Agent layer: rule-based skill router (documented reasoning: local-model
   tool-calling is unreliable, so routing is deterministic and retrieval
   always runs regardless of skill) → orchestrator dispatching to
   QA / Ship 30 / artifact generation.
6. Artifact pipeline: fence extraction → two-layer HTML sanitization
   (backend strip/CSP-inject + frontend sandboxed iframe) → Markdown via a
   renderer with raw HTML disabled.
7. API layer: sessions/chat/artifacts/health with structured error responses.
8. Automated tests across chunker, ranking, ship30 validation, sanitizer,
   generator, router, orchestrator (with a scripted fake provider), and API
   contract/resilience — 47 tests, run in CI with no external services.
9. Frontend: session sidebar, chat panel with citations/skill/provider
   badges, sandboxed artifact viewer, live status bar — typechecked and
   production-built.
10. Docs (this file, `design.md`, `architecture.md`, `README.md`) and
    `agent-transcripts/` logging how the build actually went, including
    corrections along the way.
