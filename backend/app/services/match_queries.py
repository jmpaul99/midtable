"""Query helpers for shared competition-scoped matches."""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.models import League, Match, TeamPool

CompetitionKey = tuple[str, str, int]

FINISHED_STATUSES = frozenset({"FINISHED", "AWARDED"})


def scoring_pools_for_league(db: Session, league: League) -> list[TeamPool]:
    return list(
        db.scalars(
            select(TeamPool)
            .where(
                TeamPool.league_id == league.id,
                TeamPool.scores_match_results.is_(True),
            )
            .order_by(TeamPool.sort_order, TeamPool.id)
        ).all()
    )


def competition_keys_from_pools(pools: list[TeamPool]) -> list[CompetitionKey]:
    keys: list[CompetitionKey] = []
    seen: set[CompetitionKey] = set()
    for pool in pools:
        if pool.competition_code is None or pool.season_year is None:
            continue
        key = (pool.provider, pool.competition_code, pool.season_year)
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def competition_key_predicate(keys: list[CompetitionKey]) -> ColumnElement[bool] | None:
    if not keys:
        return None
    return or_(
        *[
            and_(
                Match.provider == provider,
                Match.competition_code == competition_code,
                Match.season_year == season_year,
            )
            for provider, competition_code, season_year in keys
        ]
    )


def matches_for_competition(
    db: Session,
    *,
    provider: str,
    competition_code: str,
    season_year: int,
) -> list[Match]:
    return list(
        db.scalars(
            select(Match)
            .where(
                Match.provider == provider,
                Match.competition_code == competition_code,
                Match.season_year == season_year,
            )
            .order_by(Match.kickoff_at, Match.id)
        ).all()
    )


def matches_for_pool(db: Session, pool: TeamPool) -> list[Match]:
    if pool.competition_code is None or pool.season_year is None:
        return []
    return matches_for_competition(
        db,
        provider=pool.provider,
        competition_code=pool.competition_code,
        season_year=pool.season_year,
    )


def matches_for_league(db: Session, league: League) -> list[Match]:
    pools = scoring_pools_for_league(db, league)
    matches: list[Match] = []
    seen_ids: set[int] = set()
    for provider, competition_code, season_year in competition_keys_from_pools(pools):
        for match in matches_for_competition(
            db,
            provider=provider,
            competition_code=competition_code,
            season_year=season_year,
        ):
            if match.id in seen_ids:
                continue
            seen_ids.add(match.id)
            matches.append(match)
    matches.sort(key=lambda m: (m.kickoff_at, m.id))
    return matches


def pool_for_match(db: Session, league: League, match: Match) -> TeamPool | None:
    for pool in scoring_pools_for_league(db, league):
        if (
            pool.provider == match.provider
            and pool.competition_code == match.competition_code
            and pool.season_year == match.season_year
        ):
            return pool
    return None


def pool_lookup_for_league(db: Session, league: League) -> dict[CompetitionKey, TeamPool]:
    lookup: dict[CompetitionKey, TeamPool] = {}
    for pool in scoring_pools_for_league(db, league):
        if pool.competition_code is None or pool.season_year is None:
            continue
        key = (pool.provider, pool.competition_code, pool.season_year)
        lookup.setdefault(key, pool)
    return lookup
