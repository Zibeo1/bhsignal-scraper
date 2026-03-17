from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.klix_rss_client import KlixRssClient, RssEntry
from app.models.article import Article
from app.services.location_resolver import LocationResolver
from app.services.outbox_service import OutboxService


@dataclass
class ScrapeResult:
    fetched: int
    inserted: int
    updated: int
    skipped: int
    outbox_enqueued: int


class ScraperService:
    def __init__(
        self,
        rss_client: KlixRssClient,
        location_resolver: LocationResolver,
        outbox_service: OutboxService,
    ) -> None:
        self.rss_client = rss_client
        self.location_resolver = location_resolver
        self.outbox_service = outbox_service

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _apply_entry(article: Article, entry: RssEntry, location_data) -> bool:
        changed = False
        article.scraped_at = datetime.now(timezone.utc)

        updates = {
            "url": entry.url,
            "title": entry.title,
            "summary": entry.summary,
            "category": entry.category,
            "author": entry.author,
            "image_url": entry.image_url,
            "published_at": entry.published_at,
            "location_tag_raw": location_data.location_tag_raw,
            "location_name": location_data.location_name,
            "latitude": location_data.latitude,
            "longitude": location_data.longitude,
            "location_confidence": location_data.location_confidence,
            "precision": location_data.precision,
        }

        for field, value in updates.items():
            current_value = getattr(article, field)

            if isinstance(current_value, datetime) and isinstance(value, datetime):
                values_equal = ScraperService._as_utc(current_value) == ScraperService._as_utc(value)
            else:
                values_equal = current_value == value

            if not values_equal:
                setattr(article, field, value)
                changed = True

        if changed:
            article.updated_at = datetime.now(timezone.utc)

        return changed

    def run_once(self, db: Session, limit: Optional[int] = None) -> ScrapeResult:
        entries = self.rss_client.fetch_latest()
        if limit is not None:
            entries = entries[:limit]

        fetched = len(entries)
        inserted = 0
        updated = 0
        skipped = 0
        outbox_enqueued = 0

        for entry in entries:
            location = self.location_resolver.resolve(
                title=entry.title,
                summary=entry.summary,
                category=entry.category,
            )

            existing = db.scalar(
                select(Article).where(Article.source_article_id == entry.source_article_id)
            )

            if existing is None:
                article = Article(
                    source="klix",
                    source_article_id=entry.source_article_id,
                    url=entry.url,
                    title=entry.title,
                    summary=entry.summary,
                    category=entry.category,
                    author=entry.author,
                    image_url=entry.image_url,
                    published_at=entry.published_at,
                    scraped_at=datetime.now(timezone.utc),
                    location_tag_raw=location.location_tag_raw,
                    location_name=location.location_name,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    location_confidence=location.location_confidence,
                    precision=location.precision,
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(article)
                db.flush()
                self.outbox_service.enqueue_article_event(db, "news.created", article)
                inserted += 1
                outbox_enqueued += 1
                continue

            if self._apply_entry(existing, entry, location):
                db.flush()
                self.outbox_service.enqueue_article_event(db, "news.updated", existing)
                updated += 1
                outbox_enqueued += 1
            else:
                skipped += 1

        return ScrapeResult(
            fetched=fetched,
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            outbox_enqueued=outbox_enqueued,
        )
