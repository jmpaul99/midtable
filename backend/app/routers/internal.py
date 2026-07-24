from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_football_provider, require_cron_secret
from app.models import League
from app.providers.football_data import FootballDataProvider
from app.services.sync import sync_league_fixtures

router = APIRouter(tags=["internal"])


@router.post(
    "/internal/sync-and-score",
    dependencies=[Depends(require_cron_secret)],
)
def sync_and_score(
    db: Session = Depends(get_db),
    provider: FootballDataProvider = Depends(get_football_provider),
) -> dict:
    """Cron entrypoint: sync fixtures + score for all active leagues."""
    leagues = db.scalars(
        select(League).where(League.status.in_(("active", "drafting")))
    ).all()
    results = []
    failures = 0
    for league in leagues:
        result = sync_league_fixtures(db, league, provider)
        if not result.get("ok"):
            failures += 1
        results.append(
            {
                "league_id": str(league.public_id),
                "result": result,
            }
        )
    payload = {"ok": failures == 0, "leagues": results, "failures": failures}
    if failures:
        raise HTTPException(status_code=502, detail=payload)
    return payload
