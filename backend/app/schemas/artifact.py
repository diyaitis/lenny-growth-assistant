from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ArtifactSummary(BaseModel):
    id: str
    kind: str
    title: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactDetail(ArtifactSummary):
    content: str
