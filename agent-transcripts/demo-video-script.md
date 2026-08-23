# Demo video script (2–3 minutes)

Target runtime: ~2:30. Camera on throughout per the assignment's requirement.
Bullet points, not a word-for-word script — talk naturally.

**Real timing, measured live on this machine with `llama3.2:3b` (CPU only,
no GPU):** a grounded QA answer took ~55s once the model was warm; the Ship
30 essay took the full several minutes (long-form generation is genuinely
slow on CPU). **Don't wait on camera for these.** Either: (a) send the
prompt, say your talking points while it's "thinking" off to the side, and
cut the dead air in editing, or (b) pre-generate the responses in the same
session just before recording (same session ID, same warm model) and
re-send the identical prompt on camera — Ollama keeps the model loaded for
a few minutes, so a repeat prompt against a warm model is much faster than
the first cold one.

## 1. The problem (≈30s)

- "Lenny's Podcast has 300+ episodes of product and growth advice, but
  finding the specific 3-minute answer to your question means scrubbing
  through hours of audio — or asking ChatGPT and getting a plausible-sounding
  answer you can't actually verify against what a guest said."
- "I built The Lenny Growth Assistant: a RAG chat app that answers product/
  growth questions grounded in real transcripts, cites who said it, and can
  turn an answer into a Ship 30 for 30 essay or a rendered doc — all inside
  one app."

## 2. Show the product (≈70s)

Live screen share, `localhost:5173` open:

- Point at the status bar: "This is running on Ollama, a local model —
  that's the mandatory path for this demo, no API key needed." (reachability
  dot green, model name visible)
- Ask a grounded question, e.g. **"What did Elena Verna say about activation
  vs. acquisition?"** → let it answer, then point at the **Sources** list
  under the answer: "It's citing the actual guest and episode, not just
  making something up."
- Ask an out-of-corpus question, e.g. **"What's the weather in Tokyo?"** →
  point out the assistant explicitly says it's not covered instead of
  guessing: "This is the grounding guarantee — no fabricated answers when the
  transcripts don't support one."
- Say **"turn that into a ship 30 for 30 essay"** → the artifact panel opens
  with a full formatted Markdown essay. "This isn't just an unstructured
  prompt — there's an actual skill behind it with Ship 30 principles encoded,
  and a validator that checks word count, headings, and bold emphasis, and
  retries once if the draft misses."
- Ask for **"an html page summarizing this"** → point at the rendered
  artifact: "This renders in a sandboxed iframe — the model's HTML output is
  treated as untrusted and can't reach outside its sandbox or make network
  calls, since it's LLM-generated content."

## 3. One technical trade-off (≈40s)

Pick ONE of these (the first is the freshest/most concrete — it's a real
bug I hit and fixed while testing this exact build, not a hypothetical):

- **Local-model latency forced real config changes, and exposed a real bug**:
  "When I actually ran this against real Ollama, an 8-billion-parameter
  model was too slow on CPU-only hardware — a single answer's prompt
  processing alone took minutes. I measured it, switched the default to a
  smaller 3B model, and had to raise timeouts and cap token budgets based on
  real numbers, not guesses. That process actually surfaced a real bug: when
  a request timed out, the app was wrapping its own 'model unavailable'
  error message inside a Ship 30 essay artifact instead of just failing
  cleanly — so I fixed it to fall back to a plain error message with no
  artifact at all, and added a regression test for it."
- **Rule-based routing over LLM tool-calling**: "I route which skill handles
  a message — plain Q&A, essay, or artifact — with keyword rules instead of
  letting the model decide via tool-calling. Small local models are
  inconsistent at reliable tool-calling, and since the demo has to run on a
  small local model, a misrouted request is worse than a slightly blunt
  keyword match. Retrieval still runs first regardless of skill, so even a
  misroute still gets grounded context."
- **Data licensing**: "Lenny's transcripts come from the official free
  starter pack, but its license forbids redistributing the raw files — so
  instead of committing transcripts to the repo, there's a fetch script that
  pulls them at setup time. The repo ships the pipeline, not the copyrighted
  content."
- **Degraded mode instead of hard failures**: "If Ollama goes down mid-demo,
  the app doesn't 500 — it returns a clearly labeled degraded message and
  keeps the conversation usable. I can show this by stopping Ollama live."
  (Only pick this one if you're comfortable doing it live — it's the most
  convincing but riskiest to demo in real time.)

## 4. Close (≈10s)

- "Full source, PRD, architecture doc, and test suite are in the repo. Local
  demo runs fully offline once Ollama and Postgres are up — thanks for
  watching."

## Logistics checklist before recording

- [ ] Ollama running (`ollama serve`) — `llama3.2:3b` and `nomic-embed-text`
      are already pulled from this session's testing (`ollama list` to
      confirm)
- [ ] `backend/dev.db` already has all 10 transcripts ingested (1,129 real
      chunks) from this session — point `DATABASE_URL` at
      `sqlite+aiosqlite:///./dev.db` and skip ingestion entirely, or use
      `docker compose up -d db` + real Postgres if you've got Docker sorted
      by recording time
- [ ] Backend + frontend running, `localhost:5173` loaded — send one
      throwaway grounded question first (off camera) to warm the model up;
      Ollama keeps it loaded for a few minutes afterward, which is the
      window you want to record in
- [ ] Screen recording software running with system audio + mic + camera
- [ ] Have the 3 example prompts above ready to paste so you're not typing
      live and burning time
- [ ] Decide upfront: are you narrating over real wait time, or
      pre-generating and re-sending on a warm model? Don't decide this live.
