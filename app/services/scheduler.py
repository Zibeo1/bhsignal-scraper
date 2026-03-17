from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.db import session_scope
from app.services.scraper_service import ScraperService
from app.services.outbox_service import OutboxService


logger = logging.getLogger(__name__)


class SchedulerCoordinator:
    def __init__(
        self,
        scraper_service: ScraperService,
        outbox_service: OutboxService,
        scrape_interval_seconds: int,
        dispatch_interval_seconds: int,
        scrape_batch_limit: int,
        run_scrape_on_startup: bool,
    ) -> None:
        self.scraper_service = scraper_service
        self.outbox_service = outbox_service
        self.scrape_interval_seconds = scrape_interval_seconds
        self.dispatch_interval_seconds = dispatch_interval_seconds
        self.scrape_batch_limit = scrape_batch_limit
        self.run_scrape_on_startup = run_scrape_on_startup
        self.scheduler = BackgroundScheduler(timezone="UTC")

    def _run_scrape_job(self) -> None:
        with session_scope() as db:
            result = self.scraper_service.run_once(db, limit=self.scrape_batch_limit)
            logger.info(
                "Scheduled scrape complete: fetched=%s inserted=%s updated=%s skipped=%s outbox=%s",
                result.fetched,
                result.inserted,
                result.updated,
                result.skipped,
                result.outbox_enqueued,
            )

    def _run_dispatch_job(self) -> None:
        with session_scope() as db:
            result = self.outbox_service.dispatch_pending(db)
            if result.delivered or result.failed or result.retried:
                logger.info(
                    "Outbox dispatch complete: delivered=%s failed=%s retried=%s",
                    result.delivered,
                    result.failed,
                    result.retried,
                )

    def start(self) -> None:
        self.scheduler.add_job(
            self._run_scrape_job,
            trigger="interval",
            seconds=self.scrape_interval_seconds,
            id="scrape-job",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._run_dispatch_job,
            trigger="interval",
            seconds=self.dispatch_interval_seconds,
            id="dispatch-job",
            replace_existing=True,
        )
        self.scheduler.start()

        if self.run_scrape_on_startup:
            self._run_scrape_job()
            self._run_dispatch_job()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
