from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.clients.klix_rss_client import RssEntry
from app.models.base import Base
from app.models.article import Article
from app.models.outbox_event import OutboxEvent
from app.services.location_resolver import LocationResolver
from app.services.outbox_service import OutboxService
from app.services.scraper_service import ScraperService


class FakeRssClient:
    def __init__(self, entries: list[RssEntry]) -> None:
        self._entries = entries

    def fetch_latest(self) -> list[RssEntry]:
        return list(self._entries)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    return session_local()


def _entries() -> list[RssEntry]:
    return [
        RssEntry(
            source_article_id="260317111",
            url="https://www.klix.ba/vijesti/bih/test/260317111",
            title="Sastanak u Sarajevu o saobracaju",
            summary="Razmatrane nove mjere.",
            category="BiH",
            author="A. A.",
            image_url=None,
            published_at=datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc),
        ),
        RssEntry(
            source_article_id="260317112",
            url="https://www.klix.ba/biznis/privreda/test/260317112",
            title="Mostar najavio nove turisticke projekte",
            summary="U Mostaru se ocekuje vise posjeta.",
            category="Privreda",
            author="B. B.",
            image_url=None,
            published_at=datetime(2026, 3, 17, 10, 10, tzinfo=timezone.utc),
        ),
    ]


def test_scraper_inserts_and_deduplicates_items() -> None:
    catalog = Path(__file__).parents[1] / "app" / "data" / "location_catalog.json"
    resolver = LocationResolver(str(catalog))
    outbox = OutboxService(
        webhook_target_url=None,
        webhook_secret="test",
        webhook_timeout_seconds=1,
        max_attempts=5,
        retry_base_seconds=1,
    )
    scraper = ScraperService(FakeRssClient(_entries()), resolver, outbox)

    with _session() as db:
        first = scraper.run_once(db)
        db.commit()

        assert first.fetched == 2
        assert first.inserted == 2
        assert first.updated == 0
        assert first.skipped == 0
        assert first.outbox_enqueued == 2

        article_count = db.scalar(select(func.count(Article.id)))
        outbox_count = db.scalar(select(func.count(OutboxEvent.id)))
        assert article_count == 2
        assert outbox_count == 2


def test_scraper_skips_when_entry_unchanged() -> None:
    catalog = Path(__file__).parents[1] / "app" / "data" / "location_catalog.json"
    resolver = LocationResolver(str(catalog))
    outbox = OutboxService(
        webhook_target_url=None,
        webhook_secret="test",
        webhook_timeout_seconds=1,
        max_attempts=5,
        retry_base_seconds=1,
    )
    scraper = ScraperService(FakeRssClient(_entries()), resolver, outbox)

    db = _session()
    try:
        first = scraper.run_once(db)
        db.commit()
        second = scraper.run_once(db)
        db.commit()

        assert first.inserted == 2
        assert second.inserted == 0
        assert second.updated == 0
        assert second.skipped == 2

        outbox_count = db.scalar(select(func.count(OutboxEvent.id)))
        assert outbox_count == 2
    finally:
        db.close()
