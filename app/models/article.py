from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="klix", index=True)
    source_article_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    url: Mapped[str] = mapped_column(String(600), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(600), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    author: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(700), nullable=True)

    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    location_tag_raw: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    location_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    precision: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
