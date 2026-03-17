from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ArticleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    source_article_id: str
    url: str
    title: str
    summary: str
    category: Optional[str]
    author: Optional[str]
    image_url: Optional[str]
    published_at: datetime
    scraped_at: datetime
    location_tag_raw: Optional[str]
    location_name: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    location_confidence: float
    precision: str
    created_at: datetime
    updated_at: datetime


class NewsListResponse(BaseModel):
    items: list[ArticleRead]
    next_since: Optional[datetime]
