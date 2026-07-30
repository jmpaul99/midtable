"""Internal cron endpoints."""

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
from app.services.draft import run_draft_maintenance
from app.services.platform_jobs import (
    json_safe_fifa_summary,
    record_cron_platform_result,
)
from app.services.ranking_catalog import sync_fifa_catalogs
from app.services.sync import sync_all_active_competitions_then_score

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
    """Cron entrypoint: sync each competition once, then score all active leagues."""
    leagues = list(
        db.scalars(
            select(League).where(League.status.in_(("active", "drafting")))
        ).all()
    )
    logger.info("sync-and-score started leagues=%s", len(leagues))
    payload = sync_all_active_competitions_then_score(db, provider, leagues)
    logger.info(
        "sync-and-score finished ok=%s failures=%s competitions=%s leagues=%s",
        payload.get("ok"),
        payload.get("failures"),
        len(payload.get("competitions") or []),
        len(payload.get("leagues") or []),
    )
    if payload.get("failures"):
        raise HTTPException(status_code=502, detail=payload)
    return payload


@router.post(
    "/internal/draft-maintenance",
    dependencies=[Depends(require_cron_secret)],
)
def draft_maintenance(db: Session = Depends(get_db)) -> dict:
    """Cron entrypoint: auto-open scheduled drafts and auto-pick expired clocks."""
    logger.info("draft-maintenance started")
    payload = run_draft_maintenance(db)
    logger.info(
        "draft-maintenance finished leagues=%s results=%s",
        payload.get("leagues_considered"),
        len(payload.get("results") or []),
    )
    return payload


@router.post(
    "/internal/sync-fifa-rankings",
    dependencies=[Depends(require_cron_secret)],
)
def sync_fifa_rankings(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Cron entrypoint: refresh FIFA men/women catalogs from Parse."""
    if not settings.parse_api_key.strip():
        raise HTTPException(status_code=503, detail="PARSE_API_KEY is not configured")
    logger.info("sync-fifa-rankings started")
    try:
        with ParseFifaRankingsProvider(
            settings.parse_api_key,
            base_url=settings.parse_fifa_base_url,
        ) as fifa_provider:
            payload = sync_fifa_catalogs(db, fifa_provider)
    except (FifaRankingsError, ValueError) as exc:
        logger.exception("sync-fifa-rankings failed")
        record_cron_platform_result(
            db,
            kind="fifa_rankings",
            ok=False,
            error=str(exc),
        )
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    summary = json_safe_fifa_summary(payload)
    record_cron_platform_result(
        db,
        kind="fifa_rankings",
        ok=bool(payload.get("ok")),
        summary=summary,
        error=None if payload.get("ok") else str(payload.get("error") or "FIFA sync failed"),
    )
    db.commit()
    logger.info("sync-fifa-rankings finished ok=%s", payload.get("ok"))
    return payload
