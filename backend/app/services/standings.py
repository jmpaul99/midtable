"""Shared competition standings snapshots from finished matches and provider tables."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    PoolTeam,
    StandingsSnapshot,
    StandingsSnapshotRow,
    Team,
    TeamPool,
)
from app.providers.base import FootballProvider, ProviderStandingRow
from app.providers.football_data import FootballDataError, respect_rate_limit
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
        snapshot = existing
        snapshot.stale = not mark_fresh
        snapshot.computed_at = datetime.now(UTC)
    else:
        snapshot = None
        try:
            with db.begin_nested():
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
        except IntegrityError:
            snapshot = db.scalars(
                select(StandingsSnapshot).where(
                    StandingsSnapshot.provider == provider,
                    StandingsSnapshot.competition_code == competition_code,
                    StandingsSnapshot.season_year == season_year,
                    StandingsSnapshot.kickoff_at == kickoff_at,
                )
            ).first()
            if snapshot is None:
                raise
            reused = True
            snapshot.stale = not mark_fresh
            snapshot.computed_at = datetime.now(UTC)

    # Flush deletes before inserts so (snapshot_id, team_id) unique does not
    # collide when refreshing an existing snapshot (Actions #349/#350 → 502
    # PendingRollbackError wrapping UniqueViolation on standings_snapshot_rows).
    _replace_snapshot_rows(
        db,
        snapshot,
        [
            (
                row.team_id,
                row.rank,
                row.played,
                int(row.points),
                row.goals_for,
                row.goals_against,
                row.goal_difference,
            )
            for row in ranked
        ],
    )
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


def oldest_snapshot_for_competition(
    db: Session,
    *,
    provider: str,
    competition_code: str,
    season_year: int,
) -> StandingsSnapshot | None:
    """Oldest snapshot for a competition season (previous-final baseline when present)."""
    return db.scalars(
        select(StandingsSnapshot)
        .where(
            StandingsSnapshot.provider == provider,
            StandingsSnapshot.competition_code == competition_code,
            StandingsSnapshot.season_year == season_year,
        )
        .order_by(StandingsSnapshot.kickoff_at.asc())
        .limit(1)
    ).first()


def _snapshots_for_competition(
    db: Session,
    *,
    provider: str,
    competition_code: str,
    season_year: int,
) -> list[StandingsSnapshot]:
    return list(
        db.scalars(
            select(StandingsSnapshot)
            .where(
                StandingsSnapshot.provider == provider,
                StandingsSnapshot.competition_code == competition_code,
                StandingsSnapshot.season_year == season_year,
            )
            .order_by(StandingsSnapshot.kickoff_at.asc())
        ).all()
    )


def previous_final_snapshot_for_competition(
    db: Session,
    *,
    provider: str,
    competition_code: str,
    season_year: int,
) -> StandingsSnapshot | None:
    """Previous-final snapshot, using a conservative fallback without an opener."""
    snapshots = _snapshots_for_competition(
        db,
        provider=provider,
        competition_code=competition_code,
        season_year=season_year,
    )
    opener = next(
        (
            snap
            for snap in snapshots
            if snap.rows and all(int(row.played or 0) == 0 for row in snap.rows)
        ),
        None,
    )
    if opener is None:
        for snap in snapshots:
            played = [int(row.played or 0) for row in snap.rows]
            if played and all(value > 0 for value in played) and min(played) >= 20:
                return snap
        return None

    opener_kickoff = _aware(opener.kickoff_at)
    for snap in snapshots:
        rows = list(snap.rows)
        if (
            _aware(snap.kickoff_at) < opener_kickoff
            and rows
            and any(int(r.played or 0) > 0 for r in rows)
        ):
            return snap
    return None


def zeroed_opener_snapshot_for_competition(
    db: Session,
    *,
    provider: str,
    competition_code: str,
    season_year: int,
) -> StandingsSnapshot | None:
    """Season-opener snapshot where every row is still played == 0."""
    for snap in _snapshots_for_competition(
        db,
        provider=provider,
        competition_code=competition_code,
        season_year=season_year,
    ):
        rows = list(snap.rows)
        if rows and all(int(r.played or 0) == 0 for r in rows):
            return snap
    return None


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _snapshot_at(
    db: Session,
    *,
    provider: str,
    competition_code: str,
    season_year: int,
    kickoff_at: datetime,
) -> StandingsSnapshot | None:
    return db.scalars(
        select(StandingsSnapshot).where(
            StandingsSnapshot.provider == provider,
            StandingsSnapshot.competition_code == competition_code,
            StandingsSnapshot.season_year == season_year,
            StandingsSnapshot.kickoff_at == kickoff_at,
        )
    ).first()


def _replace_snapshot_rows(
    db: Session,
    snapshot: StandingsSnapshot,
    rows: list[tuple[int, int, int, int, int, int, int]],
) -> None:
    """Replace all rows for a snapshot.

    ``rows``: (team_id, rank, played, points, gf, ga, gd).

    Must not rely on iterating ``snapshot.rows`` for deletes: after a prior
    replace in the same Session, delete-orphan leaves deleted "zombie" instances
    in the identity-map collection while newly inserted rows (added via FK only)
    are not attached. A second ORM delete then targets stale PKs (no-op on
    Postgres, which does not reuse identities) and the following insert hits
    ``standings_snapshot_rows_snapshot_team_key`` — Sync #380 after #27.
    """
    db.execute(
        delete(StandingsSnapshotRow).where(
            StandingsSnapshotRow.snapshot_id == snapshot.id
        )
    )
    # Drop zombies / empty stale collection so append loads a clean set.
    db.expire(snapshot, ["rows"])
    for team_id, rank, played, points, gf, ga, gd in rows:
        snapshot.rows.append(
            StandingsSnapshotRow(
                team_id=team_id,
                rank=rank,
                played=played,
                points=points,
                goals_for=gf,
                goals_against=ga,
                goal_difference=gd,
            )
        )
    db.flush()


def _upsert_snapshot_with_rows(
    db: Session,
    *,
    provider: str,
    competition_code: str,
    season_year: int,
    kickoff_at: datetime,
    rows: list[tuple[int, int, int, int, int, int, int]],
) -> StandingsSnapshot:
    existing = _snapshot_at(
        db,
        provider=provider,
        competition_code=competition_code,
        season_year=season_year,
        kickoff_at=kickoff_at,
    )
    if existing is None:
        # Savepoint so a concurrent unique violation cannot abort the caller's txn
        # (e.g. fixture sync committing after baselines).
        try:
            with db.begin_nested():
                existing = StandingsSnapshot(
                    provider=provider,
                    competition_code=competition_code,
                    season_year=season_year,
                    kickoff_at=kickoff_at,
                    stale=False,
                    computed_at=datetime.now(UTC),
                )
                db.add(existing)
                db.flush()
        except IntegrityError:
            existing = _snapshot_at(
                db,
                provider=provider,
                competition_code=competition_code,
                season_year=season_year,
                kickoff_at=kickoff_at,
            )
            if existing is None:
                raise
            existing.stale = False
            existing.computed_at = datetime.now(UTC)
    else:
        existing.stale = False
        existing.computed_at = datetime.now(UTC)
    _replace_snapshot_rows(db, existing, rows)
    return existing


def _teams_for_competition_season(
    db: Session,
    *,
    provider: str,
    competition_code: str,
    season_year: int,
    fallback_external_ids: list[str] | None = None,
) -> list[Team]:
    """Teams linked to any fantasy pool for this shared competition season.

    When no pools exist yet (e.g. platform-admin global sync), fall back to
    ``fallback_external_ids`` from the just-synced squad list.
    """
    pool_ids = list(
        db.scalars(
            select(TeamPool.id).where(
                TeamPool.provider == provider,
                TeamPool.competition_code == competition_code,
                TeamPool.season_year == season_year,
            )
        ).all()
    )
    team_ids: list[int] = []
    if pool_ids:
        team_ids = list(
            db.scalars(
                select(PoolTeam.team_id).where(PoolTeam.pool_id.in_(pool_ids)).distinct()
            ).all()
        )
    if not team_ids and fallback_external_ids:
        return list(
            db.scalars(
                select(Team).where(
                    Team.provider == provider,
                    Team.external_id.in_(fallback_external_ids),
                )
            ).all()
        )
    if not team_ids:
        return []
    return list(db.scalars(select(Team).where(Team.id.in_(team_ids))).all())


def _map_standing_rows_to_local(
    db: Session,
    *,
    provider: str,
    standing_rows: list[ProviderStandingRow],
) -> list[tuple[int, int, int, int, int, int, int]]:
    mapped: list[tuple[int, int, int, int, int, int, int]] = []
    for row in standing_rows:
        team = db.scalars(
            select(Team).where(
                Team.provider == provider,
                Team.external_id == row.external_team_id,
            )
        ).first()
        if team is None:
            continue
        mapped.append(
            (
                team.id,
                row.position,
                row.played,
                row.points,
                row.goals_for,
                row.goals_against,
                row.goal_difference,
            )
        )
    return mapped


def ensure_competition_season_table_baselines(
    db: Session,
    provider: FootballProvider,
    *,
    provider_key: str,
    competition_code: str,
    season_year: int,
    fallback_external_ids: list[str] | None = None,
) -> dict[str, bool]:
    """Ensure shared previous-final + zeroed opener snapshots for competition season Y.

    Previous-final is fetched from standings API for ``season_year - 1`` and stored under
    ``season_year`` with kickoff = day after prior season end. Zeroed opener uses current
    season start. Snapshots are shared across leagues; previous-final is fetch-once.

    ``fallback_external_ids`` supplies current-season squad ids when no fantasy pools
    have linked teams yet (platform-admin global sync).
    """
    created_previous = False
    created_zeroed = False
    code = competition_code.upper()

    # Use the same previous-final detector draft autopick uses. A mid-season
    # kickoff snapshot with played > 0 must not count as a cached baseline.
    has_previous_final = (
        previous_final_snapshot_for_competition(
            db,
            provider=provider_key,
            competition_code=code,
            season_year=season_year,
        )
        is not None
    )
    if not has_previous_final:
        previous_year = int(season_year) - 1
        prev_info, rate = provider.resolve_competition_season(code, previous_year)
        respect_rate_limit(rate)
        if prev_info.end_date is not None:
            kickoff = _aware(prev_info.end_date) + timedelta(days=1)
        else:
            # Fallback: mid-summer after a typical European season.
            kickoff = datetime(previous_year + 1, 7, 1, tzinfo=UTC)
        try:
            standing_rows, rate = provider.list_standings(code, previous_year)
            respect_rate_limit(rate)
        except FootballDataError as exc:
            if exc.rate_limited:
                # Let callers wait/retry; do not treat as "no standings".
                raise
            logger.warning(
                "ensure_table_baselines previous standings failed competition=%s/%s err=%s",
                code,
                previous_year,
                exc,
            )
            standing_rows = []
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ensure_table_baselines previous standings failed competition=%s/%s err=%s",
                code,
                previous_year,
                exc,
            )
            standing_rows = []
        mapped = _map_standing_rows_to_local(
            db, provider=provider_key, standing_rows=standing_rows
        )
        if mapped:
            _upsert_snapshot_with_rows(
                db,
                provider=provider_key,
                competition_code=code,
                season_year=season_year,
                kickoff_at=kickoff,
                rows=mapped,
            )
            created_previous = True
            logger.info(
                "ensure_table_baselines previous-final competition=%s/%s rows=%s kickoff=%s",
                code,
                season_year,
                len(mapped),
                kickoff.isoformat(),
            )
        else:
            logger.info(
                "ensure_table_baselines no previous-final rows competition=%s/%s",
                code,
                season_year,
            )
    else:
        logger.debug(
            "ensure_table_baselines skip previous-final (cached) competition=%s/%s",
            code,
            season_year,
        )

    current_info, rate = provider.resolve_competition_season(code, int(season_year))
    respect_rate_limit(rate)
    if current_info.start_date is not None:
        zero_kickoff = _aware(current_info.start_date)
    else:
        oldest_now = oldest_snapshot_for_competition(
            db,
            provider=provider_key,
            competition_code=code,
            season_year=season_year,
        )
        if oldest_now is not None:
            zero_kickoff = _aware(oldest_now.kickoff_at) + timedelta(seconds=1)
        else:
            zero_kickoff = datetime(int(season_year), 8, 1, tzinfo=UTC)

    existing_zero = _snapshot_at(
        db,
        provider=provider_key,
        competition_code=code,
        season_year=season_year,
        kickoff_at=zero_kickoff,
    )
    if existing_zero is None:
        teams = _teams_for_competition_season(
            db,
            provider=provider_key,
            competition_code=code,
            season_year=season_year,
            fallback_external_ids=fallback_external_ids,
        )
        teams_sorted = sorted(teams, key=lambda t: (t.name or "").lower())
        zero_rows = [
            (t.id, index, 0, 0, 0, 0, 0)
            for index, t in enumerate(teams_sorted, start=1)
        ]
        if zero_rows:
            _upsert_snapshot_with_rows(
                db,
                provider=provider_key,
                competition_code=code,
                season_year=season_year,
                kickoff_at=zero_kickoff,
                rows=zero_rows,
            )
            created_zeroed = True
            logger.info(
                "ensure_table_baselines zeroed opener competition=%s/%s rows=%s kickoff=%s",
                code,
                season_year,
                len(zero_rows),
                zero_kickoff.isoformat(),
            )

    return {
        "created_previous_final": created_previous,
        "created_zeroed_opener": created_zeroed,
    }
