import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../types";

const SKILL_LABEL: Record<string, string> = {
  qa: "Answer",
  ship30_essay: "Ship 30 essay",
  artifact: "Artifact",
};

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`message message--${message.role}`} role="listitem">
      <div className="message__meta">
        <span className="message__role">{isUser ? "You" : "Assistant"}</span>
        {!isUser && message.provider && message.provider !== "none" && (
          <span className="badge badge--provider">{message.provider}</span>
        )}
        {!isUser && message.skill && message.skill !== "qa" && (
          <span className="badge badge--skill">{SKILL_LABEL[message.skill]}</span>
        )}
      </div>

      <div className="message__content">
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        )}
      </div>

      {message.citations.length > 0 && (
        <div className="message__citations" aria-label="Sources">
          <span className="message__citations-label">Sources:</span>
          <ul>
            {message.citations.map((c) => (
              <li key={c.chunk_id} title={`similarity ${c.score.toFixed(2)}`}>
                {c.guest ?? "Unknown guest"} — {c.title}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
