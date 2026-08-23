# design.md — UI/UX

## Principles

1. **The chat stays a chat; long-form output goes in the artifact panel.**
   A 1,250-word essay dumped into a chat bubble is unreadable and makes the
   conversation itself hard to scroll. Ship 30 essays and generated
   docs/pages always go to the artifact viewer; the chat gets a one-line
   pointer message instead ("Here's your essay — see the viewer.").
2. **Grounding is visible, not implied.** Every grounded answer shows which
   guest/episode it drew from. An answer with no citations is either a
   direct restatement of the "not covered" message or something worth being
   suspicious of — so citations are always rendered when present, never
   hidden behind a click.
3. **Model identity and health are ambient, not buried in settings.** The
   status bar always shows the active provider and whether it's reachable.
   The assignment's "toggle behavior must be visible" requirement is met by
   never hiding this, not by a settings page the evaluator has to go find.
4. **Degraded is not broken.** When the model is unreachable, the UI shows a
   clear, specific assistant message and keeps working (you can still send
   another message, switch sessions, etc.) rather than an error boundary or
   a blank screen.

## Information architecture

```
App
├─ Sidebar            session list + "new chat" (left, persistent)
├─ Status bar          active provider · reachability · DB dialect (top, persistent)
└─ Main content
   ├─ Chat panel        message history + composer (left ~55%)
   └─ Artifact panel     empty state, or the current artifact (right ~45%)
```

Two panes side by side is the deliberate structural echo of Claude's own
Artifacts UI — evaluators asked to build "an Artifact Viewer, similar to
Claude Artifacts" will recognize the pattern immediately, which is the point.

## Key interaction states

- **Empty session** — chat panel shows a short prompt with two example
  queries (a QA example and a "turn this into an essay" example) so a new
  evaluator isn't staring at a blank box.
- **Sending** — composer disables its submit button (not the textarea, so
  the user can keep typing/editing their next message); a three-dot typing
  indicator appears in place of the next assistant bubble. The user's
  message renders optimistically the instant it's submitted (before the
  server responds), and is rolled back if the request fails, with the error
  surfaced in a dismissible-by-next-action banner above the composer.
- **Grounded answer** — assistant bubble + a "Sources" list under it (guest
  name + episode title per citation).
- **Not grounded** — assistant bubble with no citations block at all (rather
  than an empty "Sources:" header), so the *absence* of sources is itself
  legible as "this wasn't backed by the transcripts."
- **Ship 30 / artifact produced** — chat gets the short pointer message; the
  artifact panel auto-opens/updates to the new artifact. If the user had a
  previous artifact open, it's replaced (there's one "current" artifact per
  turn, not a growing list to manage — kept intentionally simple for v1).
- **Degraded** — assistant bubble explains what's unreachable in plain
  language and what to check (matches the copy in `llm/factory.py`'s
  fallback response, so the UI never contradicts the API).
- **HTML artifact** — renders in a sandboxed iframe with a plain white
  background (artifacts often assume a light canvas regardless of app theme,
  same as Claude's own Artifacts).
- **Markdown artifact** — rendered with headings/bullets/bold styled
  distinctly from chat markdown (larger heading scale) since it's meant to
  read as a standalone document, not a chat reply.

## Responsive behavior

- **≥900px** — three-column-feeling layout: sidebar | chat | artifact, all
  visible at once (see `app-shell` / `app-main__content` grid in
  `global.css`).
- **<900px** — sidebar collapses to a horizontal strip capped at 160px tall
  (session list becomes a short scrollable list rather than disappearing
  entirely — there's no hamburger-menu state to implement/test for a
  take-home); chat and artifact panel stack vertically instead of
  side-by-side, each taking half the remaining height so neither is fully
  hidden when an artifact exists.
- All layout is CSS grid/flex with relative sizing — no fixed pixel widths
  on the two main panes — so intermediate widths degrade smoothly rather
  than snapping.

## Accessibility

- Message list has `role="list"` / `role="listitem"` and `aria-live="polite"`
  so new assistant messages are announced without re-announcing the entire
  history.
- The composer's textarea has a visually-hidden (`sr-only`) `<label>`
  ("Message") rather than relying on placeholder text as the only label.
- Enter submits, Shift+Enter inserts a newline — the standard chat-input
  convention, so it matches user expectation without a visible hint needed.
- All interactive elements (session buttons, send button, artifact-close
  button) are real `<button>` elements, so they're keyboard-reachable and
  get default focus styling; `:focus-visible` is styled explicitly (not
  suppressed) in `global.css`.
- Color is never the only signal: the status bar's reachability dot is
  paired with the word "reachable"/"unreachable" in text; citation "sources"
  are a labeled list, not just a colored badge.
- Respects `prefers-color-scheme` for dark mode (the whole palette is
  token-based in `global.css`) since a take-home evaluator may well be
  running a dark-themed OS/browser and a light-only UI would be a papercut.
- The HTML artifact iframe has an explicit `title` attribute (the artifact's
  title, or a fallback) for screen-reader users navigating by landmark.

## Design decisions worth calling out

- **No component library** (no MUI/Chakra/shadcn). For a two-pane chat app
  of this size, hand-written CSS with design tokens is less overhead than
  configuring a library, and it keeps the bundle small (production build is
  ~310KB JS / ~6KB CSS, mostly React itself).
- **`react-markdown` with no `rehype-raw` plugin** is a security decision as
  much as a rendering one — see `architecture.md` > Security: this is what
  makes Markdown artifacts have no HTML-injection surface at all, by
  construction, rather than by a sanitization step someone could forget.
- **One artifact "slot," not a gallery.** A real product would likely let
  you page through multiple generated artifacts per session. Cut for scope —
  the brief asks for artifacts to render "beside the chat," which a single
  current-artifact panel satisfies, and a gallery/history UI is a distinct
  feature with its own state-management questions better scoped separately.
