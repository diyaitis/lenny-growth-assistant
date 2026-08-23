import type { SessionSummary } from "../types";

interface Props {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  loading: boolean;
}

export function SessionSidebar({ sessions, activeSessionId, onSelect, onCreate, loading }: Props) {
  return (
    <nav className="sidebar" aria-label="Chat sessions">
      <button type="button" className="sidebar__new-chat" onClick={onCreate} disabled={loading}>
        + New chat
      </button>
      <ul className="sidebar__list">
        {sessions.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              className={`sidebar__item ${s.id === activeSessionId ? "sidebar__item--active" : ""}`}
              onClick={() => onSelect(s.id)}
              aria-current={s.id === activeSessionId ? "true" : undefined}
            >
              {s.title || "Untitled session"}
            </button>
          </li>
        ))}
        {sessions.length === 0 && !loading && <li className="sidebar__empty">No sessions yet</li>}
      </ul>
    </nav>
  );
}
