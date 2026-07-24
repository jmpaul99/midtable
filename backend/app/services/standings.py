"""Standings snapshot build from finished matches (strict kickoff ordering)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Match, StandingsSnapshot, StandingsSnapshotRow, Team, TeamPool
from app.services.match_adapters import match_to_input
from app.services.scoring import (
    ResultPoints,
    TableRow,
    build_standings_before_kickoff,
    is_finished,
)


def initial_rows_for_pool(db: Session, pool: TeamPool) -> list[TableRow]:
    from app.models import PoolTeam

    teams = db.scalars(
        select(Team)
        .join(PoolTeam, PoolTeam.team_id == Team.id)
        .where(PoolTeam.pool_id == pool.id)
    ).all()
    return [TableRow(team_id=t.id, name=t.name) for t in teams]


def build_snapshot_for_kickoff(
    db: Session,
    *,
    pool: TeamPool,
    kickoff_at: datetime,
    result_points: ResultPoints,
    mark_fresh: bool = True,
) -> StandingsSnapshot:
    matches = [
        match_to_input(m)
        for m in db.scalars(select(Match).where(Match.pool_id == pool.id)).all()
        if is_finished(match_to_input(m))
    ]
    ranked = build_standings_before_kickoff(
        team_rows=initial_rows_for_pool(db, pool),
        finished_matches=matches,
        kickoff_at=kickoff_at,
        pool_id=pool.id,
        result_points=result_points,
        tiebreaks=tuple(pool.tie_break_order or ["points", "gd", "gf", "name"]),
    )

    existing = db.scalars(
        select(StandingsSnapshot).where(
            StandingsSnapshot.pool_id == pool.id,
            StandingsSnapshot.kickoff_at == kickoff_at,
        )
    ).first()
    if existing:
        for row in list(existing.rows):
            db.delete(row)
        snapshot = existing
        snapshot.stale = not mark_fresh
        snapshot.computed_at = datetime.now(UTC)
    else:
        snapshot = StandingsSnapshot(
            pool_id=pool.id,
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
    return snapshot


def mark_snapshots_stale_after(db: Session, pool_id: int, kickoff_at: datetime) -> int:
    snapshots = db.scalars(
        select(StandingsSnapshot).where(
            StandingsSnapshot.pool_id == pool_id,
            StandingsSnapshot.kickoff_at > kickoff_at,
        )
    ).all()
    for snap in snapshots:
        snap.stale = True
    db.flush()
    return len(snapshots)
