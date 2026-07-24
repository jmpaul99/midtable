"""Sync fixtures for scores_match_results=true pools only; score + cascade."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import League, Match, RankingList, ScoringEvent, SyncStatus, Team, TeamPool, TeamRanking
from app.providers.base import FootballProvider, RateLimitInfo
from app.services.match_adapters import match_to_input
from app.services.scoring import (
    RankedTeam,
    ResultPoints,
    UpsetRules,
    is_finished,
    plan_recompute_cascade,
    score_match_events,
)
from app.services.standings import build_snapshot_for_kickoff, mark_snapshots_stale_after

STALE_LOCK_MINUTES = 15
PROVIDER_KEY = "football-data.org"


def earliest_finished_seeds_per_pool(
    matches: list[Match],
    *,
    scoring_pool_ids: set[int],
) -> tuple[list[Match], list[Match]]:
    """Return (finished_in_scoring_pools, one_earliest_seed_per_pool)."""
    finished = [
        m
        for m in matches
        if m.pool_id in scoring_pool_ids and is_finished(match_to_input(m))
    ]
    by_pool: dict[int, list[Match]] = {}
    for m in finished:
        by_pool.setdefault(m.pool_id, []).append(m)
    seeds: list[Match] = []
    for pool_matches in by_pool.values():
        pool_matches.sort(key=lambda x: x.kickoff_at)
        seeds.append(pool_matches[0])
    return finished, seeds


def _ensure_sync_status(db: Session, league_id: int, provider: str) -> SyncStatus:
    status = db.scalars(
        select(SyncStatus)
        .where(
            SyncStatus.league_id == league_id,
            SyncStatus.provider == provider,
        )
        .with_for_update()
    ).first()
    if status is None:
        status = SyncStatus(league_id=league_id, provider=provider)
        db.add(status)
        db.flush()
        status = db.scalars(
            select(SyncStatus)
            .where(
                SyncStatus.league_id == league_id,
                SyncStatus.provider == provider,
            )
            .with_for_update()
        ).one()
    return status


def _team_by_external(db: Session, provider: str, external_id: str) -> Team | None:
    return db.scalars(
        select(Team).where(Team.provider == provider, Team.external_id == external_id)
    ).first()


def _lock_stale(status: SyncStatus) -> bool:
    if not status.in_progress:
        return False
    if status.in_progress_since is None:
        return True
    age = datetime.now(UTC) - status.in_progress_since
    return age > timedelta(minutes=STALE_LOCK_MINUTES)


def sync_league_fixtures(
    db: Session,
    league: League,
    provider: FootballProvider,
) -> dict[str, Any]:
    """Pull matches for scoring pools only; preserve scheduled_matchweek on postponements."""
    status = _ensure_sync_status(db, league.id, PROVIDER_KEY)
    if status.in_progress and not _lock_stale(status):
        return {
            "ok": False,
            "error": "sync already in progress",
            "status_code": 409,
        }

    status.in_progress = True
    status.in_progress_since = datetime.now(UTC)
    status.last_error = None
    db.flush()

    changed_matches: list[Match] = []
    created = 0
    updated = 0
    skipped_missing_teams = 0
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
                    skipped_missing_teams += 1
                    continue
                existing = db.scalars(
                    select(Match).where(
                        Match.league_id == league.id,
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
            "skipped_missing_teams": skipped_missing_teams,
            **score_summary,
        }
        status.in_progress = False
        status.in_progress_since = None
        db.commit()
        return {"ok": True, "status_code": 200, **status.last_summary}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        status = _ensure_sync_status(db, league.id, PROVIDER_KEY)
        status.in_progress = False
        status.in_progress_since = None
        status.last_error = str(exc)
        db.commit()
        return {"ok": False, "error": str(exc), "status_code": 502}


def score_changed_matches(
    db: Session,
    league: League,
    changed: list[Match],
) -> dict[str, Any]:
    if not changed:
        return {"scored": 0, "cascaded": 0, "skipped_missing_snapshot": 0}

    result_points = ResultPoints.from_config(league.result_points)
    upset_rules = UpsetRules.from_config(league.upset_rules)
    all_matches = list(db.scalars(select(Match).where(Match.league_id == league.id)).all())
    all_inputs = [match_to_input(m) for m in all_matches]
    by_id = {m.id: m for m in all_matches}
    fixed_ranks = _fixed_ranking_map(db, league, upset_rules)

    scored = 0
    cascaded = 0
    skipped_missing_snapshot = 0
    for match in changed:
        mi = match_to_input(match)
        if not is_finished(mi):
            for event in db.scalars(
                select(ScoringEvent).where(ScoringEvent.match_id == match.id)
            ).all():
                db.delete(event)
            # Still cascade: later tables/upsets depended on this result.
            plan = plan_recompute_cascade(mi, all_inputs)
            mark_snapshots_stale_after(db, plan.pool_id, plan.starts_at)
            cascaded += len(plan.affected_match_ids)
            pool = db.get(TeamPool, match.pool_id)
            assert pool is not None
            s, skip = _rescore_plan_matches(
                db,
                league=league,
                pool=pool,
                plan_match_ids=plan.affected_match_ids,
                by_id=by_id,
                result_points=result_points,
                upset_rules=upset_rules,
                fixed_ranks=fixed_ranks,
            )
            scored += s
            skipped_missing_snapshot += skip
            continue

        plan = plan_recompute_cascade(mi, all_inputs)
        mark_snapshots_stale_after(db, plan.pool_id, plan.starts_at)
        cascaded += len(plan.affected_match_ids)

        pool = db.get(TeamPool, match.pool_id)
        assert pool is not None
        s, skip = _rescore_plan_matches(
            db,
            league=league,
            pool=pool,
            plan_match_ids=plan.affected_match_ids,
            by_id=by_id,
            result_points=result_points,
            upset_rules=upset_rules,
            fixed_ranks=fixed_ranks,
        )
        scored += s
        skipped_missing_snapshot += skip
    db.flush()
    lock_ranking_lists_after_scoring(db, league)
    return {
        "scored": scored,
        "cascaded": cascaded,
        "skipped_missing_snapshot": skipped_missing_snapshot,
    }


def _fixed_ranking_map(
    db: Session,
    league: League,
    upset_rules: UpsetRules,
) -> dict[int, RankedTeam] | None:
    if upset_rules.rank_source != "fixed_ranking_at_event_start":
        return None
    key = upset_rules.ranking_list_key
    if not key:
        return None
    ranking_list = db.scalars(
        select(RankingList).where(
            RankingList.league_id == league.id,
            RankingList.key == key,
        )
    ).first()
    if ranking_list is None:
        return None
    rows = list(
        db.scalars(
            select(TeamRanking).where(TeamRanking.ranking_list_id == ranking_list.id)
        ).all()
    )
    # played high enough that min_played eligibility does not block tournament upsets
    played = max(upset_rules.min_played, 0)
    return {
        row.team_id: RankedTeam(
            team_id=row.team_id,
            rank=row.rank,
            played=played,
            points=Decimal(0),
            goals_for=0,
            goals_against=0,
            goal_difference=0,
        )
        for row in rows
    }


def _rescore_plan_matches(
    db: Session,
    *,
    league: League,
    pool: TeamPool,
    plan_match_ids: tuple[int, ...] | list[int],
    by_id: dict[int, Match],
    result_points: ResultPoints,
    upset_rules: UpsetRules,
    fixed_ranks: dict[int, RankedTeam] | None,
) -> tuple[int, int]:
    scored = 0
    skipped = 0
    kickoffs = sorted({by_id[mid].kickoff_at for mid in plan_match_ids if mid in by_id})
    for kickoff in kickoffs:
        if fixed_ranks is None:
            snap = build_snapshot_for_kickoff(
                db,
                pool=pool,
                kickoff_at=kickoff,
                result_points=result_points,
                mark_fresh=True,
            )
            snap_rows = {r.team_id: r for r in snap.rows}
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
        else:
            ranked = fixed_ranks
        for mid in plan_match_ids:
            m = by_id.get(mid)
            if m is None or m.kickoff_at != kickoff:
                continue
            minput = match_to_input(m)
            if not is_finished(minput):
                for event in db.scalars(
                    select(ScoringEvent).where(ScoringEvent.match_id == m.id)
                ).all():
                    db.delete(event)
                continue
            if m.home_team_id not in ranked or m.away_team_id not in ranked:
                skipped += 1
                continue
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
    return scored, skipped


def lock_ranking_lists_after_scoring(db: Session, league: League) -> int:
    """Lock ranking lists referenced by upset_rules once any scoring events exist."""
    key = (league.upset_rules or {}).get("ranking_list_key")
    if not key:
        return 0
    has_events = db.scalars(
        select(ScoringEvent.id).where(ScoringEvent.league_id == league.id).limit(1)
    ).first()
    if has_events is None:
        return 0
    lists = list(
        db.scalars(
            select(RankingList).where(
                RankingList.league_id == league.id,
                RankingList.key == key,
                RankingList.locked.is_(False),
            )
        ).all()
    )
    for row in lists:
        row.locked = True
    if lists:
        db.flush()
    return len(lists)
