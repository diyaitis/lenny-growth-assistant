import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { ChatMessage } from "../types";
import { MessageBubble } from "./MessageBubble";

interface Props {
  messages: ChatMessage[];
  onSend: (text: string) => Promise<void>;
  sending: boolean;
  error: string | null;
  disabled: boolean;
}

export function ChatPanel({ messages, onSend, sending, error, disabled }: Props) {
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    setDraft("");
    await onSend(text);
  }

  return (
    <section className="chat-panel" aria-label="Conversation">
      <div className="chat-panel__messages" ref={listRef} role="list" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat-panel__empty">
            <h1>The Lenny Growth Assistant</h1>
            <p>
              Ask a product or growth question grounded in Lenny's Podcast transcripts. Try:
              "What did Elena Verna say about activation vs. acquisition?" or "Turn that into a Ship 30 essay."
            </p>
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {sending && (
          <div className="message message--assistant message--pending" role="status">
            <div className="message__meta">
              <span className="message__role">Assistant</span>
            </div>
            <div className="typing-indicator" aria-label="Assistant is typing">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="chat-panel__error" role="alert">
          {error}
        </div>
      )}

      <form className="chat-panel__input" onSubmit={handleSubmit}>
        <label htmlFor="chat-input" className="sr-only">
          Message
        </label>
        <textarea
          id="chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          placeholder="Ask about product, growth, or say 'turn this into a ship 30 essay'…"
          rows={2}
          disabled={disabled}
        />
        <button type="submit" disabled={disabled || sending || !draft.trim()}>
          Send
        </button>
      </form>
    </section>
  );
}
