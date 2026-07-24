"""Season bootstrap with end-date gates."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BonusType,
    CompetitionTemplate,
    DraftState,
    League,
    PoolTeam,
    Team,
    TeamPool,
)
from app.providers.base import FootballProvider


def prior_leagues_blocking(
    db: Session,
    *,
    template_key: str,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Return prior leagues that block starting a new season for this template family."""
    today = today or datetime.now(UTC).date()
    template = db.scalars(
        select(CompetitionTemplate).where(CompetitionTemplate.key == template_key)
    ).first()
    if template is None:
        return []
    leagues = db.scalars(
        select(League).where(League.template_id == template.id)
    ).all()
    blockers: list[dict[str, Any]] = []
    for league in leagues:
        ended = league.status == "complete" or (
            league.scheduled_end_date is not None and league.scheduled_end_date < today
        )
        if league.status in {"pre_draft", "drafting", "active"} and not ended:
            blockers.append(
                {
                    "id": str(league.public_id),
                    "name": league.name,
                    "season_label": league.season_label,
                    "status": league.status,
                    "scheduled_end_date": (
                        league.scheduled_end_date.isoformat()
                        if league.scheduled_end_date
                        else None
                    ),
                    "reason": "prior season still open",
                }
            )
    return blockers


def bootstrap_season(
    db: Session,
    *,
    template: CompetitionTemplate,
    name: str,
    season_label: str,
    provider: FootballProvider,
    pool_provider_params: list[dict[str, Any]],
    scheduled_start_date: date | None = None,
    scheduled_end_date: date | None = None,
    force: bool = False,
) -> League:
    blockers = prior_leagues_blocking(db, template_key=template.key)
    if blockers and not force:
        raise HTTPException(
            status_code=409,
            detail={"message": "prior seasons block bootstrap", "blockers": blockers},
        )

    # Validate provider seasons for each scoring / listed pool
    for params in pool_provider_params:
        code = params["competition_code"]
        year = int(params["season_year"])
        info, _ = provider.resolve_competition_season(code, year)
        if not info.available:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "provider season not available",
                    "competition_code": code,
                    "season_year": year,
                    "provider_message": info.message,
                },
            )

    league = League(
        template_id=template.id,
        name=name,
        season_label=season_label,
        status="pre_draft",
        draft_style=template.draft_style,
        preassign_mode=template.preassign_mode,
        result_points=deepcopy(template.result_points),
        upset_rules=deepcopy(template.upset_rules),
        leaderboard_phases=deepcopy(template.leaderboard_phases),
        leaderboard_tiebreaks=deepcopy(template.leaderboard_tiebreaks),
        buy_in=template.buy_in,
        payouts=deepcopy(template.payouts),
        scheduled_start_date=scheduled_start_date,
        scheduled_end_date=scheduled_end_date,
    )
    db.add(league)
    db.flush()

    params_by_key = {p["key"]: p for p in pool_provider_params}
    for definition in template.pool_definitions or []:
        key = definition["key"]
        params = params_by_key.get(key, {})
        pool = TeamPool(
            league_id=league.id,
            key=key,
            label=definition.get("label", key),
            scores_match_results=bool(definition.get("scores_match_results", True)),
            slot_count=int(definition.get("slot_count", definition.get("slots_per_member", 0))),
            tie_break_order=definition.get(
                "tie_break_order", ["points", "gd", "gf", "name"]
            ),
            provider=params.get("provider", definition.get("provider", "football-data.org")),
            competition_code=params.get(
                "competition_code", definition.get("competition_code")
            ),
            season_year=params.get("season_year", definition.get("season_year")),
        )
        db.add(pool)
        db.flush()

        if pool.competition_code and pool.season_year:
            teams, _ = provider.list_teams(pool.competition_code, int(pool.season_year))
            for pt in teams:
                team = db.scalars(
                    select(Team).where(
                        Team.provider == pool.provider,
                        Team.external_id == pt.external_id,
                    )
                ).first()
                if team is None:
                    team = Team(
                        provider=pool.provider,
                        external_id=pt.external_id,
                        name=pt.name,
                        short_name=pt.short_name,
                        tla=pt.tla,
                        crest_url=pt.crest_url,
                    )
                    db.add(team)
                    db.flush()
                db.add(PoolTeam(pool_id=pool.id, team_id=team.id))

    for index, bonus in enumerate(template.bonus_types or []):
        db.add(
            BonusType(
                league_id=league.id,
                key=bonus["key"],
                label=bonus["label"],
                default_points=Decimal(str(bonus.get("default_points", bonus.get("points", 0)))),
                sort_order=int(bonus.get("sort_order", index)),
                include_in_phases=bonus.get("include_in_phases", []),
            )
        )

    db.add(DraftState(league_id=league.id, current_pick_number=1, status="pending"))
    db.flush()
    return league
