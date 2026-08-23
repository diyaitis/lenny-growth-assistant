export interface SessionSummary {
  id: string;
  title: string | null;
  user_label: string | null;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  index: number;
  transcript_id: string;
  chunk_id: string;
  guest: string | null;
  title: string;
  source_url: string | null;
  score: number;
}

export type Skill = "qa" | "ship30_essay" | "artifact";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  provider: string | null;
  skill: Skill | null;
  citations: Citation[];
  created_at: string;
}

export interface ArtifactSummary {
  id: string;
  kind: "markdown" | "html";
  title: string | null;
  created_at: string;
}

export interface ArtifactDetail extends ArtifactSummary {
  content: string;
}

export interface ChatResponse {
  message: ChatMessage;
  artifact: ArtifactSummary | null;
  grounded: boolean;
  degraded: boolean;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  environment: string;
  db_dialect: string;
  db_reachable: boolean;
  llm_provider: string;
  llm_fallback_provider: string | null;
  llm_reachable: boolean;
  embedding_backend_reachable: boolean;
}

export interface ApiErrorBody {
  error: { code: number; message: string };
}
