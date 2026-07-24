"""Season ops: bootstrap, recompute, readiness, PL seasons."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import AuthenticatedUser, get_current_profile
from app.db import get_db
from app.deps import get_football_provider, require_commissioner, require_platform_admin
from app.models import (
    CompetitionTemplate,
    League,
    LeagueMember,
    Match,
    PoolTeam,
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
    ReadinessCheck,
    ReadinessResponse,
    RecomputeResponse,
)
from app.services.bootstrap import (
    bootstrap_season,
    bootstrap_teams_for_league,
    prior_leagues_blocking,
)
from app.services.members import default_team_name

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
    return BootstrapTeamsResponse(**summary)


@router.post("/leagues/{league_id}/recompute", response_model=RecomputeResponse)
def recompute_scores(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> RecomputeResponse:
    from app.services.sync import earliest_finished_seeds_per_pool, score_changed_matches

    league, _ = membership
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
    summary = score_changed_matches(db, league, seeds)
    db.commit()
    return RecomputeResponse(finished_matches=len(finished), **summary)


@router.get("/leagues/{league_id}/readiness", response_model=ReadinessResponse)
def readiness(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> ReadinessResponse:
    """Return every setup/sync gate as a checklist (all checks always evaluated)."""
    league, _ = membership
    checks: list[ReadinessCheck] = []

    members = list(db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all())
    member_count = len(members)
    required = None
    config = league.config or {}
    if config.get("max_members") is not None:
        try:
            required = max(2, int(config["max_members"]))
        except (TypeError, ValueError):
            required = None

    if required is None:
        checks.append(
            ReadinessCheck(
                key="members",
                label="Manager roster size configured",
                status="error",
                detail="Set the required number of managers in league settings",
            )
        )
    elif member_count == required:
        checks.append(
            ReadinessCheck(
                key="members",
                label=f"Full manager roster ({required})",
                status="ok",
                detail=f"{member_count} of {required} managers joined",
            )
        )
    elif member_count < required:
        checks.append(
            ReadinessCheck(
                key="members",
                label=f"Full manager roster ({required})",
                status="error",
                detail=f"{member_count} of {required} managers joined — invite the rest before drafting",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                key="members",
                label=f"Full manager roster ({required})",
                status="error",
                detail=f"{member_count} of {required} managers joined — remove extras before drafting",
            )
        )

    missing_draft = sum(1 for m in members if m.draft_slot is None)
    if member_count == 0:
        checks.append(
            ReadinessCheck(
                key="draft_order",
                label="Draft order complete",
                status="error",
                detail="No managers to assign draft slots",
            )
        )
    elif missing_draft == 0:
        checks.append(
            ReadinessCheck(
                key="draft_order",
                label="Draft order complete",
                status="ok",
                detail=f"All {member_count} managers have a draft slot",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                key="draft_order",
                label="Draft order complete",
                status="error",
                detail=f"{missing_draft} of {member_count} managers missing a draft slot",
            )
        )

    pools = list(db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all())
    if pools:
        checks.append(
            ReadinessCheck(
                key="pools",
                label="Competitions configured",
                status="ok",
                detail=f"{len(pools)} competition(s)",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                key="pools",
                label="Competitions configured",
                status="error",
                detail="Create competitions from a template or in league settings",
            )
        )

    scoring_pools = [p for p in pools if p.scores_match_results]
    if not pools:
        pass
    elif scoring_pools:
        checks.append(
            ReadinessCheck(
                key="scoring_pools",
                label="Scoring competitions present",
                status="ok",
                detail=f"{len(scoring_pools)} competition(s) score match results",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                key="scoring_pools",
                label="Scoring competitions present",
                status="warning",
                detail="No competition has match scoring enabled — Sync will find nothing to pull",
            )
        )

    for pool in pools:
        label = pool.label or pool.key
        if pool.slot_count >= 1:
            checks.append(
                ReadinessCheck(
                    key=f"slots:{pool.key}",
                    label=f"{label}: roster slots",
                    status="ok",
                    detail=f"{pool.slot_count} slot(s) per manager",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    key=f"slots:{pool.key}",
                    label=f"{label}: roster slots",
                    status="error",
                    detail="slot_count must be at least 1",
                )
            )

        team_count = len(
            list(db.scalars(select(PoolTeam).where(PoolTeam.pool_id == pool.id)).all())
        )
        if team_count > 0:
            checks.append(
                ReadinessCheck(
                    key=f"teams:{pool.key}",
                    label=f"{label}: clubs loaded",
                    status="ok",
                    detail=f"{team_count} club(s)",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    key=f"teams:{pool.key}",
                    label=f"{label}: clubs loaded",
                    status="warning" if not pool.scores_match_results else "error",
                    detail="No clubs yet — use Bootstrap teams (or create-league load)",
                )
            )

        if pool.scores_match_results:
            if pool.competition_code and pool.season_year:
                checks.append(
                    ReadinessCheck(
                        key=f"provider:{pool.key}",
                        label=f"{label}: provider competition",
                        status="ok",
                        detail=f"{pool.competition_code} · {pool.season_year}",
                    )
                )
            else:
                missing = []
                if not pool.competition_code:
                    missing.append("competition code")
                if not pool.season_year:
                    missing.append("season year")
                checks.append(
                    ReadinessCheck(
                        key=f"provider:{pool.key}",
                        label=f"{label}: provider competition",
                        status="error",
                        detail=f"Missing {', '.join(missing)} — Sync skips this competition",
                    )
                )

    errors = [c.detail or c.label for c in checks if c.status == "error"]
    warnings = [c.detail or c.label for c in checks if c.status == "warning"]
    return ReadinessResponse(
        ready=len(errors) == 0,
        checks=checks,
        errors=errors,
        warnings=warnings,
    )


@router.get("/leagues/premier-league/bootstrap-gates")
def bootstrap_gates(
    _: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> dict:
    return {"blockers": prior_leagues_blocking(db, template_key="premier_league")}


@router.post("/leagues/premier-league/seasons", response_model=LeagueDetailResponse)
def start_pl_season(
    payload: BootstrapSeasonRequest,
    _: AuthenticatedUser = Depends(require_platform_admin),
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
    return _league_detail(db, league, member)
