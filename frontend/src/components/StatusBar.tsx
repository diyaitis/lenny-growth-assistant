import type { HealthStatus } from "../types";

export function StatusBar({ health }: { health: HealthStatus | null }) {
  if (!health) {
    return (
      <div className="status-bar status-bar--unknown" role="status">
        Checking backend status…
      </div>
    );
  }

  const dot = health.status === "ok" ? "status-dot--ok" : "status-dot--degraded";

  return (
    <div className={`status-bar status-bar--${health.status}`} role="status">
      <span className={`status-dot ${dot}`} aria-hidden="true" />
      <span>
        Model: <strong>{health.llm_provider}</strong>
        {health.llm_fallback_provider && <> (fallback: {health.llm_fallback_provider})</>}
      </span>
      <span aria-hidden="true">·</span>
      <span>{health.llm_reachable ? "reachable" : "unreachable — responses will be degraded"}</span>
      <span aria-hidden="true">·</span>
      <span>DB: {health.db_dialect}</span>
    </div>
  );
}
