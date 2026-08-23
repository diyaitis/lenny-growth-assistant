import type {
  ApiErrorBody,
  ArtifactDetail,
  ArtifactSummary,
  ChatMessage,
  ChatResponse,
  HealthStatus,
  SessionSummary,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "Could not reach the backend API. Is it running?");
  }

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = (await res.json()) as ApiErrorBody;
      message = body.error?.message ?? message;
    } catch {
      // response wasn't JSON — keep the generic message
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthStatus>("/health"),

  createSession: (title?: string) =>
    request<SessionSummary>("/sessions", { method: "POST", body: JSON.stringify({ title }) }),

  listSessions: () => request<SessionSummary[]>("/sessions"),

  getMessages: (sessionId: string) => request<ChatMessage[]>(`/sessions/${sessionId}/messages`),

  sendMessage: (sessionId: string, message: string) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message }),
    }),

  getArtifact: (artifactId: string) => request<ArtifactDetail>(`/artifacts/${artifactId}`),

  // Returns null (not an error) when the session simply has no artifacts
  // yet — that's the common case for most sessions, not a failure.
  getLatestArtifact: async (sessionId: string): Promise<ArtifactSummary | null> => {
    try {
      return await request<ArtifactSummary>(`/sessions/${sessionId}/artifacts/latest`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  },
};
