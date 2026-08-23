# The Lenny Growth Assistant

A full-stack, RAG-grounded conversational assistant over **Lenny's Podcast**
transcripts: ask product/growth questions, get answers cited back to the
episode and guest that said them, turn an answer into a Ship 30 for
30–style essay, or generate a Markdown/HTML artifact — all rendered in an
in-app viewer, not a separate tool.

Built as a Forward Deployed Engineer take-home. See also:
[`PRD.md`](./PRD.md) (problem, scope, risks) ·
[`design.md`](./design.md) (UI/UX) ·
[`architecture.md`](./architecture.md) (system design) ·
[`agent-transcripts/`](./agent-transcripts) (how this was actually built).

---

## Architecture at a glance

```
 ┌──────────────┐        ┌───────────────────────────────────────────────┐
 │   Frontend   │  HTTP  │                   Backend (FastAPI)            │
 │ React + Vite │◄──────►│                                                 │
 │  Chat + a    │        │  routes: /health /sessions /chat /artifacts    │
 │  sandboxed   │        │       │                                        │
 │  artifact    │        │       ▼                                        │
 │  viewer      │        │  AgentOrchestrator                             │
 └──────────────┘        │   ├─ router.py      (rule-based skill routing)│
                          │   ├─ retriever.py   (pgvector / cosine search)│
                          │   ├─ skills/ship30.py                        │
                          │   └─ artifacts/{generator,sanitizer}.py       │
                          │       │                                        │
                          │       ▼                                        │
                          │  LLM provider layer (llm/factory.py)          │
                          │   anthropic | ollama | openai  (env-toggled)  │
                          └──────────────┬──────────────────────────────┘
                                         ▼
                          ┌───────────────────────────────┐
                          │ Postgres + pgvector             │
                          │ sessions · messages · transcripts│
                          │ · chunks(embedding vector) · artifacts│
                          └───────────────────────────────┘
```

Full detail (schema, endpoints, ingestion flow, security model) is in
[`architecture.md`](./architecture.md).

## Prerequisites

- Docker + Docker Compose (recommended path), **or** Python 3.11+ and Node 20+
  for a no-Docker local run.
- [Ollama](https://ollama.com) installed and running natively on your host —
  this is the **mandatory** local-model path for the demo. Docker Compose
  reaches it via `host.docker.internal`; it is not run inside a container
  (see `docker-compose.yml` for why).
- Optional: an Anthropic and/or OpenAI API key, if you want to try the cloud
  provider toggle.

Pull the models the demo needs once:

```bash
ollama pull llama3.2:3b        # or any chat model that fits your machine
ollama pull nomic-embed-text   # embeddings for retrieval
ollama serve                   # if not already running as a service
```

`llama3.2:3b` is the default because it's what was actually verified
end-to-end on CPU-only hardware (see Troubleshooting below) — `llama3.1:8b`
also produces correct, grounded, well-cited answers, but was noticeably
slower per turn on a laptop CPU. If you have a GPU or beefier hardware,
`llama3.1:8b` (or larger) is a straight upgrade: set `OLLAMA_MODEL`
accordingly (see `.env.example`) and restart — nothing else needs to change.

## Quick start (Docker Compose)

```bash
cp .env.example .env
# .env already defaults to LLM_PROVIDER=ollama — no API key needed.

bash scripts/fetch_transcripts.sh   # pulls the demo transcript corpus (see data/README.md for why
                                     # this is a fetch step and not committed files)

docker compose up --build

# in another terminal, once `db` and `backend` are healthy:
docker compose exec backend python scripts/ingest.py
```

Then open **http://localhost:5173**. Backend API is at **http://localhost:8000**
(`/health`, interactive docs at `/docs`).

## Quick start (no Docker)

```bash
# 1. Postgres with pgvector. Easiest is a one-off container even if you skip
#    Compose for the app itself:
docker run -d --name lenny-pg -e POSTGRES_USER=lenny -e POSTGRES_PASSWORD=lenny \
  -e POSTGRES_DB=lenny_growth -p 5432:5432 pgvector/pgvector:pg16

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../.env.example .env   # edit DATABASE_URL if not using the container above
uvicorn app.main:app --reload --port 8000

# 3. Ingest transcripts (separate terminal)
bash ../scripts/fetch_transcripts.sh
cd backend && python scripts/ingest.py

# 4. Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

### Running without Postgres at all

Set `DATABASE_URL=sqlite+aiosqlite:///./dev.db` and skip the Postgres step
entirely. The app runs — sessions, messages, and chat all work — but
retrieval falls back to a Python-side cosine-similarity scan instead of
pgvector's indexed search (see `app/services/retriever.py`), and there's no
`vector` extension so this path is for quick local hacking, not for judging
retrieval quality or scale.

## Environment variables

See [`.env.example`](./.env.example) — every variable is documented there
with its default and whether it's required. The one you'll actually touch:

| Variable | What it does |
|---|---|
| `LLM_PROVIDER` | `ollama` (mandatory for this demo) \| `anthropic` \| `openai` |
| `LLM_FALLBACK_PROVIDER` | If set, used when the primary provider is unreachable, instead of a degraded canned reply |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Only needed if you switch `LLM_PROVIDER` to that provider |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` / `OLLAMA_EMBEDDING_MODEL` | Where Ollama lives and which models to use |

Switching providers is a restart, not a code change — flip `LLM_PROVIDER` in
`.env` and restart the backend. The active provider (and whether it's
currently reachable) is shown in the app's status bar.

## Running tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
```

47 tests, no network or real database required — sqlite + an intentionally
unreachable Ollama URL are used, so the resilience/fallback paths are
exercised for real rather than mocked away. See `backend/tests/` and the
**Tests** section of `architecture.md` for what's covered.

Frontend:

```bash
cd frontend
npm install
npm run typecheck   # strict TS, no `any` leaks
npm run build       # production build
```

A manual UI test plan (things to click through in a browser) is in
[`architecture.md` > Manual test plan](./architecture.md#manual-test-plan).

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `/health` shows `llm_reachable: false` | Ollama isn't running, or the model isn't pulled. Run `ollama serve` and `ollama pull <model>`. |
| Chat replies with "I couldn't reach the language model…" | Same as above — this is the intended degraded-mode message, not a crash. Check `/health`. |
| Ingestion says "0 transcripts" | Run `bash scripts/fetch_transcripts.sh` first — `data/transcripts/` is git-ignored on purpose (see `data/README.md`). |
| Every answer says "I don't have grounding for that" | Ingestion hasn't run yet, or Ollama's embedding model isn't pulled (`ollama pull nomic-embed-text`) so retrieval degraded to the low-quality hash fallback — still functional, just weaker. Check backend logs for `embedding_fallback_hash`. |
| `docker compose up` backend can't reach Ollama | On Linux, confirm `extra_hosts: host.docker.internal:host-gateway` took effect (`docker compose config`), or set `OLLAMA_BASE_URL` to your host's LAN IP. |
| Chat requests time out / degrade even though Ollama is running | Measured on real hardware during development: a CPU-only laptop with no GPU does ~3-5 tokens/sec, and a grounded QA turn's ~1,700-token retrieved context can take 2-4+ minutes end to end — slower than you'd expect from "a small local model." Raise `LLM_TIMEOUT_SECONDS` further, lower `RETRIEVAL_TOP_K` (shorter prompts), or switch `OLLAMA_MODEL` to something smaller like `llama3.2:3b`. This is a hardware-speed issue, not a correctness bug — retrieval/grounding still work correctly during the wait. |
| Postgres connection errors | Confirm `db` is healthy (`docker compose ps`) before the backend starts — Compose already waits on `service_healthy`, but a first-run image pull can be slow. |
| HTML artifact looks blank / stripped-down | Intentional — see `architecture.md` > Security for the sandboxing/sanitization rules the artifact viewer enforces. |

## Repository layout

```
backend/           FastAPI app, agent/orchestrator, RAG pipeline, tests
frontend/          React + Vite chat UI and artifact viewer
data/              transcripts (fetched, git-ignored) + corpus manifest
scripts/           fetch_transcripts.sh
agent-transcripts/ coding-agent session logs for this build (see its README)
PRD.md  design.md  architecture.md
```
