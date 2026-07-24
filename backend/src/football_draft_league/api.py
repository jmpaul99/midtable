from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from football_draft_league import __version__
from football_draft_league.config import get_settings
from football_draft_league.routes import router as application_router

router = APIRouter()
router.include_router(application_router, prefix=get_settings().api_prefix)


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, timestamp=datetime.now(UTC))
