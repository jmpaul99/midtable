"""Season ops: bootstrap, recompute, readiness, PL seasons."""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Literal

from app.auth.jwt import get_current_profile
from app.db import get_db
from app.deps import get_football_provider, require_commissioner
from app.models import (
    CompetitionTemplate,
    League,
    LeagueMember,
    Profile,
)
from app.providers.football_data import FootballDataProvider
from app.routers.league_mappers import _league_detail
from app.schemas.leagues import (
    BootstrapSeasonRequest,
    BootstrapTeamsRequest,
    BootstrapTeamsResponse,
    LeagueDetailResponse,
    ReadinessResponse,
    RecomputeResponse,
)
from app.services.bootstrap import (
    bootstrap_season,
    bootstrap_teams_for_league,
    prior_leagues_blocking,
)
from app.services.members import default_team_name
from app.services.readiness import evaluate_readiness

logger = logging.getLogger(__name__)

router = APIRouter(tags=["league-ops"])

@router.post("/leagues/{league_id}/bootstrap-teams", response_model=BootstrapTeamsResponse)
def bootstrap_teams(
    payload: BootstrapTeamsRequest,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
    provider: FootballDataProvider = Depends(get_football_provider),
) -> BootstrapTeamsResponse:
    league, _ = membership
    summary = bootstrap_teams_for_league(
        db,
        league=league,
        provider=provider,
        pool_provider_params=payload.pool_provider_params,
    )
    db.commit()
    logger.info(
        "bootstrap_teams done league_id=%s summary=%s",
        league.public_id,
        summary,
    )
    return BootstrapTeamsResponse(**summary)


@router.post("/leagues/{league_id}/recompute", response_model=RecomputeResponse)
def recompute_scores(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> RecomputeResponse:
    from app.services.match_queries import matches_for_league, pool_for_match, scoring_pools_for_league
    from app.services.sync import earliest_finished_seeds_per_pool, score_changed_matches

    league, _ = membership
    started = time.perf_counter()
    matches = matches_for_league(db, league)
    scoring_pools = scoring_pools_for_league(db, league)
    scoring_pool_ids = {p.id for p in scoring_pools}
    pool_by_match_id: dict[int, int] = {}
    for m in matches:
        pool = pool_for_match(db, league, m)
        if pool:
            pool_by_match_id[m.id] = pool.id
    finished, seeds = earliest_finished_seeds_per_pool(
        matches, pool_by_match_id=pool_by_match_id, scoring_pool_ids=scoring_pool_ids
    )
    logger.info(
        "recompute_scores start league_id=%s finished=%s seeds=%s",
        league.public_id,
        len(finished),
        len(seeds),
    )
    summary = score_changed_matches(db, league, seeds)
    db.commit()
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "recompute_scores done league_id=%s finished_matches=%s scored=%s "
        "cascaded=%s skipped_missing_snapshot=%s duration_ms=%.1f",
        league.public_id,
        len(finished),
        summary.get("scored", 0),
        summary.get("cascaded", 0),
        summary.get("skipped_missing_snapshot", 0),
        duration_ms,
    )
    return RecomputeResponse(finished_matches=len(finished), **summary)


@router.get("/leagues/{league_id}/readiness", response_model=ReadinessResponse)
def readiness(
    purpose: Literal["draft", "sync"] = Query("draft"),
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> ReadinessResponse:
    """Return draft or sync readiness checklist (default: draft)."""
    league, _ = membership
    if purpose not in ("draft", "sync"):
        raise HTTPException(status_code=400, detail="purpose must be 'draft' or 'sync'")
    return evaluate_readiness(db, league, purpose=purpose)


@router.get("/leagues/premier-league/bootstrap-gates")
def bootstrap_gates(
    _: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> dict:
    return {"blockers": prior_leagues_blocking(db, template_key="premier_league")}


@router.post("/leagues/premier-league/seasons", response_model=LeagueDetailResponse)
def start_pl_season(
    payload: BootstrapSeasonRequest,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
    provider: FootballDataProvider = Depends(get_football_provider),
) -> LeagueDetailResponse:
    template = db.scalars(
        select(CompetitionTemplate).where(CompetitionTemplate.key == payload.template_key)
    ).first()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    league = bootstrap_season(
        db,
        template=template,
        name=payload.name,
        season_label=payload.season_label,
        provider=provider,
        pool_provider_params=payload.pool_provider_params,
        scheduled_start_date=payload.scheduled_start_date,
        scheduled_end_date=payload.scheduled_end_date,
        draft_scheduled_at=payload.draft_scheduled_at,
        pick_timer_seconds=payload.pick_timer_seconds,
        max_members=payload.max_members,
        force=payload.force,
    )
    member = LeagueMember(
        league_id=league.id,
        profile_id=profile.id,
        is_commissioner=True,
        draft_slot=1,
        team_name=default_team_name(profile.display_name),
    )
    db.add(member)
    db.commit()
    db.refresh(league)
    db.refresh(member)
    logger.info(
        "PL season started league_id=%s season_label=%s creator_profile_id=%s",
        league.public_id,
        league.season_label,
        profile.public_id,
    )
    return _league_detail(db, league, member)
