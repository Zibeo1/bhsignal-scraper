from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ScrapeRunRequest(BaseModel):
    limit: Optional[int] = Field(default=None, ge=1, le=1000)


class ScrapeRunResponse(BaseModel):
    fetched: int
    inserted: int
    updated: int
    skipped: int
    outbox_enqueued: int
