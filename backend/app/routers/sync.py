from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_football_provider, require_commissioner
from app.models import League, LeagueMember
from app.providers.football_data import FootballDataProvider
from app.services.sync import sync_league_fixtures

router = APIRouter(tags=["sync"])


def _raise_for_sync_result(result: dict) -> dict:
    if result.get("ok"):
        return result
    code = int(result.get("status_code") or 502)
    raise HTTPException(status_code=code, detail=result.get("error") or "Sync failed")


@router.post("/leagues/{league_id}/sync")
def commissioner_sync(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
    provider: FootballDataProvider = Depends(get_football_provider),
) -> dict:
    league, _ = membership
    return _raise_for_sync_result(sync_league_fixtures(db, league, provider))
