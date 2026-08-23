from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    user_label: str | None = Field(default=None, max_length=200)


class SessionResponse(BaseModel):
    id: str
    title: str | None
    user_label: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CitationOut(BaseModel):
    index: int
    transcript_id: str
    chunk_id: str
    guest: str | None
    title: str
    source_url: str | None
    score: float


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    provider: str | None
    skill: str | None
    citations: list[dict]
    created_at: datetime

    model_config = {"from_attributes": True}
