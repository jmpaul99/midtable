"""Season ops: bootstrap, recompute, readiness, PL seasons."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
    EarliestKickoffRequest,
    EarliestKickoffResponse,
    LeagueDetailResponse,
    LeagueJobResponse,
    ReadinessResponse,
)
from app.services.bootstrap import (
    bootstrap_season,
    bootstrap_teams_for_league,
    prior_leagues_blocking,
)
from app.services.draft_schedule import earliest_kickoff_for_keys
from app.services.league_jobs import ActiveJobConflict, enqueue_league_job, trigger_job_run
from app.services.members import default_team_name
from app.services.readiness import evaluate_readiness

logger = logging.getLogger(__name__)

router = APIRouter(tags=["league-ops"])


@router.post("/competitions/earliest-kickoff", response_model=EarliestKickoffResponse)
def earliest_competition_kickoff(
    payload: EarliestKickoffRequest,
    _: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> EarliestKickoffResponse:
    """Return the earliest known kickoff across the given competitions."""
    keys = [
        (item.provider, item.competition_code, item.season_year)
        for item in payload.competitions
    ]
    return EarliestKickoffResponse(kickoff_at=earliest_kickoff_for_keys(db, keys))

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


@router.post("/leagues/{league_id}/recompute", response_model=LeagueJobResponse)
def recompute_scores(
    response: Response,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> LeagueJobResponse:
    league, _ = membership
    logger.info(
        "recompute_scores enqueue league_id=%s",
        league.public_id,
    )
    try:
        job = enqueue_league_job(
            db,
            league,
            kind="recompute",
            source="commissioner",
            created_by_profile_id=profile.id,
        )
    except ActiveJobConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "job": {
                    "id": str(exc.job.public_id),
                    "kind": exc.job.kind,
                    "source": exc.job.source,
                    "status": exc.job.status,
                },
            },
        ) from exc
    trigger_job_run(job.public_id)
    response.status_code = status.HTTP_202_ACCEPTED
    return LeagueJobResponse(
        id=job.public_id,
        kind=job.kind,
        source=job.source,
        status=job.status,
        error=job.error,
        summary=job.summary,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


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
