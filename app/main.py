from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.clients.klix_rss_client import KlixRssClient
from app.core.config import Settings, get_settings
from app.core.db import init_db
from app.core.logging import configure_logging
from app.services.location_resolver import LocationResolver
from app.services.outbox_service import OutboxService
from app.services.scheduler import SchedulerCoordinator
from app.services.scraper_service import ScraperService


def _build_container(settings: Settings) -> dict:
    rss_client = KlixRssClient(
        rss_url=settings.klix_rss_url,
        timeout_seconds=settings.request_timeout_seconds,
        user_agent=settings.user_agent,
        batch_limit=settings.scrape_batch_limit,
    )
    location_resolver = LocationResolver(settings.location_catalog_path)
    outbox_service = OutboxService(
        webhook_target_url=settings.webhook_target_url,
        webhook_secret=settings.webhook_secret,
        webhook_timeout_seconds=settings.webhook_timeout_seconds,
        max_attempts=settings.outbox_max_attempts,
        retry_base_seconds=settings.outbox_retry_base_seconds,
    )
    scraper_service = ScraperService(
        rss_client=rss_client,
        location_resolver=location_resolver,
        outbox_service=outbox_service,
        bosnia_only=settings.bosnia_only,
    )
    scheduler = SchedulerCoordinator(
        scraper_service=scraper_service,
        outbox_service=outbox_service,
        scrape_interval_seconds=settings.scrape_interval_seconds,
        dispatch_interval_seconds=settings.outbox_dispatch_interval_seconds,
        scrape_batch_limit=settings.scrape_batch_limit,
        run_scrape_on_startup=settings.run_scrape_on_startup,
    )

    return {
        "settings": settings,
        "rss_client": rss_client,
        "location_resolver": location_resolver,
        "outbox_service": outbox_service,
        "scraper_service": scraper_service,
        "scheduler": scheduler,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    init_db()
    container = _build_container(settings)
    app.state.container = container

    if settings.scheduler_enabled:
        container["scheduler"].start()

    try:
        yield
    finally:
        if settings.scheduler_enabled:
            container["scheduler"].shutdown()
        container["rss_client"].http_client.close()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(health_router)
app.include_router(api_router, prefix=settings.api_prefix)
