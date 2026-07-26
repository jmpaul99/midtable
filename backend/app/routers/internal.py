import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_football_provider, require_cron_secret
from app.models import League
from app.providers.fifa_rankings import FifaRankingsError, ParseFifaRankingsProvider
from app.providers.football_data import FootballDataProvider
from app.services.ranking_catalog import sync_fifa_catalogs
from app.services.sync import sync_league_fixtures

logger = logging.getLogger(__name__)

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
    logger.info("sync-and-score started leagues=%s", len(leagues))
    results = []
    failures = 0
    for league in leagues:
        result = sync_league_fixtures(db, league, provider)
        if not result.get("ok"):
            failures += 1
            logger.warning(
                "sync-and-score league failed league_id=%s error=%s",
                league.public_id,
                result.get("error"),
            )
        results.append(
            {
                "league_id": str(league.public_id),
                "result": result,
            }
        )
    payload = {"ok": failures == 0, "leagues": results, "failures": failures}
    logger.info(
        "sync-and-score finished ok=%s failures=%s leagues=%s",
        payload["ok"],
        failures,
        len(leagues),
    )
    if failures:
        raise HTTPException(status_code=502, detail=payload)
    return payload


@router.post(
    "/internal/sync-fifa-rankings",
    dependencies=[Depends(require_cron_secret)],
)
def sync_fifa_rankings(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Cron entrypoint: refresh FIFA men/women catalogs from Parse and rematerialize."""
    if not settings.parse_api_key.strip():
        raise HTTPException(status_code=503, detail="PARSE_API_KEY is not configured")
    logger.info("sync-fifa-rankings started")
    try:
        with ParseFifaRankingsProvider(
            settings.parse_api_key,
            base_url=settings.parse_fifa_base_url,
        ) as provider:
            payload = sync_fifa_catalogs(db, provider)
    except (FifaRankingsError, ValueError) as exc:
        logger.exception("sync-fifa-rankings failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    logger.info("sync-fifa-rankings finished ok=%s", payload.get("ok"))
    return payload
