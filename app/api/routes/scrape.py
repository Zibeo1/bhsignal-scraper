from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_container, get_db_session
from app.schemas.scrape import ScrapeRunRequest, ScrapeRunResponse


router = APIRouter(prefix="/scrape", tags=["scrape"])


@router.post("/run", response_model=ScrapeRunResponse)
def run_scrape(
    body: Optional[ScrapeRunRequest] = None,
    dispatch_outbox: bool = True,
    container=Depends(get_container),
    db: Session = Depends(get_db_session),
) -> ScrapeRunResponse:
    scraper_service = container["scraper_service"]
    outbox_service = container["outbox_service"]

    limit = body.limit if body is not None else None
    result = scraper_service.run_once(db, limit=limit)

    if dispatch_outbox:
        outbox_service.dispatch_pending(db)

    db.commit()

    return ScrapeRunResponse(
        fetched=result.fetched,
        inserted=result.inserted,
        updated=result.updated,
        skipped=result.skipped,
        outbox_enqueued=result.outbox_enqueued,
    )
