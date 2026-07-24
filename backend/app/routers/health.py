from datetime import UTC, datetime

from fastapi import APIRouter

from app import __version__
from app.config import get_settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        timestamp=datetime.now(UTC),
        dev_tools_enabled=settings.is_development,
    )
