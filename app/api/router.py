from fastapi import APIRouter

from app.api.routes.news import router as news_router
from app.api.routes.outbox import router as outbox_router
from app.api.routes.scrape import router as scrape_router


api_router = APIRouter()
api_router.include_router(news_router)
api_router.include_router(scrape_router)
api_router.include_router(outbox_router)
