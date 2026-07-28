"""Query helpers for shared competition-scoped matches."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal, TypeVar

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import ColumnElement

from app.models import League, Match, ScoringEvent, Team, TeamPool
from app.services.match_constants import FINISHED_STATUSES

CompetitionKey = tuple[str, str, int]
MatchSort = Literal["kickoff_asc", "kickoff_desc", "points_desc"]
TMapped = TypeVar("TMapped")

__all__ = [
    "CompetitionKey",
    "FINISHED_STATUSES",
    "MatchSort",
    "competition_key_predicate",
    "competition_key_predicate_for",
    "competition_keys_from_pools",
    "fill_mapped_match_page",
    "matches_for_competition",
    "matches_for_league",
    "matches_for_pool",
    "paginate_matches",
    "pool_for_match",
    "pool_lookup_for_league",
    "scoring_pools_for_league",
]


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


def competition_key_predicate_for(
    model: Any,
    keys: list[CompetitionKey],
) -> ColumnElement[bool] | None:
    """OR of (provider, competition_code, season_year) triples for any mapped model."""
    if not keys:
        return None
    return or_(
        *[
            and_(
                model.provider == provider,
                model.competition_code == competition_code,
                model.season_year == season_year,
            )
            for provider, competition_code, season_year in keys
        ]
    )


def competition_key_predicate(keys: list[CompetitionKey]) -> ColumnElement[bool] | None:
    return competition_key_predicate_for(Match, keys)


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


def paginate_matches(
    db: Session,
    *,
    keys: list[CompetitionKey],
    limit: int,
    offset: int,
    filters: Sequence[ColumnElement[bool]] | None = None,
    order: MatchSort = "kickoff_desc",
    league_id: int | None = None,
) -> tuple[list[Match], bool]:
    """Page matches whose competition keys and both teams exist.

    Fetches ``limit + 1`` rows so callers can set ``has_more`` without a count query.
    ``order="points_desc"`` requires ``league_id`` (league-scoped scoring totals).
    """
    key_pred = competition_key_predicate(keys)
    if key_pred is None:
        return [], False
    if order == "points_desc" and league_id is None:
        raise ValueError("league_id is required for points_desc order")

    home_team = aliased(Team)
    away_team = aliased(Team)
    where_clauses: list[ColumnElement[bool]] = [key_pred]
    if filters:
        where_clauses.extend(filters)

    stmt = (
        select(Match)
        .join(home_team, home_team.id == Match.home_team_id)
        .join(away_team, away_team.id == Match.away_team_id)
        .where(*where_clauses)
    )

    if order == "points_desc":
        pts_subq = (
            select(
                ScoringEvent.match_id.label("match_id"),
                ScoringEvent.team_id.label("team_id"),
                func.coalesce(func.sum(ScoringEvent.points), 0).label("pts"),
            )
            .where(ScoringEvent.league_id == league_id)
            .group_by(ScoringEvent.match_id, ScoringEvent.team_id)
            .subquery()
        )
        home_pts = pts_subq.alias("home_pts")
        away_pts = pts_subq.alias("away_pts")
        stmt = (
            stmt.outerjoin(
                home_pts,
                and_(
                    home_pts.c.match_id == Match.id,
                    home_pts.c.team_id == Match.home_team_id,
                ),
            )
            .outerjoin(
                away_pts,
                and_(
                    away_pts.c.match_id == Match.id,
                    away_pts.c.team_id == Match.away_team_id,
                ),
            )
            .order_by(
                func.greatest(
                    func.coalesce(home_pts.c.pts, 0),
                    func.coalesce(away_pts.c.pts, 0),
                ).desc(),
                Match.kickoff_at.desc(),
                Match.id.desc(),
            )
        )
    elif order == "kickoff_asc":
        stmt = stmt.order_by(Match.kickoff_at.asc(), Match.id.asc())
    else:
        stmt = stmt.order_by(Match.kickoff_at.desc(), Match.id.desc())

    rows = list(db.scalars(stmt.offset(offset).limit(limit + 1)).unique().all())
    has_more = len(rows) > limit
    return rows[:limit], has_more


def fill_mapped_match_page(
    *,
    limit: int,
    offset: int,
    fetch_matches: Callable[[int, int], tuple[list[Match], bool]],
    map_matches: Callable[[list[Match]], list[TMapped]],
) -> tuple[list[TMapped], bool, int]:
    """Fill a response page when mapping may drop SQL match rows.

    ``offset`` / returned ``next_offset`` are SQL match cursors. Callers that map
    matches to API rows (and skip orphans) must page with ``next_offset``, not the
    returned item count, so clients neither skip nor stall on dropped rows.
    """
    items: list[TMapped] = []
    sql_offset = offset
    sql_has_more = True
    while len(items) < limit and sql_has_more:
        batch_limit = limit - len(items)
        matches, sql_has_more = fetch_matches(batch_limit, sql_offset)
        sql_offset += len(matches)
        if not matches:
            break
        items.extend(map_matches(matches))
    has_more = len(items) >= limit and sql_has_more
    return items, has_more, sql_offset


def pool_lookup_for_league(
    db: Session,
    league: League,
    *,
    pools: list[TeamPool] | None = None,
) -> dict[CompetitionKey, TeamPool]:
    if pools is None:
        pools = scoring_pools_for_league(db, league)
    lookup: dict[CompetitionKey, TeamPool] = {}
    for pool in pools:
        if pool.competition_code is None or pool.season_year is None:
            continue
        key = (pool.provider, pool.competition_code, pool.season_year)
        lookup.setdefault(key, pool)
    return lookup


def pool_for_match(
    db: Session,
    league: League,
    match: Match,
    *,
    lookup: dict[CompetitionKey, TeamPool] | None = None,
) -> TeamPool | None:
    if lookup is None:
        lookup = pool_lookup_for_league(db, league)
    if match.competition_code is None or match.season_year is None:
        return None
    return lookup.get((match.provider, match.competition_code, match.season_year))
