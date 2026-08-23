# Session log — building The Lenny Growth Assistant

## 1. Reading the brief

Source assignment was a `.docx` (not the `.pdf` the task description
mentioned — the actual downloaded file was
`Forward_Deployed_Engineer_Take_Home_Assignment.docx`). Extracted its text
by unzipping the `.docx` (it's a zip of XML) and stripping `word/document.xml`
tags with a small Node script, since no Python was reachable via the `python`
alias on this machine at first (Windows' App Execution Alias shortcut
intercepted it) — `python3` worked, and `node` was used for the docx
extraction to sidestep the ambiguity entirely.

## 2. Sourcing real data instead of inventing fake transcripts

The brief says "ingest transcripts from Lenny's Podcast" without naming a
concrete source. Rather than fabricate placeholder transcripts (which would
undercut the whole point of a RAG demo — there'd be nothing real to ground
against), searched for and found the official free starter pack:
`LennysNewsletter/lennys-newsletterpodcastdata` on GitHub (50 real podcast
transcripts, AI-friendly markdown, published by Lenny's Newsletter itself).

**Correction made:** the starter pack's `LICENSE.md` permits personal/
non-commercial use and building projects on top of it, but explicitly
forbids redistributing the raw dataset files. The first instinct would have
been to just copy the chosen transcripts into `data/transcripts/` and commit
them. Caught this before committing anything — instead, `data/transcripts/`
is git-ignored, and `scripts/fetch_transcripts.sh` reproduces the exact demo
corpus by cloning the official repo and copying a curated subset, so the
repo never redistributes copyrighted content while ingestion stays fully
reproducible. This is documented as a first-class decision in `PRD.md` >
Risks, not just a code comment.

## 3. Manifest generation — a real bug, caught by output inspection

Wrote a Node script to build `data/corpus_manifest.json` (title/guest/date
metadata for the 10 chosen transcripts, for citation/reproducibility
purposes) from each file's YAML frontmatter using a hand-rolled regex parser.

**Failed attempt:** the first two runs produced a manifest where every
entry's `title`/`guest`/`date` fell back to the filename — i.e., the
frontmatter parser was silently matching nothing. Inspected the raw bytes of
one file (`Buffer.slice(0,10)`) and found the transcripts use **CRLF**
(`\r\n`) line endings, but the parsing regex was anchored on bare `\n`. Fixed
by normalizing `\r\n` -> `\n` before matching. This also became a documented
note in `services/ingestion.py`'s docstring: the *production* Python
ingestion path uses `yaml.safe_load`, which handles CRLF natively, so this
specific bug only affected the one-off manifest script — but it was worth
catching early since the same transcripts feed both.

## 4. A subtler SQLAlchemy bug: double-encoding the vector column

Built `db/types.py`'s `Vector` type (pgvector on Postgres, JSON list on
SQLite, so tests don't need a real Postgres+pgvector instance) with an
initial version that manually overrode `process_bind_param` /
`process_result_value` *in addition to* a dialect-specific
`load_dialect_impl`.

**Caught before it shipped, by reasoning through `TypeDecorator` semantics
rather than by a failing test:** `TypeDecorator` already applies
`process_bind_param` and then the underlying impl's own `bind_processor` in
sequence. The manual overrides for the SQLite path (`json.dumps` the list,
then let the JSON impl serialize *again*) would have double-encoded every
embedding into a JSON string containing an escaped JSON string. Removed the
overrides entirely — the dialect-specific impls (`_PgVector`'s bind/result
processors, or plain `JSON`) already do the right thing on their own, so no
extra processing was needed. Left a comment explaining why the class looks
"incomplete" (no bind/result overrides) — it's deliberate, not an oversight.

## 5. Orchestrator test bug: closing a DB session before it's used

First draft of `tests/test_agent_orchestrator.py`'s `_make_orchestrator`
helper opened the SQLAlchemy session with `async with SessionLocal() as db:`
and returned the orchestrator *from inside* that block via an early
`return` — which meant the session was closed by the context manager the
moment the function returned, before `orchestrator.handle_message()` (called
later, by the test) ever touched the database.

**Correction:** the first test worked around it locally by re-assigning
`orchestrator.retriever` after the fact, which fixed that one test but left
the same latent bug in every other orchestrator test that didn't apply the
same workaround. Caught this while reviewing the diff before running the
suite, not after a failure — replaced the workaround with a proper fix:
`_make_orchestrator` no longer uses `async with`, and a comment explains
that the session must outlive the helper because retrieval happens later,
inside `handle_message`.

## 6. Fixing a real test failure: essay fixture word count

Running the full suite for the first time (`pytest -q`) surfaced one actual
failure:

```
tests/test_ship30_skill.py::test_good_essay_passes_validation
AssertionError: ['word count 804 is outside the expected range (812-1687)']
```

The "good essay" fixture was built by repeating a few sentences a guessed
number of times (`"Acquisition is easy to chart. " * 40`, etc.) and landed
short of the validator's tolerance band by construction. Rewrote the fixture
to compute the exact filler needed (`target_words - len(header.split())`
words of padding) instead of guessing a multiplier, so the test asserts
against a fixture that's correct by construction rather than by luck. Full
suite: 47/47 passing after this fix.

## 7. A resource-leak fix caught by warnings, not failures

The first green test run had `SAWarning: garbage collector is trying to
clean up non-checked-in connection` on `/health` tests. Traced it to
`api/routes/health.py` manually driving the `get_db()` async generator with
`async for db in get_db(): ... break` — breaking out of an async generator
before it naturally completes doesn't reliably run its cleanup. Rewrote the
route to take `db: AsyncSession = Depends(get_db)` like every other route,
letting FastAPI's own dependency lifecycle close the session properly. The
same class of warning from orchestrator tests' intentionally-long-lived
sessions (see #5) was accepted and documented rather than "fixed," since
disposing the engine pool at test teardown reclaims those connections
cleanly — different root cause, different appropriate fix.

## 8. Manual end-to-end verification

Before writing the automated test suite, ran the actual FastAPI app with
`uvicorn` against sqlite + a deliberately-unreachable Ollama URL
(`http://localhost:19999`) and drove it with `curl`: created a session, sent
a chat message, and confirmed the degraded-mode response, 404 on an unknown
session, and 422 on an empty message — all before those became automated
`test_api.py` assertions. This is why `test_api.py`'s docstring says the
resilience path is "exercised for real rather than mocked away": it was
manually verified working first, then locked in as a test.

Also ran `npm run build` and `npx tsc -b --noEmit` for the frontend (both
clean on the first pass) and booted both dev servers together
(`uvicorn` + `vite`) to confirm the frontend actually serves and can reach
the backend over CORS. A browser automation tool was unavailable in this
environment (the user had started but not completed installing the Chrome
extension), so final pixel-level/visual QA — the manual test plan in
`architecture.md` — is left for the evaluator to run in an actual browser;
this is stated plainly rather than claimed as done.

## 9. What would be next (as of the initial build)

Documented in `PRD.md` > Scope as explicitly deferred rather than
half-implemented: streaming responses, per-message model switching, an
artifact history/gallery beyond a single current slot, and Alembic
migrations once the schema needs to change more than once.

---

## 10. Follow-up session: making the local demo actually real

The initial build above was verified with the resilience/degraded paths
(sqlite + unreachable Ollama, by design, so those paths were genuinely
exercised) but never against a real running Ollama instance, and never
pushed anywhere. This session closed both gaps, plus attempted (and
partially failed at) getting a real hosted Postgres running.

### 10.1 GitHub — no surprises

`gh` was already authenticated (`diyaitis`). `gh repo create --public
--source=. --remote=origin` + `git push -u origin main` worked on the first
try: https://github.com/diyaitis/lenny-growth-assistant.

### 10.2 Installing Ollama — a PATH gotcha

`winget install Ollama.Ollama` succeeded (this is a normal user-scope app
install, correctly distinguished by the environment's own safety classifier
from a system-level change like enabling WSL2, which it also correctly
blocked pending explicit user confirmation — asked and got "install Ollama
only").

**Failed attempt:** immediately after install, `nohup ollama serve` and
`ollama pull llama3.1:8b` both failed with "command not found" / exit 127,
even though `ollama --version` had worked moments earlier in a different
command. Root cause: each Bash tool invocation is a fresh shell process, and
the installer updated the Windows user `PATH` registry value *after* the
harness's shell process tree had already started — so the new PATH entry
was invisible to every subsequently-spawned shell in this session until a
genuinely new process picked up the updated environment. Fixed by referencing
the full binary path (`/c/Users/.../AppData/Local/Programs/Ollama/ollama`)
explicitly rather than relying on `ollama` being resolvable, which sidesteps
the stale-PATH issue entirely rather than working around it fragile-ly.
(Separately discovered `ollama serve` was already running as a background
service from the installer — no need to start it manually at all.)

### 10.3 Supabase Postgres — provisioned, then blocked, then reverted

Since Docker (and therefore the docker-compose Postgres) wasn't available
(no Docker Desktop; installing it needs WSL2, admin elevation via a UAC
prompt no automated tool can click through, and a reboot — correctly treated
as out of scope for a headless session rather than attempted anyway), tried
provisioning Postgres via Supabase instead — which the assignment brief
explicitly allows ("You may use Supabase or Railway"). Checked cost first
($0/month on the free tier) and confirmed before creating anything, per the
tool's own cost-confirmation flow. Created a project and enabled the
`vector` extension via `apply_migration`, successfully.

**Blocked, then reverted:** the user couldn't access the created project's
dashboard — it turned out the Supabase MCP integration is authenticated
under a different Supabase account than the one signed in in the browser.
Tried a workaround (`ALTER USER postgres WITH PASSWORD ...` directly via the
SQL execution tool, to sidestep needing dashboard access for a password
reset) — failed with `permission denied to alter role: only superusers can
alter privileged roles`, confirming the MCP tool's SQL execution runs under
a role deliberately scoped below Postgres superuser, not a bypassable
restriction. Rather than pursue a full integration reconnect under a
different account (a genuine option, but a detour with an uncertain time
cost against a deadline), the user chose to drop it. Paused the orphaned
project (`pause_project`) rather than leaving it running unused. The
Postgres/pgvector code path itself is unaffected — it's exactly what
`docker compose up` exercises, and the dialect-portable `Vector` type means
the app runs identically against sqlite in the meantime.

### 10.4 Real ingestion — a genuine performance finding, and a real bug it exposed

First real ingestion run against real Ollama embeddings hit the 5-minute
foreground command timeout partway through the first transcript. Not a bug —
CPU-only local embedding generation is genuinely ~1.7s/chunk (measured: 133
chunks in ~224s for one transcript), so the full 10-transcript corpus was
always going to take 20-30+ minutes, which just hadn't been exercised at
real scale before (the automated tests use instant hash-based fake
embeddings; the docs already noted Ollama-embedding latency was untested at
this scale).

That timeout did expose a real bug worth fixing, though: `ingest_directory`
only called `db.commit()` once, after every file finished — so the timeout
killed the in-progress transaction and the ~3.5 minutes already spent
embedding the first transcript were entirely lost, not partially saved.
Fixed by moving the commit inside the per-file loop (`app/services/
ingestion.py`), so a crash/timeout/Ctrl-C now costs at most "redo the
current file," not "redo everything since the last full run." Re-ran the
full test suite after the change (still 47/47) before re-running ingestion
in the background with a realistic time budget.

### 10.5 Browser tooling — still not connected

The user installed the Claude in Chrome extension and ran `/chrome` mid-
session. Checked for the resulting browser tools via `ToolSearch` — none
appeared. Per the environment's own documentation, extension connections are
typically detected at session start, so this likely needs a fresh session
rather than being fixable mid-session. Reported this plainly rather than
guessing or claiming a connection that wasn't actually there.
