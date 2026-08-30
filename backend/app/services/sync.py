"""Sync shared competition fixtures; score per fantasy league."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.logging_config import log_id
from app.models import League, Match, ScoringEvent, SyncStatus, Team, TeamPool
from app.providers.base import FootballProvider, RateLimitInfo
from app.services.league_jobs import record_cron_league_result
from app.services.match_adapters import match_to_input
from app.services.match_queries import (
    FINISHED_STATUSES,
    CompetitionKey,
    competition_keys_from_pools,
    matches_for_league,
    pool_for_match,
    pool_lookup_for_league,
    scoring_pools_for_league,
)
from app.services.ranking_catalog import (
    ensure_fixed_ranking_for_league,
    ranks_for_league,
)
from app.services.scoring import (
    RankedTeam,
    ResultPoints,
    ScoringEventDraft,
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


def merge_scoring_seeds(*groups: Sequence[Match]) -> list[Match]:
    """Dedupe match seeds by id, preserving first-seen order."""
    out: list[Match] = []
    seen: set[int] = set()
    for group in groups:
        for match in group:
            match_id = match.id
            if match_id is None or match_id in seen:
                continue
            seen.add(match_id)
            out.append(match)
    return out


def unscored_finished_matches(db: Session, league: League) -> list[Match]:
    """Finished scoring-pool matches with no ScoringEvent rows for this league."""
    matches = matches_for_league(db, league)
    if not matches:
        return []
    pool_lookup = pool_lookup_for_league(db, league)
    finished: list[Match] = []
    for match in matches:
        pool = pool_for_match(db, league, match, lookup=pool_lookup)
        if pool is None:
            continue
        if is_finished(match_to_input(match, pool_id=pool.id)):
            finished.append(match)
    if not finished:
        return []
    scored_ids = set(
        db.scalars(
            select(ScoringEvent.match_id).where(
                ScoringEvent.league_id == league.id,
                ScoringEvent.match_id.in_([m.id for m in finished]),
            )
        ).all()
    )
    return [m for m in finished if m.id not in scored_ids]


def gap_fill_seeds_for_league(
    db: Session,
    league: League,
    *,
    all_unscored: bool = False,
) -> list[Match]:
    """Gap-fill seeds for finished matches still missing ScoringEvents.

    Default: earliest unscored finished match per scoring pool (cascade covers
    later kickoffs). When ``all_unscored`` is true, return every unscored
    finished match — used after an earliest seed fails to write events so later
    fixtures are not blocked on subsequent attempts in the same cron.
    """
    gaps = unscored_finished_matches(db, league)
    if not gaps:
        return []
    pool_lookup = pool_lookup_for_league(db, league)
    pool_by_match_id: dict[int, int] = {}
    scoring_pool_ids: set[int] = set()
    eligible: list[Match] = []
    for match in gaps:
        pool = pool_for_match(db, league, match, lookup=pool_lookup)
        if pool is None:
            continue
        pool_by_match_id[match.id] = pool.id
        scoring_pool_ids.add(pool.id)
        eligible.append(match)
    if all_unscored:
        eligible.sort(key=lambda m: (m.kickoff_at, m.id or 0))
        return eligible
    _, seeds = earliest_finished_seeds_per_pool(
        eligible,
        pool_by_match_id=pool_by_match_id,
        scoring_pool_ids=scoring_pool_ids,
    )
    return seeds


def score_league_after_sync(
    db: Session,
    league: League,
    changed: Sequence[Match],
) -> dict[str, Any]:
    """Score provider-changed matches plus gap-fill seeds for missing events."""
    gap_seeds = gap_fill_seeds_for_league(db, league)
    seeds = merge_scoring_seeds(changed, gap_seeds)
    summary = score_changed_matches(db, league, seeds)
    # If an earliest gap-fill seed stays unscoreable (missing ranks / zero-point
    # with no event row), cascade alone may not have run for later fixtures on
    # a prior cron that only had that stuck seed. Re-seed every remaining gap.
    tried_ids = {m.id for m in seeds if m.id is not None}
    still_stuck = [
        m
        for m in gap_fill_seeds_for_league(db, league)
        if m.id in tried_ids
    ]
    extra_seeds: list[Match] = []
    if still_stuck:
        remaining = [
            m
            for m in gap_fill_seeds_for_league(db, league, all_unscored=True)
            if m.id not in tried_ids
        ]
        if remaining:
            extra_seeds = remaining
            extra = score_changed_matches(db, league, extra_seeds)
            summary = {
                "scored": int(summary.get("scored") or 0) + int(extra.get("scored") or 0),
                "cascaded": int(summary.get("cascaded") or 0)
                + int(extra.get("cascaded") or 0),
                "skipped_missing_snapshot": int(summary.get("skipped_missing_snapshot") or 0)
                + int(extra.get("skipped_missing_snapshot") or 0),
            }
            logger.warning(
                "gap_fill unblocked later matches league_id=%s stuck_seeds=%s "
                "extra_seeds=%s extra_scored=%s",
                log_id(league),
                [m.id for m in still_stuck],
                len(extra_seeds),
                extra.get("scored"),
            )
    return {
        **summary,
        "gap_fill_seeds": len(gap_seeds) + len(extra_seeds),
        "seed_count": len(seeds) + len(extra_seeds),
    }


def leagues_sharing_competition_keys(
    db: Session,
    keys: Sequence[CompetitionKey],
    *,
    statuses: Sequence[str] = ("active", "drafting"),
    always_include: League | None = None,
) -> list[League]:
    """Active/drafting leagues that score any of the given competitions."""
    leagues: list[League] = []
    if keys:
        key_preds = [
            and_(
                TeamPool.provider == provider,
                TeamPool.competition_code == competition_code,
                TeamPool.season_year == season_year,
            )
            for provider, competition_code, season_year in keys
        ]
        leagues = list(
            db.scalars(
                select(League)
                .join(TeamPool, TeamPool.league_id == League.id)
                .where(
                    League.status.in_(tuple(statuses)),
                    TeamPool.scores_match_results.is_(True),
                    or_(*key_preds),
                )
                .distinct()
                .order_by(League.id)
            ).all()
        )
    if always_include is None:
        return leagues
    others = [league for league in leagues if league.id != always_include.id]
    return [always_include, *others]


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
        # Concurrent cron + commissioner can race on the unique
        # (provider, competition_code, season_year). Insert under a savepoint so
        # a unique violation cannot abort the caller's outer transaction
        # (PendingRollbackError → opaque HTTP 500 from /internal/sync-and-score).
        try:
            with db.begin_nested():
                status = SyncStatus(
                    provider=provider,
                    competition_code=competition_code,
                    season_year=season_year,
                )
                db.add(status)
                db.flush()
        except IntegrityError:
            status = None
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
    try:
        status = _ensure_sync_status(
            db,
            provider=provider_key,
            competition_code=competition_code,
            season_year=season_year,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "sync_competition lock lookup failed competition=%s/%s",
            competition_code,
            season_year,
        )
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.exception(
                "sync_competition rollback after lock lookup failed competition=%s/%s",
                competition_code,
                season_year,
            )
        return {
            "ok": False,
            "error": f"sync lock lookup failed: {exc}",
            "status_code": 500,
            "competition_code": competition_code,
            "season_year": season_year,
        }
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
    # Commit so other requests see the lock (cron + commissioner across processes).
    try:
        db.commit()
        db.refresh(status)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "sync_competition failed to acquire lock competition=%s/%s",
            competition_code,
            season_year,
        )
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.exception(
                "sync_competition rollback after lock acquire failed competition=%s/%s",
                competition_code,
                season_year,
            )
        return {
            "ok": False,
            "error": f"sync lock acquire failed: {exc}",
            "status_code": 500,
            "competition_code": competition_code,
            "season_year": season_year,
        }

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
                if pm.status in FINISHED_STATUSES:
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
                # Thin competition-list rows can report TIMED/SCHEDULED with
                # null goals after the match is already FINISHED in DB (or after
                # a prior detail enrich). Never downgrade terminal status or wipe
                # known scores with that thin payload.
                existing_finished = existing.status in FINISHED_STATUSES
                provider_finished = pm.status in FINISHED_STATUSES
                thin_null_goals = pm.home_goals is None and pm.away_goals is None
                downgrade_via_thin_list = (
                    existing_finished and not provider_finished and thin_null_goals
                )
                if not downgrade_via_thin_list:
                    existing.status = pm.status
                wiping_finished_goals = (
                    provider_finished
                    and thin_null_goals
                    and existing.home_goals is not None
                    and existing.away_goals is not None
                )
                if not wiping_finished_goals and not downgrade_via_thin_list:
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
        # Baselines are best-effort. Use a savepoint so a DB error (e.g. concurrent
        # standings_snapshots unique violation vs commissioner sync) cannot abort the
        # outer transaction — that used to poison the session and make the caller's
        # db.commit() raise PendingRollbackError → HTTP 500 from /internal/sync-and-score.
        try:
            from app.services.standings import ensure_competition_season_table_baselines

            with db.begin_nested():
                ensure_competition_season_table_baselines(
                    db,
                    provider,
                    provider_key=provider_key,
                    competition_code=competition_code,
                    season_year=season_year,
                )
                db.flush()
        except Exception:  # noqa: BLE001
            logger.warning(
                "sync_competition table baselines failed competition=%s/%s",
                competition_code,
                season_year,
                exc_info=True,
            )
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
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.exception(
                "sync_competition rollback failed competition=%s/%s",
                competition_code,
                season_year,
            )
        try:
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
        except Exception:  # noqa: BLE001
            logger.exception(
                "sync_competition failed to clear lock competition=%s/%s",
                competition_code,
                season_year,
            )
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "sync_competition rollback after lock clear failed competition=%s/%s",
                    competition_code,
                    season_year,
                )
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
    """Sync competitions for this league's scoring pools, then score affected leagues.

    Scoring covers:
    - Matches changed in this pull
    - Gap-fill: finished matches still missing ScoringEvents for a league
    - Every active/drafting league that shares a synced competition (fixtures are shared)
    """
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
    competition_failures: list[dict[str, Any]] = []

    for provider_key, competition_code, season_year in keys:
        try:
            resolved = provider.resolve_competition_season(competition_code, season_year)
        except Exception:  # noqa: BLE001
            logger.warning(
                "sync_league_fixtures could not resolve competition type "
                "competition=%s/%s",
                competition_code,
                season_year,
                exc_info=True,
            )
            resolved = None
        if isinstance(resolved, tuple) and resolved:
            info = resolved[0]
            ctype = getattr(info, "competition_type", None)
            if ctype:
                for pool in all_pools:
                    if (
                        (pool.provider or "football-data.org") == provider_key
                        and (pool.competition_code or "").upper()
                        == competition_code.upper()
                        and int(pool.season_year or 0) == int(season_year)
                    ):
                        pool.competition_type = ctype
        result = sync_competition_fixtures(
            db,
            provider,
            provider_key=provider_key,
            competition_code=competition_code,
            season_year=season_year,
        )
        if not result.get("ok"):
            competition_failures.append(result)
            continue
        # Persist each competition independently so a later failure cannot roll it back.
        db.commit()
        created += int(result.get("created") or 0)
        updated += int(result.get("updated") or 0)
        skipped_missing_teams += int(result.get("skipped_missing_teams") or 0)
        for m in result.get("changed_matches") or []:
            if m.id not in seen_changed:
                seen_changed.add(m.id)
                changed_matches.append(m)

    affected_leagues = leagues_sharing_competition_keys(
        db, keys, always_include=league
    )
    primary_summary: dict[str, Any] = {
        "scored": 0,
        "cascaded": 0,
        "skipped_missing_snapshot": 0,
        "gap_fill_seeds": 0,
        "seed_count": 0,
    }
    sibling_results: list[dict[str, Any]] = []
    score_failures = 0
    for target in affected_leagues:
        try:
            score_summary = score_league_after_sync(db, target, changed_matches)
            if target.id == league.id:
                primary_summary = score_summary
            else:
                sibling_results.append(
                    {
                        "league_id": str(target.public_id),
                        "ok": True,
                        **{
                            k: score_summary[k]
                            for k in (
                                "scored",
                                "cascaded",
                                "skipped_missing_snapshot",
                                "gap_fill_seeds",
                                "seed_count",
                            )
                            if k in score_summary
                        },
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "sync_league_fixtures score failed league_id=%s initiator=%s",
                log_id(target),
                log_id(league),
            )
            score_failures += 1
            if target.id == league.id:
                raise
            sibling_results.append(
                {
                    "league_id": str(target.public_id),
                    "ok": False,
                    "error": str(exc),
                }
            )

    from app.services.draft_schedule import clear_draft_schedule_if_after_first_kickoff

    cleared_schedule = clear_draft_schedule_if_after_first_kickoff(db, league)
    db.commit()

    if competition_failures and created == 0 and updated == 0 and not changed_matches:
        # Nothing synced; surface the first competition error (e.g. lock conflict).
        first = competition_failures[0]
        logger.warning(
            "sync_league_fixtures soft-fail league_id=%s reason=competition_errors "
            "failures=%s scored_anyway=%s",
            log_id(league),
            len(competition_failures),
            primary_summary.get("scored", 0),
        )
        return {
            "ok": False,
            "error": str(first.get("error") or "Sync failed"),
            "status_code": int(first.get("status_code") or 502),
            "competition_failures": len(competition_failures),
            "sibling_leagues_scored": sum(1 for r in sibling_results if r.get("ok")),
            "sibling_results": sibling_results,
            **primary_summary,
        }

    ok = not competition_failures and score_failures == 0
    logger.info(
        "sync_league_fixtures ok=%s league_id=%s created=%s updated=%s changed=%s "
        "scored=%s gap_fill_seeds=%s siblings=%s skipped_missing_teams=%s "
        "skipped_pools=%s cleared_draft_schedule=%s competition_failures=%s",
        ok,
        log_id(league),
        created,
        updated,
        len(changed_matches),
        primary_summary.get("scored", 0),
        primary_summary.get("gap_fill_seeds", 0),
        len(sibling_results),
        skipped_missing_teams,
        skipped_pools_missing_code,
        cleared_schedule,
        len(competition_failures),
    )
    payload: dict[str, Any] = {
        "ok": ok,
        "status_code": 200 if ok else 502,
        "created": created,
        "updated": updated,
        "changed": len(changed_matches),
        "skipped_missing_teams": skipped_missing_teams,
        "skipped_pools_missing_code": skipped_pools_missing_code,
        "sibling_leagues_scored": sum(1 for r in sibling_results if r.get("ok")),
        "sibling_results": sibling_results,
        "competition_failures": len(competition_failures),
        **primary_summary,
    }
    if competition_failures:
        payload["error"] = str(
            competition_failures[0].get("error") or "One or more competitions failed"
        )
    return payload


def sync_all_active_competitions_then_score(
    db: Session,
    provider: FootballProvider,
    leagues: list[League],
) -> dict[str, Any]:
    """Cron helper: sync each competition once, then score every league with gap-fill.

    Never raises on soft or unexpected failures — returns ``failures`` so the
    /internal/sync-and-score handler can emit HTTP 502 with a structured body
    instead of an opaque FastAPI 500.
    """
    try:
        return _sync_all_active_competitions_then_score_body(db, provider, leagues)
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_all_active_competitions_then_score unhandled")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.exception("sync_all rollback after unhandled error failed")
        return {
            "ok": False,
            "failures": 1,
            "error": str(exc)[:500],
            "error_type": type(exc).__name__,
            "competitions": [],
            "leagues": [],
        }


def _sync_all_active_competitions_then_score_body(
    db: Session,
    provider: FootballProvider,
    leagues: list[League],
) -> dict[str, Any]:
    """Inner cron sync+score loop (raises only if something escapes per-item handlers)."""
    key_to_leagues: dict[CompetitionKey, list[League]] = {}
    for league in leagues:
        pools = scoring_pools_for_league(db, league)
        for key in competition_keys_from_pools(pools):
            key_to_leagues.setdefault(key, []).append(league)

    competition_results: list[dict[str, Any]] = []
    # Persist match ids (not ORM instances) so later scoring survives commit/rollback.
    changed_ids_by_key: dict[CompetitionKey, list[int]] = {}
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
            try:
                db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "sync_all commit failed after competition=%s/%s",
                    competition_code,
                    season_year,
                )
                db.rollback()
                # Lock may still be held from the in-progress commit at sync start.
                try:
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
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "sync_all failed to clear lock competition=%s/%s",
                        competition_code,
                        season_year,
                    )
                    db.rollback()
                failures += 1
                competition_results.append(
                    {
                        "ok": False,
                        "error": str(exc),
                        "status_code": 500,
                        "competition_code": competition_code,
                        "season_year": season_year,
                    }
                )
                continue
            changed_ids_by_key[key] = [
                mid for mid in (m.id for m in changed) if mid is not None
            ]
        else:
            failures += 1
        competition_results.append(result)

    league_results: list[dict[str, Any]] = []
    for league in leagues:
        pools = scoring_pools_for_league(db, league)
        league_keys = set(competition_keys_from_pools(pools))
        match_ids: list[int] = []
        seen: set[int] = set()
        for key in league_keys:
            for mid in changed_ids_by_key.get(key, []):
                if mid not in seen:
                    seen.add(mid)
                    match_ids.append(mid)
        changed: list[Match] = []
        if match_ids:
            by_id = {
                m.id: m
                for m in db.scalars(select(Match).where(Match.id.in_(match_ids))).all()
            }
            changed = [by_id[mid] for mid in match_ids if mid in by_id]
        try:
            score_summary = score_league_after_sync(db, league, changed)
            record_cron_league_result(
                db,
                league,
                ok=True,
                summary={
                    "changed": len(changed),
                    **score_summary,
                },
            )
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
            try:
                record_cron_league_result(
                    db,
                    league,
                    ok=False,
                    error=str(exc),
                )
                db.commit()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "record_cron_league_result failed league_id=%s", log_id(league)
                )
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
    pool_lookup = pool_lookup_for_league(db, league)
    pool_by_match: dict[int, TeamPool] = {}
    all_inputs = []
    for m in all_matches:
        pool = pool_for_match(db, league, m, lookup=pool_lookup)
        if pool is None:
            continue
        pool_by_match[m.id] = pool
        all_inputs.append(match_to_input(m, pool_id=pool.id))
    by_id = {m.id: m for m in all_matches}
    fixed_ranks = ranks_for_league(
        db, league, upset_rules, allow_live_catalog=True
    )

    scored = 0
    cascaded = 0
    skipped_missing_snapshot = 0
    skipped_match_ids: list[int] = []
    for match in changed:
        pool = pool_by_match.get(match.id) or pool_for_match(
            db, league, match, lookup=pool_lookup
        )
        if pool is None:
            continue
        mi = match_to_input(match, pool_id=pool.id)
        finished = is_finished(mi)
        if not finished:
            finished_missing_goals = match.status in FINISHED_STATUSES
            if finished_missing_goals:
                # Incomplete provider row (FINISHED/AWARDED but null goals). Do not
                # wipe existing events — a bad parse used to clear scores forever.
                logger.warning(
                    "score seed league_id=%s match_id=%s pool_id=%s "
                    "path=finished_missing_goals status=%s home_goals=%s away_goals=%s",
                    log_id(league),
                    match.id,
                    pool.id,
                    match.status,
                    match.home_goals,
                    match.away_goals,
                )
            else:
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
                "score seed league_id=%s match_id=%s pool_id=%s path=%s "
                "cascade_affected=%s starts_at=%s",
                log_id(league),
                match.id,
                pool.id,
                "finished_missing_goals_cascade"
                if finished_missing_goals
                else "unfinished_wipe",
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
                # Keep events when status says finished but goals are missing.
                if m.status not in FINISHED_STATUSES:
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
            # Zero-point outcomes (e.g. both sides 0 under custom result_points)
            # intentionally write no fantasy events. Record a 0-pt marker so
            # gap-fill does not treat the match as forever unscored and block
            # later fixtures on subsequent crons that only re-seed the earliest gap.
            if not desired:
                desired = (
                    ScoringEventDraft(
                        match_id=m.id,
                        team_id=m.home_team_id,
                        event_type="processed",
                        points=Decimal(0),
                        scheduled_matchweek=minput.scheduled_matchweek,
                        stage=minput.stage,
                        metadata={"reason": "zero_point_result"},
                    ),
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
