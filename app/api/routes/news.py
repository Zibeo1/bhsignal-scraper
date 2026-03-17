from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.models.article import Article
from app.schemas.article import ArticleRead, NewsListResponse


router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=NewsListResponse)
def list_news(
    since: Optional[datetime] = Query(default=None),
    category: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> NewsListResponse:
    query = select(Article).order_by(Article.published_at.desc())

    if since is not None:
        query = query.where(Article.published_at >= since)

    if category:
        query = query.where(func.lower(Article.category) == category.lower())

    if location:
        query = query.where(func.lower(Article.location_name).contains(location.lower()))

    items = db.scalars(query.limit(limit)).all()
    next_since = items[-1].published_at if items else None
    return NewsListResponse(items=[ArticleRead.model_validate(item) for item in items], next_since=next_since)


@router.get("/{article_id}", response_model=ArticleRead)
def get_news_item(article_id: str, db: Session = Depends(get_db_session)) -> ArticleRead:
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleRead.model_validate(article)
