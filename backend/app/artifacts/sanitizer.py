"""Artifact isolation strategy.

Generated HTML is treated as fully untrusted (it comes from an LLM, which
could be prompt-injected via retrieved transcript content or a crafted user
message). Two independent layers, so a bypass of one doesn't mean full
compromise:

1. Backend sanitization (this file): strip constructs that would let the
   artifact escape its sandbox or exfiltrate outside of it regardless of how
   the frontend renders it — <base> (relative-URL hijacking), <meta
   http-equiv="refresh"> (forced navigation), remote <script src>/<link>
   (loading attacker/third-party code we didn't generate), and event-handler
   attributes (onerror=, onclick=, ...) as a defense-in-depth belt-and-braces
   measure even though the iframe sandbox already blocks their most dangerous
   effects.

2. Frontend sandboxing (frontend/src/components/ArtifactViewer.tsx): rendered
   in `<iframe sandbox="allow-scripts">` via `srcdoc` — deliberately WITHOUT
   `allow-same-origin`, `allow-top-navigation`, `allow-popups`, or
   `allow-forms`. This gives the document a unique opaque origin: inline
   scripts still run (so interactive demos work), but the frame cannot read
   the parent page, cookies, or localStorage, cannot navigate the top window,
   and cannot open popups or submit forms.

Residual risk we accept and document: the sandbox attribute does not block
outbound network requests (fetch/XHR/img/CSS) from inside the iframe. We close
that gap with an injected Content-Security-Policy meta tag (`connect-src
'none'; frame-src 'none'`) that blocks exactly that, while still allowing
inline script/style execution and locally-embedded images. Markdown
artifacts never render raw HTML at all (see frontend ArtifactViewer): they go
through a Markdown renderer with raw-HTML pass-through disabled, so there is
no injection surface for Markdown artifacts in the first place.
"""
from __future__ import annotations

import re

_STRIP_TAG_PATTERNS = [
    re.compile(r"<base\b[^>]*>", re.IGNORECASE),
    re.compile(r"<meta[^>]+http-equiv=[\"']?refresh[\"']?[^>]*>", re.IGNORECASE),
    # <script src="..."> (remote) — keep inline <script>...</script> with no src
    re.compile(r"<script\b[^>]*\bsrc=[\"'][^\"']*[\"'][^>]*>\s*</script>", re.IGNORECASE),
    re.compile(r"<link\b[^>]*\brel=[\"']?stylesheet[\"']?[^>]*>", re.IGNORECASE),
]

_EVENT_HANDLER_ATTR = re.compile(r'\son\w+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', re.IGNORECASE)

_INJECTED_CSP = (
    '<meta http-equiv="Content-Security-Policy" '
    'content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; '
    "img-src data: ; font-src data: ; connect-src 'none'; frame-src 'none'; "
    'form-action \'none\';">'
)


def sanitize_html_artifact(html: str) -> str:
    cleaned = html
    for pattern in _STRIP_TAG_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = _EVENT_HANDLER_ATTR.sub("", cleaned)

    if re.search(r"<head[^>]*>", cleaned, re.IGNORECASE):
        cleaned = re.sub(r"(<head[^>]*>)", r"\1" + _INJECTED_CSP, cleaned, count=1, flags=re.IGNORECASE)
    elif re.search(r"<html[^>]*>", cleaned, re.IGNORECASE):
        cleaned = re.sub(
            r"(<html[^>]*>)", r"\1<head>" + _INJECTED_CSP + "</head>", cleaned, count=1, flags=re.IGNORECASE
        )
    else:
        cleaned = _INJECTED_CSP + cleaned

    return cleaned
