"""Sync shared competition fixtures; score per fantasy league."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging_config import log_id
from app.models import League, Match, ScoringEvent, SyncStatus, Team, TeamPool
from app.providers.base import FootballProvider, RateLimitInfo
from app.services.match_adapters import match_to_input
from app.services.match_queries import (
    CompetitionKey,
    competition_keys_from_pools,
    matches_for_league,
    pool_for_match,
    scoring_pools_for_league,
)
from app.services.ranking_catalog import (
    ensure_fixed_ranking_for_league,
    ranks_for_league,
)
from app.services.scoring import (
    RankedTeam,
    ResultPoints,
    UpsetRules,
    is_finished,
    plan_recompute_cascade,
    score_match_events,
)
from app.services.standings import build_snapshot_for_kickoff, mark_snapshots_stale_after

logger = logging.getLogger(__name__)

STALE_LOCK_MINUTES = 15
PROVIDER_KEY = "football-data.org"


def earliest_finished_seeds_per_pool(
    matches: list[Match],
    *,
    pool_by_match_id: dict[int, int],
    scoring_pool_ids: set[int],
) -> tuple[list[Match], list[Match]]:
    """Return (finished_in_scoring_pools, one_earliest_seed_per_pool)."""
    finished: list[Match] = []
    for m in matches:
        pool_id = pool_by_match_id.get(m.id)
        if pool_id is None or pool_id not in scoring_pool_ids:
            continue
        if is_finished(match_to_input(m, pool_id=pool_id)):
            finished.append(m)
    by_pool: dict[int, list[Match]] = {}
    for m in finished:
        by_pool.setdefault(pool_by_match_id[m.id], []).append(m)
    seeds: list[Match] = []
    for pool_matches in by_pool.values():
        pool_matches.sort(key=lambda x: x.kickoff_at)
        seeds.append(pool_matches[0])
    return finished, seeds


def _ensure_sync_status(
    db: Session,
    *,
    provider: str,
    competition_code: str,
    season_year: int,
) -> SyncStatus:
    status = db.scalars(
        select(SyncStatus)
        .where(
            SyncStatus.provider == provider,
            SyncStatus.competition_code == competition_code,
            SyncStatus.season_year == season_year,
        )
        .with_for_update()
    ).first()
    if status is None:
        status = SyncStatus(
            provider=provider,
            competition_code=competition_code,
            season_year=season_year,
        )
        db.add(status)
        db.flush()
        status = db.scalars(
            select(SyncStatus)
            .where(
                SyncStatus.provider == provider,
                SyncStatus.competition_code == competition_code,
                SyncStatus.season_year == season_year,
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


def sync_competition_fixtures(
    db: Session,
    provider: FootballProvider,
    *,
    provider_key: str,
    competition_code: str,
    season_year: int,
) -> dict[str, Any]:
    """Pull and upsert shared Match rows for one competition season."""
    status = _ensure_sync_status(
        db,
        provider=provider_key,
        competition_code=competition_code,
        season_year=season_year,
    )
    if status.in_progress and not _lock_stale(status):
        logger.warning(
            "sync_competition soft-fail competition=%s/%s reason=in_progress",
            competition_code,
            season_year,
        )
        return {
            "ok": False,
            "error": "sync already in progress",
            "status_code": 409,
            "competition_code": competition_code,
            "season_year": season_year,
        }
    if status.in_progress and _lock_stale(status):
        logger.warning(
            "sync_competition taking over stale lock competition=%s/%s in_progress_since=%s",
            competition_code,
            season_year,
            status.in_progress_since,
        )

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
        matches, rate = provider.list_matches(competition_code, season_year)
        for pm in matches:
            home = _team_by_external(db, provider_key, pm.home_external_id)
            away = _team_by_external(db, provider_key, pm.away_external_id)
            if home is None or away is None:
                skipped_missing_teams += 1
                continue
            existing = db.scalars(
                select(Match).where(
                    Match.provider == provider_key,
                    Match.competition_code == competition_code,
                    Match.season_year == season_year,
                    Match.external_id == pm.external_id,
                )
            ).first()
            if existing is None:
                row = Match(
                    provider=provider_key,
                    competition_code=competition_code,
                    season_year=season_year,
                    external_id=pm.external_id,
                    home_team_id=home.id,
                    away_team_id=away.id,
                    kickoff_at=pm.kickoff_at,
                    status=pm.status,
                    home_goals=pm.home_goals,
                    away_goals=pm.away_goals,
                    duration=pm.duration or "REGULAR",
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
                    existing.duration,
                    existing.kickoff_at,
                )
                if existing.scheduled_matchweek is None and pm.matchday is not None:
                    existing.scheduled_matchweek = pm.matchday
                existing.kickoff_at = pm.kickoff_at
                existing.status = pm.status
                existing.home_goals = pm.home_goals
                existing.away_goals = pm.away_goals
                existing.duration = pm.duration or "REGULAR"
                if pm.stage:
                    existing.stage = pm.stage
                existing.last_synced_at = datetime.now(UTC)
                after = (
                    existing.status,
                    existing.home_goals,
                    existing.away_goals,
                    existing.duration,
                    existing.kickoff_at,
                )
                if before != after:
                    updated += 1
                    changed_matches.append(existing)

        db.flush()
        status.last_sync_at = datetime.now(UTC)
        status.requests_available_minute = (
            rate.requests_available_minute if rate else status.requests_available_minute
        )
        status.last_summary = {
            "created": created,
            "updated": updated,
            "changed": len(changed_matches),
            "skipped_missing_teams": skipped_missing_teams,
        }
        status.in_progress = False
        status.in_progress_since = None
        db.flush()
        logger.info(
            "sync_competition ok competition=%s/%s created=%s updated=%s changed=%s "
            "skipped_missing_teams=%s",
            competition_code,
            season_year,
            created,
            updated,
            len(changed_matches),
            skipped_missing_teams,
        )
        return {
            "ok": True,
            "status_code": 200,
            "competition_code": competition_code,
            "season_year": season_year,
            "changed_matches": changed_matches,
            **status.last_summary,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "sync_competition failed competition=%s/%s",
            competition_code,
            season_year,
        )
        db.rollback()
        status = _ensure_sync_status(
            db,
            provider=provider_key,
            competition_code=competition_code,
            season_year=season_year,
        )
        status.in_progress = False
        status.in_progress_since = None
        status.last_error = str(exc)
        db.commit()
        return {
            "ok": False,
            "error": str(exc),
            "status_code": 502,
            "competition_code": competition_code,
            "season_year": season_year,
        }


def sync_league_fixtures(
    db: Session,
    league: League,
    provider: FootballProvider,
) -> dict[str, Any]:
    """Sync competitions for this league's scoring pools, then score the league."""
    all_pools = list(
        db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all()
    )
    if not all_pools:
        logger.warning(
            "sync_league_fixtures soft-fail league_id=%s reason=no_pools",
            log_id(league),
        )
        return {
            "ok": False,
            "error": (
                "No competitions configured. "
                "Add competitions in League settings → Competitions."
            ),
            "status_code": 400,
        }

    scoring_pools = [p for p in all_pools if p.scores_match_results]
    keys = competition_keys_from_pools(scoring_pools)
    skipped_pools_missing_code = sum(
        1
        for p in scoring_pools
        if not p.competition_code or not p.season_year
    )

    created = 0
    updated = 0
    skipped_missing_teams = 0
    changed_matches: list[Match] = []
    seen_changed: set[int] = set()

    for provider_key, competition_code, season_year in keys:
        result = sync_competition_fixtures(
            db,
            provider,
            provider_key=provider_key,
            competition_code=competition_code,
            season_year=season_year,
        )
        if not result.get("ok"):
            return result
        # Persist each competition independently so a later failure cannot roll it back.
        db.commit()
        created += int(result.get("created") or 0)
        updated += int(result.get("updated") or 0)
        skipped_missing_teams += int(result.get("skipped_missing_teams") or 0)
        for m in result.get("changed_matches") or []:
            if m.id not in seen_changed:
                seen_changed.add(m.id)
                changed_matches.append(m)

    score_summary = score_changed_matches(db, league, changed_matches)
    db.commit()
    logger.info(
        "sync_league_fixtures ok league_id=%s created=%s updated=%s changed=%s "
        "scored=%s skipped_missing_teams=%s skipped_pools=%s",
        log_id(league),
        created,
        updated,
        len(changed_matches),
        score_summary.get("scored", 0),
        skipped_missing_teams,
        skipped_pools_missing_code,
    )
    return {
        "ok": True,
        "status_code": 200,
        "created": created,
        "updated": updated,
        "changed": len(changed_matches),
        "skipped_missing_teams": skipped_missing_teams,
        "skipped_pools_missing_code": skipped_pools_missing_code,
        **score_summary,
    }


def sync_all_active_competitions_then_score(
    db: Session,
    provider: FootballProvider,
    leagues: list[League],
) -> dict[str, Any]:
    """Cron helper: sync each competition once, then score every league."""
    key_to_leagues: dict[CompetitionKey, list[League]] = {}
    for league in leagues:
        pools = scoring_pools_for_league(db, league)
        for key in competition_keys_from_pools(pools):
            key_to_leagues.setdefault(key, []).append(league)

    competition_results: list[dict[str, Any]] = []
    changed_by_key: dict[CompetitionKey, list[Match]] = {}
    failures = 0

    for key, _league_list in key_to_leagues.items():
        provider_key, competition_code, season_year = key
        result = sync_competition_fixtures(
            db,
            provider,
            provider_key=provider_key,
            competition_code=competition_code,
            season_year=season_year,
        )
        # Drop Match objects before serializing response; keep ids for scoring.
        changed = list(result.pop("changed_matches", []) or [])
        if result.get("ok"):
            db.commit()
            changed_by_key[key] = changed
        else:
            failures += 1
        competition_results.append(result)

    league_results: list[dict[str, Any]] = []
    for league in leagues:
        pools = scoring_pools_for_league(db, league)
        league_keys = set(competition_keys_from_pools(pools))
        changed: list[Match] = []
        seen: set[int] = set()
        for key in league_keys:
            for m in changed_by_key.get(key, []):
                if m.id not in seen:
                    seen.add(m.id)
                    changed.append(m)
        try:
            score_summary = score_changed_matches(db, league, changed)
            db.commit()
            league_results.append(
                {
                    "league_id": str(league.public_id),
                    "result": {"ok": True, **score_summary},
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("score_league failed league_id=%s", log_id(league))
            db.rollback()
            failures += 1
            league_results.append(
                {
                    "league_id": str(league.public_id),
                    "result": {"ok": False, "error": str(exc)},
                }
            )

    return {
        "ok": failures == 0,
        "failures": failures,
        "competitions": competition_results,
        "leagues": league_results,
    }


def score_changed_matches(
    db: Session,
    league: League,
    changed: list[Match],
) -> dict[str, Any]:
    started = time.perf_counter()
    ensure_fixed_ranking_for_league(db, league)
    db.flush()
    if not changed:
        logger.info(
            "score_changed_matches empty league_id=%s seeds=0",
            log_id(league),
        )
        return {"scored": 0, "cascaded": 0, "skipped_missing_snapshot": 0}

    logger.info(
        "score_changed_matches start league_id=%s seeds=%s",
        log_id(league),
        len(changed),
    )
    result_points = ResultPoints.from_config(league.result_points)
    upset_rules = UpsetRules.from_config(league.upset_rules)
    all_matches = matches_for_league(db, league)
    pool_by_match: dict[int, TeamPool] = {}
    all_inputs = []
    for m in all_matches:
        pool = pool_for_match(db, league, m)
        if pool is None:
            continue
        pool_by_match[m.id] = pool
        all_inputs.append(match_to_input(m, pool_id=pool.id))
    by_id = {m.id: m for m in all_matches}
    fixed_ranks = ranks_for_league(db, league, upset_rules)

    scored = 0
    cascaded = 0
    skipped_missing_snapshot = 0
    skipped_match_ids: list[int] = []
    for match in changed:
        pool = pool_by_match.get(match.id) or pool_for_match(db, league, match)
        if pool is None:
            continue
        mi = match_to_input(match, pool_id=pool.id)
        finished = is_finished(mi)
        if not finished:
            for event in db.scalars(
                select(ScoringEvent).where(
                    ScoringEvent.match_id == match.id,
                    ScoringEvent.league_id == league.id,
                )
            ).all():
                db.delete(event)
            plan = plan_recompute_cascade(mi, all_inputs)
            mark_snapshots_stale_after(
                db,
                provider=match.provider,
                competition_code=match.competition_code,
                season_year=match.season_year,
                kickoff_at=plan.starts_at,
            )
            cascaded += len(plan.affected_match_ids)
            logger.info(
                "score seed league_id=%s match_id=%s pool_id=%s path=unfinished_wipe "
                "cascade_affected=%s starts_at=%s",
                log_id(league),
                match.id,
                pool.id,
                len(plan.affected_match_ids),
                plan.starts_at.isoformat(),
            )
            s, skip, skip_ids = _rescore_plan_matches(
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
            skipped_match_ids.extend(skip_ids)
            continue

        plan = plan_recompute_cascade(mi, all_inputs)
        mark_snapshots_stale_after(
            db,
            provider=match.provider,
            competition_code=match.competition_code,
            season_year=match.season_year,
            kickoff_at=plan.starts_at,
        )
        cascaded += len(plan.affected_match_ids)
        logger.info(
            "score seed league_id=%s match_id=%s pool_id=%s path=finished "
            "cascade_affected=%s starts_at=%s",
            log_id(league),
            match.id,
            pool.id,
            len(plan.affected_match_ids),
            plan.starts_at.isoformat(),
        )

        s, skip, skip_ids = _rescore_plan_matches(
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
        skipped_match_ids.extend(skip_ids)
    db.flush()
    lock_ranking_lists_after_scoring(db, league)
    duration_ms = (time.perf_counter() - started) * 1000
    if skipped_missing_snapshot > 0:
        sample = skipped_match_ids[:10]
        logger.warning(
            "score_changed_matches skipped_missing_snapshot league_id=%s count=%s "
            "match_ids_sample=%s",
            log_id(league),
            skipped_missing_snapshot,
            sample,
        )
    logger.info(
        "score_changed_matches done league_id=%s scored=%s cascaded=%s "
        "skipped_missing_snapshot=%s duration_ms=%.1f",
        log_id(league),
        scored,
        cascaded,
        skipped_missing_snapshot,
        duration_ms,
    )
    return {
        "scored": scored,
        "cascaded": cascaded,
        "skipped_missing_snapshot": skipped_missing_snapshot,
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
) -> tuple[int, int, list[int]]:
    scored = 0
    skipped = 0
    skipped_ids: list[int] = []
    events_upserted = 0
    events_deleted = 0
    rank_source = "fixed_ranking" if fixed_ranks is not None else "snapshot"
    kickoffs = sorted({by_id[mid].kickoff_at for mid in plan_match_ids if mid in by_id})
    for kickoff in kickoffs:
        batch_count = sum(
            1 for mid in plan_match_ids if mid in by_id and by_id[mid].kickoff_at == kickoff
        )
        logger.debug(
            "rescore kickoff batch league_id=%s pool_id=%s kickoff=%s matches=%s source=%s",
            log_id(league),
            pool.id,
            kickoff.isoformat(),
            batch_count,
            rank_source,
        )
        if fixed_ranks is None:
            if not pool.competition_code or not pool.season_year:
                continue
            snap = build_snapshot_for_kickoff(
                db,
                provider=pool.provider,
                competition_code=pool.competition_code,
                season_year=pool.season_year,
                kickoff_at=kickoff,
                pool_id=pool.id,
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
            minput = match_to_input(m, pool_id=pool.id)
            if not is_finished(minput):
                for event in db.scalars(
                    select(ScoringEvent).where(
                        ScoringEvent.match_id == m.id,
                        ScoringEvent.league_id == league.id,
                    )
                ).all():
                    db.delete(event)
                    events_deleted += 1
                continue
            if m.home_team_id not in ranked or m.away_team_id not in ranked:
                skipped += 1
                skipped_ids.append(m.id)
                logger.warning(
                    "rescore skip missing rank league_id=%s match_id=%s "
                    "home_team_id=%s away_team_id=%s",
                    log_id(league),
                    m.id,
                    m.home_team_id,
                    m.away_team_id,
                )
                continue
            existing_events = {
                (e.team_id, e.event_type): e
                for e in db.scalars(
                    select(ScoringEvent).where(
                        ScoringEvent.match_id == m.id,
                        ScoringEvent.league_id == league.id,
                    )
                ).all()
            }
            desired = score_match_events(
                minput, ranked, result_points=result_points, upset_rules=upset_rules
            )
            desired_keys = {(e.team_id, e.event_type) for e in desired}
            for key, event in list(existing_events.items()):
                if key not in desired_keys:
                    db.delete(event)
                    events_deleted += 1
            for draft in desired:
                key = (draft.team_id, draft.event_type)
                if key in existing_events:
                    row = existing_events[key]
                    row.points = draft.points
                    row.scheduled_matchweek = draft.scheduled_matchweek
                    row.stage = draft.stage
                    row.metadata_ = draft.metadata
                    events_upserted += 1
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
                    events_upserted += 1
            scored += 1
    logger.info(
        "rescore plan done league_id=%s pool_id=%s scored=%s skipped=%s "
        "events_upserted=%s events_deleted=%s",
        log_id(league),
        pool.id,
        scored,
        skipped,
        events_upserted,
        events_deleted,
    )
    return scored, skipped, skipped_ids


def lock_ranking_lists_after_scoring(db: Session, league: League) -> int:
    """Lock ranking lists referenced by upset_rules once any scoring events exist."""
    from app.services.ranking_catalog import freeze_catalog_for_league_lock

    key = (league.upset_rules or {}).get("ranking_list_key")
    if not key:
        return 0
    has_events = db.scalars(
        select(ScoringEvent.id).where(ScoringEvent.league_id == league.id).limit(1)
    ).first()
    if has_events is None:
        return 0
    return freeze_catalog_for_league_lock(db, league, key)
