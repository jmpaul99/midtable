"""Season ops: bootstrap, recompute, readiness, PL seasons."""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.db import get_db
from app.deps import get_football_provider, require_commissioner
from app.models import (
    CompetitionTemplate,
    League,
    LeagueMember,
    Match,
    Profile,
    TeamPool,
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
    from app.services.sync import earliest_finished_seeds_per_pool, score_changed_matches

    league, _ = membership
    started = time.perf_counter()
    scoring_pool_ids = {
        p.id
        for p in db.scalars(
            select(TeamPool).where(
                TeamPool.league_id == league.id,
                TeamPool.scores_match_results.is_(True),
            )
        ).all()
    }
    matches = list(db.scalars(select(Match).where(Match.league_id == league.id)).all())
    finished, seeds = earliest_finished_seeds_per_pool(
        matches, scoring_pool_ids=scoring_pool_ids
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
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> ReadinessResponse:
    """Return every setup/sync gate as a checklist (all checks always evaluated)."""
    league, _ = membership
    return evaluate_readiness(db, league)


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
