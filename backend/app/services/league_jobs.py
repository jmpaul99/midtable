"""Enqueue and run durable league sync/recompute jobs."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.logging_config import log_id
from app.models import League, LeagueJob
from app.providers.base import FootballProvider
from app.providers.football_data import FootballDataProvider

logger = logging.getLogger(__name__)

JobKind = Literal["sync", "recompute"]
JobSource = Literal["commissioner", "cron"]
ACTIVE_STATUSES = ("pending", "running")
TERMINAL_STATUSES = ("succeeded", "failed", "cancelled")


class ActiveJobConflict(Exception):
    """Raised when a league already has a pending/running job."""

    def __init__(self, job: LeagueJob):
        self.job = job
        super().__init__("A sync or recompute job is already in progress for this league")


class JobNotCancellable(Exception):
    """Raised when a job is not pending/running."""

    def __init__(self, job: LeagueJob):
        self.job = job
        super().__init__(f"Job is {job.status} and cannot be cancelled")


def get_job_by_public_id(db: Session, job_id: UUID) -> LeagueJob | None:
    return db.scalars(select(LeagueJob).where(LeagueJob.public_id == job_id)).first()


def release_competition_sync_locks_for_league(db: Session, league: League) -> int:
    """Clear in-progress SyncStatus locks for this league's scoring competitions.

    Used when cancelling a hung sync so another job can acquire the lock without
    waiting for the stale-lock timeout.
    """
    from app.models import SyncStatus
    from app.services.match_queries import (
        competition_keys_from_pools,
        scoring_pools_for_league,
    )

    keys = competition_keys_from_pools(scoring_pools_for_league(db, league))
    if not keys:
        return 0
    released = 0
    for provider, competition_code, season_year in keys:
        status = db.scalars(
            select(SyncStatus)
            .where(
                SyncStatus.provider == provider,
                SyncStatus.competition_code == competition_code,
                SyncStatus.season_year == season_year,
                SyncStatus.in_progress.is_(True),
            )
            .with_for_update()
        ).first()
        if status is None:
            continue
        status.in_progress = False
        status.in_progress_since = None
        released += 1
        logger.info(
            "league_job released sync lock competition=%s/%s/%s league_id=%s",
            provider,
            competition_code,
            season_year,
            log_id(league),
        )
    return released


def cancel_league_job(
    db: Session,
    league: League,
    job_id: UUID,
) -> LeagueJob:
    """Mark a pending/running job cancelled and release competition sync locks."""
    job = (
        db.scalars(
            select(LeagueJob).where(LeagueJob.public_id == job_id).with_for_update()
        ).first()
    )
    if job is None or job.league_id != league.id:
        raise ValueError(f"Job not found: {job_id}")
    if job.status not in ACTIVE_STATUSES:
        raise JobNotCancellable(job)

    now = datetime.now(UTC)
    prior = job.status
    job.status = "cancelled"
    job.error = "Cancelled by commissioner"
    if job.started_at is None:
        job.started_at = now
    job.finished_at = now
    released = 0
    if job.kind == "sync":
        released = release_competition_sync_locks_for_league(db, league)
    db.commit()
    db.refresh(job)
    logger.info(
        "league_job cancelled job_id=%s league_id=%s prior_status=%s locks_released=%s",
        job.public_id,
        log_id(league),
        prior,
        released,
    )
    return job


def _latest_for_source(db: Session, league_id: int, source: str) -> LeagueJob | None:
    return db.scalars(
        select(LeagueJob)
        .where(LeagueJob.league_id == league_id, LeagueJob.source == source)
        .order_by(LeagueJob.created_at.desc(), LeagueJob.id.desc())
        .limit(1)
    ).first()


def latest_jobs_for_league(db: Session, league_id: int) -> dict[str, LeagueJob | None]:
    """Return newest job per source: manual (commissioner) and cron."""
    return {
        "manual": _latest_for_source(db, league_id, "commissioner"),
        "cron": _latest_for_source(db, league_id, "cron"),
    }


def enqueue_league_job(
    db: Session,
    league: League,
    *,
    kind: JobKind,
    source: JobSource = "commissioner",
    created_by_profile_id: int | None = None,
) -> LeagueJob:
    """Create a pending job. Raises ActiveJobConflict if one is already active."""
    existing = db.scalars(
        select(LeagueJob).where(
            LeagueJob.league_id == league.id,
            LeagueJob.status.in_(ACTIVE_STATUSES),
        )
    ).first()
    if existing is not None:
        raise ActiveJobConflict(existing)

    job = LeagueJob(
        league_id=league.id,
        kind=kind,
        source=source,
        status="pending",
        created_by_profile_id=created_by_profile_id,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalars(
            select(LeagueJob).where(
                LeagueJob.league_id == league.id,
                LeagueJob.status.in_(ACTIVE_STATUSES),
            )
        ).first()
        if existing is not None:
            raise ActiveJobConflict(existing) from exc
        raise
    db.refresh(job)
    logger.info(
        "league_job enqueued job_id=%s league_id=%s kind=%s source=%s",
        job.public_id,
        log_id(league),
        kind,
        source,
    )
    return job


def record_cron_league_result(
    db: Session,
    league: League,
    *,
    ok: bool,
    summary: dict[str, Any] | None = None,
    error: str | None = None,
) -> LeagueJob:
    """Insert a terminal cron sync job after inline cron scoring (full history kept)."""
    now = datetime.now(UTC)
    job = LeagueJob(
        league_id=league.id,
        kind="sync",
        source="cron",
        status="succeeded" if ok else "failed",
        created_by_profile_id=None,
        summary=summary,
        error=error,
        started_at=now,
        finished_at=now,
    )
    db.add(job)
    db.flush()
    logger.info(
        "league_job cron recorded job_id=%s league_id=%s ok=%s",
        job.public_id,
        log_id(league),
        ok,
    )
    return job


def _json_safe_summary(result: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in result.items():
        if key in {"changed_matches", "ok", "sibling_results"}:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, dict):
            out[key] = {
                k: v
                for k, v in value.items()
                if isinstance(v, (str, int, float, bool, type(None)))
            }
    return out


def recompute_league_scores(db: Session, league: League) -> dict[str, Any]:
    """Shared recompute: seed from earliest finished match per scoring pool."""
    from app.services.match_queries import (
        matches_for_league,
        pool_for_match,
        pool_lookup_for_league,
        scoring_pools_for_league,
    )
    from app.services.sync import earliest_finished_seeds_per_pool, score_changed_matches

    started = time.perf_counter()
    matches = matches_for_league(db, league)
    scoring_pools = scoring_pools_for_league(db, league)
    scoring_pool_ids = {p.id for p in scoring_pools}
    pool_lookup = pool_lookup_for_league(db, league, pools=scoring_pools)
    pool_by_match_id: dict[int, int] = {}
    for m in matches:
        pool = pool_for_match(db, league, m, lookup=pool_lookup)
        if pool:
            pool_by_match_id[m.id] = pool.id
    finished, seeds = earliest_finished_seeds_per_pool(
        matches, pool_by_match_id=pool_by_match_id, scoring_pool_ids=scoring_pool_ids
    )
    logger.info(
        "recompute_scores start league_id=%s finished=%s seeds=%s",
        log_id(league),
        len(finished),
        len(seeds),
    )
    summary = score_changed_matches(db, league, seeds)
    db.commit()
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "recompute_scores done league_id=%s finished_matches=%s scored=%s "
        "cascaded=%s skipped_missing_snapshot=%s duration_ms=%.1f",
        log_id(league),
        len(finished),
        summary.get("scored", 0),
        summary.get("cascaded", 0),
        summary.get("skipped_missing_snapshot", 0),
        duration_ms,
    )
    return {"finished_matches": len(finished), **summary}


def run_league_job(
    db: Session,
    job_id: UUID,
    provider: FootballProvider,
) -> LeagueJob:
    """Claim a pending job and run sync or recompute to completion."""
    job = (
        db.scalars(
            select(LeagueJob).where(LeagueJob.public_id == job_id).with_for_update()
        ).first()
    )
    if job is None:
        raise ValueError(f"Job not found: {job_id}")
    if job.status != "pending":
        logger.info(
            "league_job skip job_id=%s status=%s reason=not_pending",
            job.public_id,
            job.status,
        )
        return job

    league = db.get(League, job.league_id)
    if league is None:
        job.status = "failed"
        job.error = "League not found"
        job.started_at = datetime.now(UTC)
        job.finished_at = datetime.now(UTC)
        db.commit()
        return job

    job.status = "running"
    job.started_at = datetime.now(UTC)
    job.error = None
    db.commit()

    outcome_status = "failed"
    outcome_error: str | None = "Unknown job kind"
    outcome_summary: dict[str, Any] | None = None

    try:
        if job.kind == "sync":
            from app.services.sync import sync_league_fixtures

            result = sync_league_fixtures(db, league, provider)
            if not result.get("ok"):
                outcome_status = "failed"
                outcome_error = str(result.get("error") or "Sync failed")
                outcome_summary = _json_safe_summary(result)
            else:
                outcome_status = "succeeded"
                outcome_error = None
                outcome_summary = _json_safe_summary(result)
        elif job.kind == "recompute":
            summary = recompute_league_scores(db, league)
            outcome_status = "succeeded"
            outcome_error = None
            outcome_summary = summary
        else:
            outcome_status = "failed"
            outcome_error = f"Unknown job kind: {job.kind}"
            outcome_summary = None
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "league_job failed job_id=%s league_id=%s kind=%s",
            job.public_id,
            log_id(league),
            job.kind,
        )
        db.rollback()
        refreshed = db.scalars(
            select(LeagueJob).where(LeagueJob.public_id == job_id).with_for_update()
        ).first()
        if refreshed is None:
            # Preserve the original failure; do not mask it with NoResultFound.
            raise
        if refreshed.status == "cancelled":
            logger.info(
                "league_job exception after cancel job_id=%s; leaving cancelled",
                job_id,
            )
            return refreshed
        job = refreshed
        job.status = "failed"
        job.error = str(exc)
        job.finished_at = datetime.now(UTC)
        try:
            db.commit()
            db.refresh(job)
        except Exception:
            logger.exception(
                "league_job could not persist failure status job_id=%s",
                job_id,
            )
            raise exc
        return job

    refreshed = db.scalars(
        select(LeagueJob).where(LeagueJob.public_id == job_id).with_for_update()
    ).first()
    if refreshed is None:
        raise ValueError(f"Job not found after run: {job_id}")
    if refreshed.status == "cancelled":
        logger.info(
            "league_job completed work but already cancelled job_id=%s",
            job_id,
        )
        return refreshed

    job = refreshed
    job.status = outcome_status
    job.error = outcome_error
    job.summary = outcome_summary
    job.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(job)

    logger.info(
        "league_job finished job_id=%s status=%s kind=%s",
        job.public_id,
        job.status,
        job.kind,
    )
    return job


def trigger_job_run(job_id: UUID) -> None:
    """Start the job without blocking the enqueue response.

    Prefer HTTP self-invoke so Cloud Run allocates CPU to a real request.
    Fall back to an in-process session on connection failure (e.g. tests).
    """
    import threading

    def _run() -> None:
        settings = get_settings()
        base = f"http://127.0.0.1:{settings.api_port}"
        url = f"{base}/internal/league-jobs/{job_id}/run"
        try:
            with httpx.Client(timeout=httpx.Timeout(600.0, connect=2.0)) as client:
                response = client.post(
                    url,
                    headers={"X-Cron-Secret": settings.cron_secret},
                )
                logger.info(
                    "league_job self-invoke done job_id=%s status=%s",
                    job_id,
                    response.status_code,
                )
        except httpx.ConnectError:
            logger.warning(
                "league_job self-invoke unreachable; running in-process job_id=%s",
                job_id,
            )
            run_job_in_new_session(job_id)
        except Exception:  # noqa: BLE001
            logger.exception("league_job self-invoke error job_id=%s", job_id)

    threading.Thread(target=_run, daemon=True, name=f"league-job-{job_id}").start()


def run_job_in_new_session(job_id: UUID) -> None:
    """Open a fresh DB session and football provider to run a job."""
    settings = get_settings()
    db = SessionLocal()
    provider: FootballDataProvider | None = None
    try:
        if not settings.football_data_api_token:
            job = get_job_by_public_id(db, job_id)
            if job is not None and job.status == "pending":
                job.status = "failed"
                job.error = "football-data.org token not configured"
                job.started_at = datetime.now(UTC)
                job.finished_at = datetime.now(UTC)
                db.commit()
            return
        provider = FootballDataProvider(
            settings.football_data_api_token,
            base_url=settings.football_data_base_url,
        )
        run_league_job(db, job_id, provider)
    except Exception:  # noqa: BLE001
        logger.exception("league_job background run failed job_id=%s", job_id)
    finally:
        if provider is not None:
            provider.close()
        db.close()
