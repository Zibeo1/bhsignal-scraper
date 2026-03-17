from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.article import Article
from app.models.outbox_event import OutboxEvent


logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    delivered: int
    failed: int
    retried: int


class OutboxService:
    def __init__(
        self,
        webhook_target_url: Optional[str],
        webhook_secret: str,
        webhook_timeout_seconds: int,
        max_attempts: int,
        retry_base_seconds: int,
    ) -> None:
        self.webhook_target_url = webhook_target_url
        self.webhook_secret = webhook_secret
        self.webhook_timeout_seconds = webhook_timeout_seconds
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds

    @staticmethod
    def _datetime_iso(value: datetime) -> str:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _article_payload(article: Article) -> dict:
        return {
            "source": article.source,
            "sourceArticleId": article.source_article_id,
            "title": article.title,
            "summary": article.summary,
            "url": article.url,
            "publishedAt": OutboxService._datetime_iso(article.published_at),
            "category": article.category,
            "author": article.author,
            "imageUrl": article.image_url,
            "locationTagRaw": article.location_tag_raw,
            "locationName": article.location_name,
            "latitude": article.latitude,
            "longitude": article.longitude,
            "locationConfidence": article.location_confidence,
            "precision": article.precision,
            "updatedAt": OutboxService._datetime_iso(article.updated_at),
        }

    def enqueue_article_event(self, db: Session, event_type: str, article: Article) -> OutboxEvent:
        payload = {
            "eventType": event_type,
            "occurredAt": datetime.now(timezone.utc).isoformat(),
            "source": "klix-scraper",
            "data": self._article_payload(article),
        }

        event = OutboxEvent(
            topic=event_type,
            payload_json=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            status="pending",
            attempts=0,
            next_retry_at=datetime.now(timezone.utc),
        )
        db.add(event)
        return event

    def _build_signature(self, payload_text: str) -> str:
        digest = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload_text.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"

    def dispatch_pending(self, db: Session, limit: int = 50) -> DispatchResult:
        if not self.webhook_target_url:
            return DispatchResult(delivered=0, failed=0, retried=0)

        now = datetime.now(timezone.utc)
        events = db.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.status.in_(["pending", "failed"]),
                OutboxEvent.next_retry_at <= now,
                OutboxEvent.attempts < self.max_attempts,
            )
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
        ).all()

        delivered = 0
        failed = 0
        retried = 0

        with httpx.Client() as client:
            for event in events:
                payload_text = event.payload_json
                headers = {
                    "Content-Type": "application/json",
                    "X-Event-Id": event.id,
                    "X-Signature-256": self._build_signature(payload_text),
                }

                event.attempts += 1
                event.updated_at = datetime.now(timezone.utc)

                try:
                    response = client.post(
                        self.webhook_target_url,
                        content=payload_text,
                        headers=headers,
                        timeout=self.webhook_timeout_seconds,
                    )
                    response.raise_for_status()
                    event.status = "delivered"
                    event.delivered_at = datetime.now(timezone.utc)
                    event.last_error = None
                    delivered += 1
                except Exception as exc:  # noqa: BLE001
                    event.last_error = str(exc)
                    backoff_multiplier = 2 ** max(0, event.attempts - 1)
                    event.next_retry_at = datetime.now(timezone.utc) + timedelta(
                        seconds=self.retry_base_seconds * backoff_multiplier
                    )

                    if event.attempts >= self.max_attempts:
                        event.status = "failed"
                        failed += 1
                    else:
                        event.status = "pending"
                        retried += 1

                    logger.warning(
                        "Webhook dispatch failed for event %s (attempt %s): %s",
                        event.id,
                        event.attempts,
                        event.last_error,
                    )

        return DispatchResult(delivered=delivered, failed=failed, retried=retried)

    def get_status_counts(self, db: Session) -> dict[str, int]:
        statuses = ["pending", "failed", "delivered"]
        counts: dict[str, int] = {status: 0 for status in statuses}

        rows = db.execute(
            select(OutboxEvent.status, func.count(OutboxEvent.id)).group_by(OutboxEvent.status)
        ).all()
        for status, count in rows:
            counts[status] = int(count)

        return counts
