from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "klix-scraper-service"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite:///./data/scraper.db"

    klix_rss_url: str = "https://www.klix.ba/rss"
    crna_hronika_rss_url: str = "https://crna-hronika.info/feed/"
    request_timeout_seconds: int = 20
    user_agent: str = "GeoNewsScraperBot/0.1 (+https://example.org/geonews)"

    scheduler_enabled: bool = True
    run_scrape_on_startup: bool = False
    scrape_interval_seconds: int = 300
    scrape_batch_limit: int = 200

    outbox_dispatch_interval_seconds: int = 20
    outbox_max_attempts: int = 10
    outbox_retry_base_seconds: int = 30

    webhook_target_url: Optional[str] = None
    webhook_secret: str = "change-me"
    webhook_timeout_seconds: int = 10

    location_catalog_path: str = "./app/data/location_catalog.json"

    # When true, only articles resolved to a Bosnia and Herzegovina location are kept.
    bosnia_only: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
