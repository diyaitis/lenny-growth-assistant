import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api/client";
import type { ArtifactDetail, ArtifactSummary } from "../types";

interface Props {
  summary: ArtifactSummary | null;
  onClose: () => void;
}

/**
 * Renders a generated artifact.
 *
 * Security model (see backend/app/artifacts/sanitizer.py for the full
 * writeup):
 *  - Markdown artifacts go through react-markdown with NO raw-HTML plugin
 *    (rehype-raw) enabled, so any HTML embedded in generated markdown is
 *    rendered as inert text, not markup. There is no injection surface here.
 *  - HTML artifacts render inside a sandboxed <iframe srcDoc=...>. The
 *    sandbox attribute intentionally omits allow-same-origin,
 *    allow-top-navigation, allow-popups, and allow-forms: scripts execute
 *    (so interactive demos work) inside a unique opaque origin that cannot
 *    read this page, its cookies, or its localStorage, cannot navigate the
 *    top window, and cannot pop up windows or submit forms. The backend
 *    additionally strips remote <script>/<link> tags and injects a CSP that
 *    blocks outbound network requests from inside the artifact (the one
 *    thing the sandbox attribute alone does not block).
 */
export function ArtifactViewer({ summary, onClose }: Props) {
  const [detail, setDetail] = useState<ArtifactDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!summary) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getArtifact(summary.id)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message ?? "Failed to load artifact");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [summary]);

  if (!summary) {
    return (
      <aside className="artifact-panel artifact-panel--empty" aria-label="Artifact viewer">
        <p>No artifact yet. Ask the assistant to generate a Ship 30 essay, a Markdown doc, or an HTML page.</p>
      </aside>
    );
  }

  return (
    <aside className="artifact-panel" aria-label="Artifact viewer">
      <header className="artifact-panel__header">
        <div>
          <span className="artifact-panel__kind">{summary.kind === "html" ? "HTML" : "Markdown"}</span>
          <h2>{summary.title ?? "Untitled artifact"}</h2>
        </div>
        <button type="button" onClick={onClose} aria-label="Close artifact viewer">
          ×
        </button>
      </header>

      <div className="artifact-panel__body">
        {loading && <p role="status">Loading artifact…</p>}
        {error && (
          <p role="alert" className="error-text">
            {error}
          </p>
        )}
        {detail && detail.kind === "markdown" && (
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{detail.content}</ReactMarkdown>
          </div>
        )}
        {detail && detail.kind === "html" && (
          <iframe
            title={detail.title ?? "Generated HTML artifact"}
            className="artifact-iframe"
            sandbox="allow-scripts"
            srcDoc={detail.content}
          />
        )}
      </div>
    </aside>
  );
}
