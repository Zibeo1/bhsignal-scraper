# Scraper Service

Independent service that ingests Klix news, resolves location, stores normalized data, and emits webhook events through a reliable outbox.

## Features

- pulls `https://www.klix.ba/rss`
- extracts normalized article fields
- resolves location against local location catalog
- stores data in own database
- creates outbox events for each create/update
- dispatches signed webhook events with retry/backoff
- exposes API for replay and operations

Note: direct article HTML scraping is often blocked by Cloudflare from server-to-server traffic. This implementation uses RSS plus location extraction from title/summary/category. You can add a headless-browser adapter later if you need exact in-article tag extraction.

## API

- `GET /health`
- `GET /api/v1/news`
- `GET /api/v1/news/{articleId}`
- `POST /api/v1/scrape/run`
- `GET /api/v1/outbox/status`
- `POST /api/v1/outbox/dispatch`

## Local Run

```bash
python3 -m pip install '.[test]'
uvicorn app.main:app --reload --port 8081
```

Trigger scrape:

```bash
curl -X POST http://localhost:8081/api/v1/scrape/run
```

## Local Webhook Test

Terminal 1:

```bash
python3 tools/mock_webhook_receiver.py
```

Terminal 2:

```bash
export WEBHOOK_TARGET_URL=http://127.0.0.1:8090/api/v1/webhooks/news
export WEBHOOK_SECRET=local-secret
uvicorn app.main:app --reload --port 8081
```

Then run:

```bash
curl -X POST http://localhost:8081/api/v1/scrape/run
curl -X POST http://localhost:8081/api/v1/outbox/dispatch
```

## Event Envelope

```json
{
  "eventType": "news.created",
  "occurredAt": "2026-03-17T19:35:10Z",
  "source": "klix-scraper",
  "data": {
    "source": "klix",
    "sourceArticleId": "260317188",
    "title": "...",
    "url": "...",
    "publishedAt": "2026-03-17T18:54:00Z",
    "locationName": "Sarajevo",
    "latitude": 43.8563,
    "longitude": 18.4131,
    "locationConfidence": 0.91,
    "precision": "city"
  }
}
```
