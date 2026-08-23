from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    environment: str
    db_dialect: str
    db_reachable: bool
    llm_provider: str
    llm_fallback_provider: str | None
    llm_reachable: bool
    embedding_backend_reachable: bool
