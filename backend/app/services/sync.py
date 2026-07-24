"""Sync fixtures for scores_match_results=true pools only; score + cascade."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import League, Match, ScoringEvent, SyncStatus, Team, TeamPool
from app.providers.base import FootballProvider, RateLimitInfo
from app.providers.football_data import FootballDataProvider
from app.services.scoring import (
    MatchInput,
    ResultPoints,
    UpsetRules,
    is_finished,
    plan_recompute_cascade,
    score_match_events,
)
from app.services.standings import build_snapshot_for_kickoff, mark_snapshots_stale_after


def get_provider(token: str, base_url: str) -> FootballProvider:
    return FootballDataProvider(token, base_url=base_url)


def _ensure_sync_status(db: Session, league_id: int, provider: str) -> SyncStatus:
    status = db.scalars(
        select(SyncStatus).where(
            SyncStatus.league_id == league_id,
            SyncStatus.provider == provider,
        )
    ).first()
    if status is None:
        status = SyncStatus(league_id=league_id, provider=provider)
        db.add(status)
        db.flush()
    return status


def _team_by_external(db: Session, provider: str, external_id: str) -> Team | None:
    return db.scalars(
        select(Team).where(Team.provider == provider, Team.external_id == external_id)
    ).first()


def sync_league_fixtures(
    db: Session,
    league: League,
    provider: FootballProvider,
) -> dict[str, Any]:
    """Pull matches for scoring pools only; preserve scheduled_matchweek on postponements."""
    status = _ensure_sync_status(db, league.id, "football-data.org")
    if status.in_progress:
        return {"ok": False, "error": "sync already in progress"}

    status.in_progress = True
    status.in_progress_since = datetime.now(UTC)
    status.last_error = None
    db.flush()

    changed_matches: list[Match] = []
    created = 0
    updated = 0
    rate: RateLimitInfo | None = None

    try:
        scoring_pools = [
            p
            for p in db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all()
            if p.scores_match_results
        ]
        for pool in scoring_pools:
            if not pool.competition_code or not pool.season_year:
                continue
            matches, rate = provider.list_matches(pool.competition_code, pool.season_year)
            for pm in matches:
                home = _team_by_external(db, pool.provider, pm.home_external_id)
                away = _team_by_external(db, pool.provider, pm.away_external_id)
                if home is None or away is None:
                    continue
                existing = db.scalars(
                    select(Match).where(
                        Match.provider == pool.provider,
                        Match.external_id == pm.external_id,
                    )
                ).first()
                if existing is None:
                    row = Match(
                        league_id=league.id,
                        pool_id=pool.id,
                        provider=pool.provider,
                        external_id=pm.external_id,
                        home_team_id=home.id,
                        away_team_id=away.id,
                        kickoff_at=pm.kickoff_at,
                        status=pm.status,
                        home_goals=pm.home_goals,
                        away_goals=pm.away_goals,
                        scheduled_matchweek=pm.matchday,
                        stage=pm.stage,
                        last_synced_at=datetime.now(UTC),
                    )
                    db.add(row)
                    created += 1
                    if pm.status in {"FINISHED", "AWARDED"}:
                        changed_matches.append(row)
                else:
                    before = (
                        existing.status,
                        existing.home_goals,
                        existing.away_goals,
                        existing.kickoff_at,
                    )
                    # Preserve original scheduled_matchweek across postponements
                    if existing.scheduled_matchweek is None and pm.matchday is not None:
                        existing.scheduled_matchweek = pm.matchday
                    existing.kickoff_at = pm.kickoff_at
                    existing.status = pm.status
                    existing.home_goals = pm.home_goals
                    existing.away_goals = pm.away_goals
                    if pm.stage:
                        existing.stage = pm.stage
                    existing.last_synced_at = datetime.now(UTC)
                    after = (
                        existing.status,
                        existing.home_goals,
                        existing.away_goals,
                        existing.kickoff_at,
                    )
                    if before != after:
                        updated += 1
                        changed_matches.append(existing)

        db.flush()
        score_summary = score_changed_matches(db, league, changed_matches)

        status.last_sync_at = datetime.now(UTC)
        status.requests_available_minute = (
            rate.requests_available_minute if rate else status.requests_available_minute
        )
        status.last_summary = {
            "created": created,
            "updated": updated,
            "changed": len(changed_matches),
            **score_summary,
        }
        status.in_progress = False
        status.in_progress_since = None
        db.commit()
        return {"ok": True, **status.last_summary}
    except Exception as exc:  # noqa: BLE001
        status.in_progress = False
        status.in_progress_since = None
        status.last_error = str(exc)
        db.commit()
        return {"ok": False, "error": str(exc)}


def score_changed_matches(
    db: Session,
    league: League,
    changed: list[Match],
) -> dict[str, Any]:
    if not changed:
        return {"scored": 0, "cascaded": 0}

    result_points = ResultPoints.from_config(league.result_points)
    upset_rules = UpsetRules.from_config(league.upset_rules)
    all_matches = list(db.scalars(select(Match).where(Match.league_id == league.id)).all())
    all_inputs = [
        MatchInput(
            match_id=m.id,
            pool_id=m.pool_id,
            home_team_id=m.home_team_id,
            away_team_id=m.away_team_id,
            kickoff_at=m.kickoff_at,
            home_goals=m.home_goals or 0,
            away_goals=m.away_goals or 0,
            status=m.status,
            scheduled_matchweek=m.scheduled_matchweek,
            stage=m.stage,
        )
        for m in all_matches
    ]
    by_id = {m.id: m for m in all_matches}

    scored = 0
    cascaded = 0
    for match in changed:
        mi = MatchInput(
            match_id=match.id,
            pool_id=match.pool_id,
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
            kickoff_at=match.kickoff_at,
            home_goals=match.home_goals or 0,
            away_goals=match.away_goals or 0,
            status=match.status,
            scheduled_matchweek=match.scheduled_matchweek,
            stage=match.stage,
        )
        if not is_finished(mi):
            # Became unfinished — remove events
            for event in db.scalars(
                select(ScoringEvent).where(ScoringEvent.match_id == match.id)
            ).all():
                db.delete(event)
            continue

        plan = plan_recompute_cascade(mi, all_inputs)
        mark_snapshots_stale_after(db, plan.pool_id, plan.starts_at)
        cascaded += len(plan.affected_match_ids)

        pool = db.get(TeamPool, match.pool_id)
        assert pool is not None
        kickoffs = sorted(
            {
                by_id[mid].kickoff_at
                for mid in plan.affected_match_ids
                if mid in by_id
            }
        )
        for kickoff in kickoffs:
            snap = build_snapshot_for_kickoff(
                db,
                pool=pool,
                kickoff_at=kickoff,
                result_points=result_points,
                mark_fresh=True,
            )
            snap_rows = {r.team_id: r for r in snap.rows}
            # Convert ORM rows to RankedTeam-compatible via snapshot_map helper
            from app.services.scoring import RankedTeam

            ranked = {
                tid: RankedTeam(
                    team_id=tid,
                    rank=row.rank,
                    played=row.played,
                    points=row.points,
                    goals_for=row.goals_for,
                    goals_against=row.goals_against,
                    goal_difference=row.goal_difference,
                )
                for tid, row in snap_rows.items()
            }
            for mid in plan.affected_match_ids:
                m = by_id.get(mid)
                if m is None or m.kickoff_at != kickoff:
                    continue
                minput = MatchInput(
                    match_id=m.id,
                    pool_id=m.pool_id,
                    home_team_id=m.home_team_id,
                    away_team_id=m.away_team_id,
                    kickoff_at=m.kickoff_at,
                    home_goals=m.home_goals or 0,
                    away_goals=m.away_goals or 0,
                    status=m.status,
                    scheduled_matchweek=m.scheduled_matchweek,
                    stage=m.stage,
                )
                if not is_finished(minput):
                    continue
                # Idempotent upsert by (match_id, team_id, event_type)
                existing_events = {
                    (e.team_id, e.event_type): e
                    for e in db.scalars(
                        select(ScoringEvent).where(ScoringEvent.match_id == m.id)
                    ).all()
                }
                desired = score_match_events(
                    minput, ranked, result_points=result_points, upset_rules=upset_rules
                )
                desired_keys = {(e.team_id, e.event_type) for e in desired}
                for key, event in list(existing_events.items()):
                    if key not in desired_keys:
                        db.delete(event)
                for draft in desired:
                    key = (draft.team_id, draft.event_type)
                    if key in existing_events:
                        row = existing_events[key]
                        row.points = draft.points
                        row.scheduled_matchweek = draft.scheduled_matchweek
                        row.stage = draft.stage
                        row.metadata_ = draft.metadata
                    else:
                        db.add(
                            ScoringEvent(
                                league_id=league.id,
                                team_id=draft.team_id,
                                match_id=draft.match_id,
                                scheduled_matchweek=draft.scheduled_matchweek,
                                stage=draft.stage,
                                event_type=draft.event_type,
                                points=Decimal(draft.points),
                                metadata_=draft.metadata,
                            )
                        )
                scored += 1
    db.flush()
    return {"scored": scored, "cascaded": cascaded}
