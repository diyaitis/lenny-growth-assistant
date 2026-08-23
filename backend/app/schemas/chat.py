from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.artifact import ArtifactSummary
from app.schemas.session import MessageResponse


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=8000)


class ChatResponse(BaseModel):
    message: MessageResponse
    artifact: ArtifactSummary | None = None
    grounded: bool
    degraded: bool
