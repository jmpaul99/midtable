"""Shared competition standings snapshots from finished matches."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Match, StandingsSnapshot, StandingsSnapshotRow, Team
from app.services.match_adapters import match_to_input
from app.services.match_queries import matches_for_competition
from app.services.scoring import (
    ResultPoints,
    TableRow,
    build_standings_before_kickoff,
    is_finished,
)

logger = logging.getLogger(__name__)

# Competition table points (not fantasy result_points).
FOOTBALL_TABLE_POINTS = ResultPoints(win=Decimal(3), draw=Decimal(1), loss=Decimal(0))
DEFAULT_TIEBREAKS = ("points", "gd", "gf", "name")


def initial_rows_for_competition(
    db: Session,
    *,
    provider: str,
    competition_code: str,
    season_year: int,
) -> list[TableRow]:
    """Teams that appear in shared matches for this competition season."""
    matches = matches_for_competition(
        db,
        provider=provider,
        competition_code=competition_code,
        season_year=season_year,
    )
    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    if not team_ids:
        return []
    teams = db.scalars(select(Team).where(Team.id.in_(team_ids))).all()
    return [TableRow(team_id=t.id, name=t.name) for t in teams]


def build_snapshot_for_kickoff(
    db: Session,
    *,
    provider: str,
    competition_code: str,
    season_year: int,
    kickoff_at: datetime,
    pool_id: int,
    mark_fresh: bool = True,
) -> StandingsSnapshot:
    """Build or refresh shared standings for a competition at kickoff.

    ``pool_id`` is only used for MatchInput cascade grouping / scoring context.
    """
    matches = [
        match_to_input(m, pool_id=pool_id)
        for m in matches_for_competition(
            db,
            provider=provider,
            competition_code=competition_code,
            season_year=season_year,
        )
        if is_finished(match_to_input(m, pool_id=pool_id))
    ]
    ranked = build_standings_before_kickoff(
        team_rows=initial_rows_for_competition(
            db,
            provider=provider,
            competition_code=competition_code,
            season_year=season_year,
        ),
        finished_matches=matches,
        kickoff_at=kickoff_at,
        pool_id=pool_id,
        result_points=FOOTBALL_TABLE_POINTS,
        tiebreaks=DEFAULT_TIEBREAKS,
    )

    existing = db.scalars(
        select(StandingsSnapshot).where(
            StandingsSnapshot.provider == provider,
            StandingsSnapshot.competition_code == competition_code,
            StandingsSnapshot.season_year == season_year,
            StandingsSnapshot.kickoff_at == kickoff_at,
        )
    ).first()
    reused = existing is not None
    if existing:
        for row in list(existing.rows):
            db.delete(row)
        snapshot = existing
        snapshot.stale = not mark_fresh
        snapshot.computed_at = datetime.now(UTC)
    else:
        snapshot = StandingsSnapshot(
            provider=provider,
            competition_code=competition_code,
            season_year=season_year,
            kickoff_at=kickoff_at,
            stale=not mark_fresh,
            computed_at=datetime.now(UTC),
        )
        db.add(snapshot)
        db.flush()

    for row in ranked:
        db.add(
            StandingsSnapshotRow(
                snapshot_id=snapshot.id,
                team_id=row.team_id,
                rank=row.rank,
                played=row.played,
                points=row.points,
                goals_for=row.goals_for,
                goals_against=row.goals_against,
                goal_difference=row.goal_difference,
            )
        )
    db.flush()
    logger.debug(
        "build_snapshot_for_kickoff competition=%s/%s/%s kickoff=%s rows=%s reused=%s",
        provider,
        competition_code,
        season_year,
        kickoff_at.isoformat(),
        len(ranked),
        reused,
    )
    return snapshot


def mark_snapshots_stale_after(
    db: Session,
    *,
    provider: str,
    competition_code: str,
    season_year: int,
    kickoff_at: datetime,
) -> int:
    snapshots = db.scalars(
        select(StandingsSnapshot).where(
            StandingsSnapshot.provider == provider,
            StandingsSnapshot.competition_code == competition_code,
            StandingsSnapshot.season_year == season_year,
            StandingsSnapshot.kickoff_at > kickoff_at,
        )
    ).all()
    for snap in snapshots:
        snap.stale = True
    db.flush()
    count = len(snapshots)
    if count > 0:
        logger.info(
            "mark_snapshots_stale_after competition=%s/%s/%s kickoff=%s stale_count=%s",
            provider,
            competition_code,
            season_year,
            kickoff_at.isoformat(),
            count,
        )
    return count
