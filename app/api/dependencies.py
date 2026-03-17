from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.db import get_db


def get_container(request: Request):
    return request.app.state.container


def get_db_session() -> Session:
    yield from get_db()
