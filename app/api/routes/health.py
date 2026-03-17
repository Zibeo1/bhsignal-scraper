from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_container, get_db_session


router = APIRouter(tags=["health"])


@router.get("/health")
def health(container=Depends(get_container), db: Session = Depends(get_db_session)) -> dict:
    db.execute(text("SELECT 1"))
    scheduler = container["scheduler"]
    return {
        "status": "ok",
        "service": container["settings"].app_name,
        "schedulerRunning": scheduler.scheduler.running,
    }
