from __future__ import annotations

from pydantic import BaseModel


class OutboxStatusResponse(BaseModel):
    pending: int
    failed: int
    delivered: int


class OutboxDispatchResponse(BaseModel):
    delivered: int
    failed: int
    retried: int
