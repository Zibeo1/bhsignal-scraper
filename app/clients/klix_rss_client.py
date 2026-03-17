from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser
import httpx


def _strip_html(raw_value: Optional[str]) -> str:
    if not raw_value:
        return ""

    without_tags = re.sub(r"<[^>]+>", " ", raw_value)
    clean = re.sub(r"\s+", " ", without_tags).strip()
    return html.unescape(clean)


def _extract_article_id(url: str) -> str:
    match = re.search(r"/(\d{6,})/?$", url)
    if match:
        return match.group(1)
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def _to_datetime(raw_date: Optional[str]) -> datetime:
    if not raw_date:
        return datetime.now(timezone.utc)

    try:
        dt = parsedate_to_datetime(raw_date)
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)

    if dt is None:
        return datetime.now(timezone.utc)

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class RssEntry:
    source_article_id: str
    url: str
    title: str
    summary: str
    category: Optional[str]
    author: Optional[str]
    image_url: Optional[str]
    published_at: datetime


def parse_feed(xml_text: str) -> list[RssEntry]:
    feed = feedparser.parse(xml_text)
    items: list[RssEntry] = []

    for entry in feed.entries:
        link = entry.get("link")
        title = _strip_html(entry.get("title"))
        if not link or not title:
            continue

        raw_category = None
        tags = entry.get("tags", [])
        if tags:
            raw_tag = tags[0]
            if isinstance(raw_tag, dict):
                raw_category = raw_tag.get("term")
            else:
                raw_category = getattr(raw_tag, "term", None)

        media_items = entry.get("media_content", [])
        image_url = None
        if media_items:
            first_media = media_items[0]
            if isinstance(first_media, dict):
                image_url = first_media.get("url")

        published_raw = entry.get("published") or entry.get("pubDate")
        author = entry.get("dc_creator") or entry.get("author")

        items.append(
            RssEntry(
                source_article_id=_extract_article_id(link),
                url=link,
                title=title,
                summary=_strip_html(entry.get("summary") or entry.get("description")),
                category=raw_category,
                author=author,
                image_url=image_url,
                published_at=_to_datetime(published_raw),
            )
        )

    return items


class KlixRssClient:
    def __init__(
        self,
        rss_url: str,
        timeout_seconds: int,
        user_agent: str,
        batch_limit: int,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.rss_url = rss_url
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.batch_limit = batch_limit
        self.http_client = http_client or httpx.Client()

    def fetch_latest(self) -> list[RssEntry]:
        response = self.http_client.get(
            self.rss_url,
            timeout=self.timeout_seconds,
            headers={"User-Agent": self.user_agent},
        )
        response.raise_for_status()
        parsed_entries = parse_feed(response.text)
        return parsed_entries[: self.batch_limit]
