from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_container, get_db_session
from app.schemas.outbox import OutboxDispatchResponse, OutboxStatusResponse


router = APIRouter(prefix="/outbox", tags=["outbox"])


@router.get("/status", response_model=OutboxStatusResponse)
def outbox_status(container=Depends(get_container), db: Session = Depends(get_db_session)) -> OutboxStatusResponse:
    outbox_service = container["outbox_service"]
    counts = outbox_service.get_status_counts(db)
    return OutboxStatusResponse(
        pending=counts.get("pending", 0),
        failed=counts.get("failed", 0),
        delivered=counts.get("delivered", 0),
    )


@router.post("/dispatch", response_model=OutboxDispatchResponse)
def outbox_dispatch(
    container=Depends(get_container),
    db: Session = Depends(get_db_session),
) -> OutboxDispatchResponse:
    outbox_service = container["outbox_service"]
    result = outbox_service.dispatch_pending(db)
    db.commit()
    return OutboxDispatchResponse(
        delivered=result.delivered,
        failed=result.failed,
        retried=result.retried,
    )
