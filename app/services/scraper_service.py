from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.klix_rss_client import RssEntry
from app.models.article import Article
from app.services import dedup
from app.services.location_resolver import LocationResolver
from app.services.outbox_service import OutboxService


_CRIME_RE = re.compile(
    r"(uhapsen|uhicen|ubijen|ubistvo|ubili|droga|narkotik|policij|nesrec|povrijed|krad|napad|"
    r"oruzj|pretres|razbojnis|poginu|saobracajn|nasilj|prevar|ukral)"
)


@dataclass
class ScrapeResult:
    fetched: int
    inserted: int
    updated: int
    skipped: int
    outbox_enqueued: int
    skipped_non_bosnia: int = 0
    skipped_duplicate: int = 0


class ScraperService:
    def __init__(
        self,
        rss_clients,
        location_resolver: LocationResolver,
        outbox_service: OutboxService,
        bosnia_only: bool = False,
    ) -> None:
        # Accept a single client or a list of clients (one per news source).
        if not isinstance(rss_clients, (list, tuple)):
            rss_clients = [rss_clients]
        self.rss_clients = list(rss_clients)
        self.location_resolver = location_resolver
        self.outbox_service = outbox_service
        self.bosnia_only = bosnia_only

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _category_for(source: str, entry: RssEntry) -> str:
        """Normalize each source into the shared category taxonomy."""
        if source == "klix":
            path = urlparse(entry.url).path.lower()
            if "crna-hronika" in path:
                return "CRNA HRONIKA"
            if re.search(r"(^|/)(sport|nogomet|kosarka|tenis|odbojka|rukomet|formula)", path):
                return "SPORT"
            if "kultura" in path:
                return "KULTURA"
            if re.search(r"(biznis|ekonomija)", path):
                return "BIZNIS"
            if re.search(r"(^|/)auto", path):
                return "AUTO"
            if re.search(r"(lifestyle|modailjepota|magazin|show|zdravlje)", path):
                return "LIFESTYLE"
            if re.search(r"(scitech|nauka|tehnologija|tech)", path):
                return "TECH"
            return "VIJESTI"

        # crna-hronika mixes crime and general news; classify by keywords.
        text = dedup.normalize(f"{entry.title} {entry.summary}")
        return "CRNA HRONIKA" if _CRIME_RE.search(text) else "VIJESTI"

    @staticmethod
    def _apply_entry(article: Article, entry: RssEntry, location_data, category: str) -> bool:
        changed = False
        article.scraped_at = datetime.now(timezone.utc)

        updates = {
            "url": entry.url,
            "title": entry.title,
            "summary": entry.summary,
            "category": category,
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

    def _load_existing_token_sets(self, db: Session) -> list[set[str]]:
        titles = db.scalars(select(Article.title)).all()
        return [dedup.title_tokens(title) for title in titles if title]

    def run_once(self, db: Session, limit: Optional[int] = None) -> ScrapeResult:
        # Pre-load headlines already stored so a story from a second source is
        # recognized as a duplicate of one we already have.
        seen_token_sets = self._load_existing_token_sets(db)

        fetched = 0
        inserted = 0
        updated = 0
        skipped = 0
        outbox_enqueued = 0
        skipped_non_bosnia = 0
        skipped_duplicate = 0

        for client in self.rss_clients:
            source = getattr(client, "source", None) or "klix"
            entries = client.fetch_latest()
            if limit is not None:
                entries = entries[:limit]

            for entry in entries:
                fetched += 1

                location = self.location_resolver.resolve(
                    title=entry.title,
                    summary=entry.summary,
                    category=entry.category,
                )

                # Keep only Bosnia and Herzegovina news.
                if self.bosnia_only and not self.location_resolver.is_bosnia(location):
                    skipped_non_bosnia += 1
                    continue

                category = self._category_for(source, entry)
                tokens = dedup.title_tokens(entry.title)

                existing = db.scalar(
                    select(Article).where(
                        Article.source == source,
                        Article.source_article_id == entry.source_article_id,
                    )
                )

                if existing is None:
                    # New article id for this source: reject if another source already
                    # published the same story (cross-source dedup).
                    if dedup.is_duplicate(tokens, seen_token_sets):
                        skipped_duplicate += 1
                        continue
                    seen_token_sets.append(tokens)

                    article = Article(
                        source=source,
                        source_article_id=entry.source_article_id,
                        url=entry.url,
                        title=entry.title,
                        summary=entry.summary,
                        category=category,
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

                # Same source + id we already have: normal update path.
                seen_token_sets.append(tokens)
                if self._apply_entry(existing, entry, location, category):
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
            skipped_non_bosnia=skipped_non_bosnia,
            skipped_duplicate=skipped_duplicate,
        )
