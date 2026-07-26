"""Season bootstrap with end-date gates."""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

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
from app.services.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
)

logger = logging.getLogger(__name__)


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
    max_members: int | None = None,
    force: bool = False,
) -> League:
    blockers = prior_leagues_blocking(db, template_key=template.key)
    if blockers and not force:
        raise ConflictError({"message": "prior seasons block bootstrap", "blockers": blockers},
        )

    # Validate provider seasons for each scoring / listed pool
    for params in pool_provider_params:
        code = params["competition_code"]
        year = int(params["season_year"])
        info, _ = provider.resolve_competition_season(code, year)
        if not info.available:
            logger.warning(
                "bootstrap_season provider unavailable competition_code=%s season_year=%s "
                "message=%s",
                code,
                year,
                info.message,
            )
            raise ConflictError({
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
        config={
            **({"max_members": max_members} if max_members is not None else {}),
            "roster_club_order": (
                template.roster_club_order
                if template.roster_club_order in ("draft", "competition")
                else "draft"
            ),
        },
        scheduled_start_date=scheduled_start_date,
        scheduled_end_date=scheduled_end_date,
    )
    db.add(league)
    db.flush()

    params_by_key = {p["key"]: p for p in pool_provider_params}
    for index, definition in enumerate(template.pool_definitions or []):
        key = definition["key"]
        params = params_by_key.get(key, {})
        pool = TeamPool(
            league_id=league.id,
            key=key,
            label=definition.get("label", key),
            scores_match_results=bool(definition.get("scores_match_results", True)),
            slot_count=int(definition.get("slot_count", definition.get("slots_per_member", 0))),
            sort_order=int(definition.get("sort_order", index + 1)),
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
    from app.services.ranking_catalog import ensure_fixed_ranking_for_league

    ensure_fixed_ranking_for_league(db, league)
    db.flush()
    logger.info(
        "bootstrap_season ok league_id=%s name=%s season_label=%s pools=%s",
        league.public_id,
        league.name,
        league.season_label,
        len(template.pool_definitions or []),
    )
    return league


def attach_template_structure(
    db: Session,
    *,
    league: League,
    template: CompetitionTemplate,
) -> None:
    """Clone pools, bonus types, and draft state from a template without provider calls."""
    for index, definition in enumerate(template.pool_definitions or []):
        key = definition["key"]
        db.add(
            TeamPool(
                league_id=league.id,
                key=key,
                label=definition.get("label", key),
                scores_match_results=bool(definition.get("scores_match_results", True)),
                slot_count=int(definition.get("slot_count", definition.get("slots_per_member", 0))),
                sort_order=int(definition.get("sort_order", index + 1)),
                tie_break_order=definition.get(
                    "tie_break_order", ["points", "gd", "gf", "name"]
                ),
                provider=definition.get("provider", "football-data.org"),
                competition_code=definition.get("competition_code"),
                season_year=definition.get("season_year"),
            )
        )
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
    existing = db.scalars(select(DraftState).where(DraftState.league_id == league.id)).first()
    if existing is None:
        db.add(DraftState(league_id=league.id, current_pick_number=1, status="pending"))
    db.flush()


def bootstrap_teams_for_league(
    db: Session,
    *,
    league: League,
    provider: FootballProvider,
    pool_provider_params: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Load provider teams into existing league pools (does not create the league)."""
    params_by_key = {p["key"]: p for p in (pool_provider_params or []) if "key" in p}
    pools = list(db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all())
    if not pools:
        raise ConflictError("League has no pools to bootstrap")

    created_teams = 0
    linked = 0
    skipped_existing = 0
    pool_summaries: list[dict[str, Any]] = []

    for pool in pools:
        override = params_by_key.get(pool.key, {})
        if "competition_code" in override:
            pool.competition_code = override["competition_code"]
        if "season_year" in override:
            pool.season_year = int(override["season_year"])
        if "provider" in override:
            pool.provider = override["provider"]

        if not pool.competition_code or not pool.season_year:
            pool_summaries.append(
                {
                    "pool_key": pool.key,
                    "error": "missing competition_code or season_year",
                    "linked": 0,
                }
            )
            continue

        info, _ = provider.resolve_competition_season(
            pool.competition_code, int(pool.season_year)
        )
        if not info.available:
            logger.warning(
                "bootstrap_teams provider unavailable league_id=%s pool_key=%s "
                "competition_code=%s season_year=%s message=%s",
                league.public_id,
                pool.key,
                pool.competition_code,
                pool.season_year,
                info.message,
            )
            raise ConflictError({
                    "message": "provider season not available",
                    "pool_key": pool.key,
                    "competition_code": pool.competition_code,
                    "season_year": pool.season_year,
                    "provider_message": info.message,
                },
            )

        teams, _ = provider.list_teams(pool.competition_code, int(pool.season_year))
        pool_linked = 0
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
                created_teams += 1
            existing_link = db.scalars(
                select(PoolTeam).where(
                    PoolTeam.pool_id == pool.id,
                    PoolTeam.team_id == team.id,
                )
            ).first()
            if existing_link:
                skipped_existing += 1
                continue
            db.add(PoolTeam(pool_id=pool.id, team_id=team.id))
            linked += 1
            pool_linked += 1
        pool_summaries.append(
            {
                "pool_key": pool.key,
                "competition_code": pool.competition_code,
                "season_year": pool.season_year,
                "linked": pool_linked,
                "provider_team_count": len(teams),
            }
        )

    db.flush()
    from app.services.ranking_catalog import ensure_fixed_ranking_for_league

    ensure_fixed_ranking_for_league(db, league)
    db.flush()
    summary = {
        "created_teams": created_teams,
        "linked": linked,
        "skipped_existing": skipped_existing,
        "pools": pool_summaries,
    }
    logger.info(
        "bootstrap_teams_for_league ok league_id=%s created_teams=%s linked=%s "
        "skipped_existing=%s pools=%s",
        league.public_id,
        created_teams,
        linked,
        skipped_existing,
        len(pool_summaries),
    )
    return summary
