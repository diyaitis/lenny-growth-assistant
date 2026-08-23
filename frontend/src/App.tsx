import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api/client";
import { ArtifactViewer } from "./components/ArtifactViewer";
import { ChatPanel } from "./components/ChatPanel";
import { SessionSidebar } from "./components/SessionSidebar";
import { StatusBar } from "./components/StatusBar";
import type { ArtifactSummary, ChatMessage, HealthStatus, SessionSummary } from "./types";

const HEALTH_POLL_MS = 20_000;

export default function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [artifact, setArtifact] = useState<ArtifactSummary | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshHealth = useCallback(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    refreshHealth();
    const id = setInterval(refreshHealth, HEALTH_POLL_MS);
    return () => clearInterval(id);
  }, [refreshHealth]);

  const createSession = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const session = await api.createSession();
      setSessions((prev) => [session, ...prev]);
      setActiveSessionId(session.id);
      setMessages([]);
      setArtifact(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create a session.");
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const list = await api.listSessions();
        setSessions(list);
        if (list.length > 0) {
          setActiveSessionId(list[0].id);
        } else {
          await createSession();
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Failed to load sessions.");
      } finally {
        setLoadingSessions(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!activeSessionId) return;
    // Restore this session's most recent artifact (if any) instead of
    // resetting to the empty state — found missing during browser QA:
    // reopening a session that had already generated a Ship 30 essay or an
    // HTML page showed no artifact at all until you asked for a new one.
    api
      .getLatestArtifact(activeSessionId)
      .then(setArtifact)
      .catch(() => setArtifact(null));
    api
      .getMessages(activeSessionId)
      .then(setMessages)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load messages."));
  }, [activeSessionId]);

  async function handleSend(text: string) {
    if (!activeSessionId) return;
    setError(null);
    setSending(true);

    const optimisticUserMessage: ChatMessage = {
      id: `pending-${Date.now()}`,
      role: "user",
      content: text,
      provider: null,
      skill: null,
      citations: [],
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUserMessage]);

    try {
      const resp = await api.sendMessage(activeSessionId, text);
      setMessages((prev) => [...prev, resp.message]);
      if (resp.artifact) setArtifact(resp.artifact);
      setSessions((prev) => {
        const updated = prev.map((s) => (s.id === activeSessionId ? { ...s, updated_at: new Date().toISOString() } : s));
        return updated;
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong sending your message.");
      setMessages((prev) => prev.filter((m) => m.id !== optimisticUserMessage.id));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="app-shell">
      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelect={setActiveSessionId}
        onCreate={createSession}
        loading={loadingSessions}
      />
      <div className="app-main">
        <StatusBar health={health} />
        <div className="app-main__content">
          <ChatPanel
            messages={messages}
            onSend={handleSend}
            sending={sending}
            error={error}
            disabled={!activeSessionId}
          />
          <ArtifactViewer summary={artifact} onClose={() => setArtifact(null)} />
        </div>
      </div>
    </div>
  );
}
