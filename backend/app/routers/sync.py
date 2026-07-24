from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import require_commissioner
from app.models import League, LeagueMember
from app.providers.football_data import FootballDataProvider
from app.services.sync import sync_league_fixtures

router = APIRouter(tags=["sync"])


@router.post("/leagues/{league_id}/sync")
def commissioner_sync(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    settings = get_settings()
    if not settings.football_data_api_token:
        raise HTTPException(status_code=503, detail="football-data.org token not configured")
    with FootballDataProvider(
        settings.football_data_api_token, base_url=settings.football_data_base_url
    ) as provider:
        return sync_league_fixtures(db, league, provider)
