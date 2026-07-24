from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import require_cron_secret
from app.models import League
from app.providers.football_data import FootballDataProvider
from app.services.sync import sync_league_fixtures

router = APIRouter(tags=["internal"])


@router.post(
    "/internal/sync-and-score",
    dependencies=[Depends(require_cron_secret)],
)
def sync_and_score(db: Session = Depends(get_db)) -> dict:
    """Cron entrypoint: sync fixtures + score for all active leagues."""
    settings = get_settings()
    if not settings.football_data_api_token:
        return {"ok": False, "error": "football-data.org token not configured"}

    leagues = db.scalars(
        select(League).where(League.status.in_(("active", "drafting")))
    ).all()
    results = []
    with FootballDataProvider(
        settings.football_data_api_token, base_url=settings.football_data_base_url
    ) as provider:
        for league in leagues:
            results.append(
                {
                    "league_id": str(league.public_id),
                    "result": sync_league_fixtures(db, league, provider),
                }
            )
    return {"ok": True, "leagues": results}
