# architecture.md

## Component boundaries

```
backend/app/
├─ config.py            single Settings object; every knob is an env var
├─ logging_config.py     structured JSON logging
├─ db/                   models, dialect-portable Vector type, bootstrap
├─ services/
│  ├─ chunker.py          turn-aware transcript splitting (pure function)
│  ├─ embeddings.py       Ollama embeddings + deterministic hash fallback
│  ├─ ingestion.py        markdown -> chunks -> embeddings -> DB (idempotent)
│  └─ retriever.py        pgvector search + a pure cosine-ranking core
├─ llm/                  ChatProvider interface + anthropic/ollama/openai
│                        implementations + FallbackChatProvider wrapper
├─ agent/
│  ├─ router.py           rule-based skill classification
│  ├─ prompts.py          system prompt templates
│  └─ orchestrator.py     ties routing + retrieval + generation + skills together
├─ skills/ship30.py       Ship 30 principles, prompt builder, validator
├─ artifacts/             fence extraction + HTML sanitizer
└─ api/                  FastAPI routes + request/response schemas
```

Each layer only depends on the ones below it in this list; `agent/` is the
only place that knows about *all* of retrieval, generation, and skills at
once. `api/routes/*` never talks to `llm/` or `services/` directly — it goes
through `AgentOrchestrator`, so the HTTP layer stays a thin translation of
requests/responses and all the actual product behavior lives in one place.

## Database schema

```sql
sessions(id, title, user_label, created_at, updated_at, meta jsonb)
messages(id, session_id -> sessions, role, content, provider, skill,
         citations jsonb, created_at)
transcripts(id, slug, title, guest, published_at, source_url, word_count,
            ingested_at)
chunks(id, transcript_id -> transcripts, chunk_index, content, token_count,
       embedding vector(768))
artifacts(id, session_id -> sessions, message_id -> messages, kind, title,
          content, raw_content, created_at)
```

Notes:
- `chunks.embedding` is `pgvector`'s `vector(768)` on Postgres, and a JSON
  array on SQLite (`db/types.py`'s `Vector` `TypeDecorator`) — SQLite is only
  used for dependency-free tests and quick local hacking (see README), never
  for a real deployment, so the fallback only needs to keep the *interface*
  identical, not the performance characteristics.
- `messages.citations` is denormalized JSON (not a join table to `chunks`)
  because citations are immutable once a message is sent — they're a record
  of what informed that specific answer, not a live relationship that should
  update if a chunk is later re-ingested.
- `artifacts.raw_content` keeps the pre-sanitization HTML the model actually
  produced, separately from `content` (what's actually served to the
  frontend). This is an audit trail: if sanitization ever strips something
  it shouldn't, or someone wants to see exactly what the model tried to do,
  it's in the DB, not lost.
- No `Alembic`. One linear schema, bootstrapped idempotently
  (`db/bootstrap.py`: `CREATE EXTENSION IF NOT EXISTS vector` +
  `create_all` + an `IF NOT EXISTS` HNSW index). If this project grew past
  demo stage, introducing real migrations would be the first infra change —
  called out explicitly rather than silently deferred.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | DB reachability, active LLM provider + reachability, embedding backend reachability |
| POST | `/sessions` | create a session (`title`, `user_label` optional) |
| GET | `/sessions` | list sessions, most recently updated first |
| GET | `/sessions/{id}` | fetch one session |
| GET | `/sessions/{id}/messages` | full message history for a session |
| POST | `/chat` | send a message, get back the assistant's message + artifact summary (if any) + `grounded`/`degraded` flags |
| GET | `/artifacts/{id}` | fetch full artifact content for the viewer |

All errors are structured: `{"error": {"code": <int>, "message": <str>}}` —
FastAPI's default validation errors (422) keep their own shape (a list of
field errors), which is standard and something any HTTP client already knows
how to parse; only *our* raised errors (404, 502, 500) are normalized through
the exception handlers in `main.py`. A 500 never leaks a stack trace to the
client; it's logged server-side (`unhandled_exception`) and the client gets
a generic message.

`POST /chat` request/response contract:

```jsonc
// request
{ "session_id": "uuid", "message": "non-empty string, max 8000 chars" }

// response
{
  "message": { "id", "role": "assistant", "content", "provider", "skill",
               "citations": [...], "created_at" },
  "artifact": { "id", "kind", "title", "created_at" } | null,
  "grounded": true | false,
  "degraded": true | false
}
```

## Ingestion / retrieval flow

1. `scripts/fetch_transcripts.sh` clones the official Lenny's Data starter
   pack and copies a curated subset (or `--all`) into `data/transcripts/`
   (git-ignored — see `data/README.md` for the licensing reason).
2. `scripts/ingest.py` → `services/ingestion.py`:
   - parses each file's YAML frontmatter (title, guest, date, source URL,
     word count) + body,
   - **re-running ingestion on a file that's already been ingested deletes
     and re-inserts that transcript's chunks** — idempotent by construction,
     no separate "refresh" code path,
   - `services/chunker.py` splits the body on `**Speaker** (timestamp):`
     turn boundaries (falls back to paragraph splitting for non-conforming
     text) and greedily packs whole turns into ~280-token chunks with a
     ~40-token overlap, so a chunk never cuts a sentence mid-thought and
     citations can name a real speaker,
   - `services/embeddings.py` embeds each chunk via Ollama's
     `nomic-embed-text` (or a deterministic hash-based fallback if Ollama's
     unreachable — logged loudly, never silent),
   - chunks are written to Postgres with their embeddings.
3. At query time, `services/retriever.py`:
   - on Postgres: pushes the search down to pgvector via `embedding <=>
     :query_vector` (cosine distance), indexed with HNSW (created at
     bootstrap, no pretraining/`lists` tuning needed unlike IVFFlat),
   - on SQLite (tests / no-Docker dev): pulls all chunks into Python and
     ranks them with a **pure function**, `rank_chunks_by_similarity`, that
     has no DB or I/O dependency — this is what makes retrieval *ranking
     logic* unit-testable without a database at all (see `test_retriever_
     ranking.py`).
4. `AgentOrchestrator` decides "grounded" as `max(chunk.score) >=
   RETRIEVAL_MIN_SCORE` (default `0.15`) and threads that into which system
   prompt is used and whether citations are attached to the persisted
   message.

## Agent routing

Routing is **rule-based** (`agent/router.py`: keyword/regex matching against
the user's message), not an LLM tool-call decision, for one concrete reason:
the demo's mandatory path is a small local Ollama model, and small models'
function-calling reliability is inconsistent enough that a misrouted request
is a worse failure mode for a take-home demo than a slightly blunt keyword
match. This is a real trade-off, not a shortcut — a larger hosted model
(Claude/GPT-4-class) could route more contextually via tool-calling, and if
this app's primary provider were always Anthropic, that would likely be the
better design. Because the brief requires the local path to work well too,
routing had to be reliable on the weakest supported model, which pushed
toward rules.

This means the agent layer is not built on the Anthropic Claude Agent SDK
(the brief's other named option, Pi Coding Agent, isn't a published package
this could be evaluated against). That was verified hands-on, not assumed:
`claude-agent-sdk` was installed and its public API inspected directly
(`agent-transcripts/session-log.md` § 10.8). It turned out to be the Claude
Code CLI's own agent runtime — `query()`/`ClaudeSDKClient` spawn a `claude`
CLI subprocess and manage it through a session-store/permission-mode/hook/
subagent/sandbox model built for autonomous coding agents, not a
lightweight "call an LLM with tools" library suited to a request/response
chat backend. Wiring it into this API would mean spawning a CLI process per
chat turn and adopting a permission/sandbox model with no bearing on
answering product questions — a mismatch, not a missing nice-to-have. (It
also silently upgraded `starlette` to a version incompatible with the
pinned FastAPI on install, which was reverted immediately.) The custom
orchestrator + plain Anthropic Messages API remains the deliberate choice
for all three providers, including Anthropic.

**Retrieval always runs first, regardless of which skill the message routes
to.** This means even a misrouted message still gets grounded context rather
than an ungrounded fallback — the router only decides *how* to use the
retrieved context (answer directly / write an essay from it / turn it into a
doc), not *whether* to retrieve.

Precedence when a message could match more than one skill: explicit
artifact/HTML intent > explicit Ship 30/essay intent > default QA. ("Turn
this essay into an html artifact" routes to `artifact`, not `ship30_essay`,
because the more specific, more consequential intent — "make me a renderable
thing," which triggers the sanitization pipeline — should win over a looser
"essay" mention.)

## Model / provider toggle

`LLM_PROVIDER` (env var) selects `anthropic | ollama | openai` at process
start (`llm/factory.py:build_provider`). `LLM_FALLBACK_PROVIDER` optionally
names a second provider to try if the primary raises
`LLMUnavailableError` (`FallbackChatProvider`). If both fail (or no fallback
is configured), the request still returns HTTP 200 with a clearly-labeled
degraded assistant message (`provider: "none"`) rather than a 5xx — a chat
app that 500s because a model is down is a worse experience than one that
says so in-band. The active provider and its live reachability are exposed
on `/health` and rendered in the frontend's status bar at all times (see
`design.md` > Principles).

Embeddings are **not** tied to the chat provider toggle — they always go
through Ollama (`nomic-embed-text`) regardless of which chat model is
active, because retrieval quality shouldn't change depending on whether
you're demoing with Claude or a local model, and neither Anthropic nor most
local chat models expose a first-class embeddings endpoint anyway.

## Security: artifact rendering

Generated HTML is untrusted by construction — it's LLM output, and the LLM's
context includes retrieved transcript text, which is a real (if narrow)
prompt-injection surface. Two independent layers:

1. **Backend (`artifacts/sanitizer.py`)** strips, before anything is stored
   or served: `<base>` (relative-URL hijacking), `<meta
   http-equiv="refresh">` (forced navigation), remote `<script src=...>` and
   `<link rel="stylesheet">` (loading code/styles we didn't generate), and
   `on*=` event-handler attributes (belt-and-braces; the sandbox below
   already blocks their worst effects). It also injects a
   `Content-Security-Policy` meta tag: `default-src 'none'; script-src
   'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src
   'none'; frame-src 'none'; form-action 'none'`.
2. **Frontend (`ArtifactViewer.tsx`)** renders HTML in `<iframe sandbox=
   "allow-scripts" srcDoc={...}>` — deliberately *without*
   `allow-same-origin`, `allow-top-navigation`, `allow-popups`, or
   `allow-forms`. Inline scripts still execute (interactive demos work), but
   the document gets a unique opaque origin: it cannot read this page, its
   cookies, or its `localStorage`, cannot navigate the top window, cannot pop
   up windows, and cannot submit forms anywhere.

**What's explicitly permitted:** inline `<script>`/`<style>` execution,
local rendering of the artifact's own markup, data: URI images.
**What's blocked:** any outbound network request from inside the artifact
(the CSP's `connect-src 'none'`/`frame-src 'none'` catches exactly what the
sandbox attribute alone does not), remote script/style loading, top-frame
navigation, popups, form submission, and any access to the parent page's
DOM/cookies/storage.

**Residual/accepted risk:** the sandbox attribute does not stop the
artifact's own inline script from doing CPU-bound or visually disruptive
things *within its own iframe* — that's an accepted trade-off for "the demo
looks and works like Claude Artifacts," not a gap that was missed.

**Markdown artifacts have no HTML-injection surface at all**: they're
rendered via `react-markdown` with no `rehype-raw` plugin, so raw HTML
embedded in generated Markdown renders as inert escaped text, never as
markup. This is a "safe by construction" choice, not a sanitizer that could
be forgotten on a future change.

## Deployment topology

```
docker-compose.yml
├─ db        pgvector/pgvector:pg16, healthchecked before backend starts
├─ backend   FastAPI, connects to db by service name; connects to Ollama on
│            the HOST via host.docker.internal (extra_hosts: host-gateway
│            for Linux) — Ollama is not itself containerized, since pulling
│            multi-GB models into a fresh container on every `up` is worse
│            for a take-home demo than "run Ollama the normal way"
└─ frontend  Vite build served via `serve`, talks to backend over HTTP
```

`data/transcripts/` is bind-mounted read-only into the backend container at
`/data/transcripts` — chosen to match where `scripts/ingest.py`'s default
path resolves *inside* the container (three directories up from
`scripts/ingest.py`, same relative structure as the repo checkout), so
ingestion works identically in and out of Docker with no "am I in a
container" branch in application code.

## Observability

Every log line is one JSON object (`logging_config.py`) with at minimum
`ts`, `level`, `logger`, `message`, plus structured `extra=` fields specific
to the event — e.g. `agent_routed` carries `skill`, `grounded`,
`retrieved_chunks`; `primary_provider_failed` carries `provider` and
`error`; `embedding_fallback_hash` carries `reason` and `model`. This is
deliberately greppable-by-field (`jq 'select(.logger=="app.agent.
orchestrator")'`) rather than prose, so an operator can answer "was it the
model, the retriever, the DB, or the renderer?" from logs alone without
attaching a debugger.

`/health` reports four independent signals (DB reachability, LLM provider
reachability, embedding backend reachability, overall status) rather than a
single boolean, because "the app is down" and "Ollama is down but the app
and DB are fine" require different responses from whoever's on call.

## Resilience — failure modes and behavior

| Failure | Behavior |
|---|---|
| Missing/invalid API key for the active cloud provider | `health_check()` returns false; a chat request raises `LLMUnavailableError` caught by `FallbackChatProvider`, which returns a degraded-but-labeled message instead of crashing |
| Ollama unreachable | Same fallback path; additionally, ingestion/embedding falls back to a deterministic hash embedding rather than failing ingestion outright |
| Model timeout | `httpx`/`anthropic` timeout exceptions are caught and re-raised as `LLMUnavailableError` with a specific message, not a generic 500 |
| Empty retrieval results | `grounded=False`; QA uses `NO_CONTEXT_SYSTEM_PROMPT` instead of guessing |
| Database connection failure | `/health`'s `db_reachable` flips to false without crashing the health check itself (caught and logged); a genuinely down DB will surface as 500s on session/chat endpoints, logged via `unhandled_exception` |
| Model ignores the artifact fence-format instruction | Orchestrator falls back to treating the whole reply as a Markdown artifact rather than failing the request (`test_artifact_skill_falls_back_to_markdown_when_model_ignores_fence_format`) |
| Ship 30 essay fails the style validator | One automatic retry with specific, targeted feedback; if still invalid, it ships anyway with the issues noted in the chat reply rather than looping indefinitely |

## Tests

`backend/tests/` — 47 tests, all runnable offline (sqlite + an unreachable
Ollama URL, see `tests/conftest.py`):

- `test_chunker.py` — turn-aware splitting, budget respecting, paragraph
  fallback, empty input.
- `test_retriever_ranking.py` — the pure cosine-similarity/top-k function,
  independent of any database.
- `test_ship30_skill.py` — validator catches missing headings/bullets/bold
  and out-of-range word counts; a well-formed essay passes.
- `test_artifact_sanitizer.py` — every stripped construct (remote script,
  base tag, meta-refresh, event handlers, remote stylesheet) and CSP
  injection, including edge cases (no `<head>`, no `<html>` at all).
- `test_artifact_generator.py` — fence extraction for both kinds, title
  inference, sanitization applied only to HTML, graceful `None` when the
  model doesn't follow the format.
- `test_router.py` — skill classification and precedence.
- `test_agent_orchestrator.py` — full orchestrator behavior with a scripted
  fake `ChatProvider` (no network): grounded vs. not-grounded QA, Ship 30's
  retry-on-invalid-draft loop actually retrying (and *not* retrying when the
  first draft is fine), artifact extraction + sanitization end-to-end,
  fence-format fallback, and that a provider outage propagates as
  `LLMUnavailableError` rather than an unhandled crash.
- `test_api.py` — API contract against the real app wiring: session
  creation, 404 on unknown session, 422 on empty message, and — run against
  a genuinely unreachable Ollama, not a mock — that `/chat` still returns
  200 with a degraded, clearly-labeled message and persists both turns.

### Manual test plan

Run this against `docker compose up` with Ollama actually running and
transcripts ingested. **Items 1, 2, 3, 6, and 7 were actually run in a real
browser** (not just curl) during development — see
`agent-transcripts/session-log.md` § 10.7 for what that found and fixed
(a citation-dedup bug and a missing artifact-restore-on-session-switch
feature, both fixed with tests). Items 4, 5, 8, 9, and 10 below were
exercised at the API level (automated tests + curl) but not re-confirmed
pixel-by-pixel in a browser — worth a final pass before considering the UI
fully signed off:

1. **Cold start**: load the app with no existing sessions → a session is
   auto-created, empty-state copy is visible, status bar shows
   `ollama` / reachable.
2. **Grounded QA**: ask something clearly covered by the ingested corpus
   (e.g. "What did Elena Verna say about activation vs acquisition?") →
   answer includes a Sources list naming Elena Verna.
3. **Out-of-corpus QA**: ask something unrelated (e.g. "What's the weather
   in Tokyo?") → assistant explicitly says it's not covered, no fabricated
   answer, no Sources block.
4. **Follow-up**: ask a pronoun-dependent follow-up ("what else did she say
   about that?") in the same session → answer stays on-topic, proving
   session context is preserved.
5. **Ship 30 essay**: ask "turn that into a ship 30 for 30 essay" → chat
   gets a short pointer message; artifact panel shows a full Markdown essay
   with headings/bullets/bold.
6. **HTML artifact**: ask for "an html landing page summarizing this" →
   artifact panel renders it in an iframe; open devtools and confirm the
   iframe has `sandbox="allow-scripts"` with no `allow-same-origin`.
7. **New session / switching sessions**: click "+ New chat" → sidebar shows
   both sessions, switching between them shows the right history. If the
   session you switch to previously generated an artifact, it's restored
   (`GET /sessions/{id}/artifacts/latest`); a session with no artifacts
   shows the empty state.
8. **Provider outage**: stop `ollama serve`, send a message → status bar
   flips to "unreachable"; chat shows the degraded message, not a spinner
   forever or a browser error page. Restart Ollama, send again → normal
   grounded responses resume without restarting the backend.
9. **Responsive check**: narrow the browser below ~900px → sidebar
   collapses to a short strip, chat and artifact stack vertically instead of
   overlapping or clipping.
10. **Keyboard-only pass**: tab through session list, composer, and (with an
    artifact open) its close button — every control is reachable and shows a
    visible focus ring; Enter sends a message, Shift+Enter adds a newline.
