"""Enqueue and run durable platform-admin sync jobs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.models import PlatformJob
from app.providers.football_data import FootballDataProvider

logger = logging.getLogger(__name__)

JobKind = Literal["teams_and_rankings", "fifa_rankings"]
JobSource = Literal["admin", "cron"]
ACTIVE_STATUSES = ("pending", "running")


class ActivePlatformJobConflict(Exception):
    """Raised when a platform job is already pending/running."""

    def __init__(self, job: PlatformJob):
        self.job = job
        super().__init__("A platform sync job is already in progress")


def get_platform_job_by_public_id(db: Session, job_id: UUID) -> PlatformJob | None:
    return db.scalars(select(PlatformJob).where(PlatformJob.public_id == job_id)).first()


def _latest_for_source(db: Session, source: str) -> PlatformJob | None:
    return db.scalars(
        select(PlatformJob)
        .where(PlatformJob.source == source)
        .order_by(PlatformJob.created_at.desc(), PlatformJob.id.desc())
        .limit(1)
    ).first()


def latest_platform_jobs(db: Session) -> dict[str, PlatformJob | None]:
    """Return newest job per source: manual (admin) and cron."""
    return {
        "manual": _latest_for_source(db, "admin"),
        "cron": _latest_for_source(db, "cron"),
    }


def enqueue_platform_job(
    db: Session,
    *,
    kind: JobKind,
    source: JobSource = "admin",
    created_by_profile_id: int | None = None,
    params: dict[str, Any] | None = None,
) -> PlatformJob:
    """Create a pending job. Raises ActivePlatformJobConflict if one is already active."""
    existing = db.scalars(
        select(PlatformJob).where(PlatformJob.status.in_(ACTIVE_STATUSES))
    ).first()
    if existing is not None:
        raise ActivePlatformJobConflict(existing)

    job = PlatformJob(
        kind=kind,
        source=source,
        status="pending",
        created_by_profile_id=created_by_profile_id,
        params=params,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalars(
            select(PlatformJob).where(PlatformJob.status.in_(ACTIVE_STATUSES))
        ).first()
        if existing is not None:
            raise ActivePlatformJobConflict(existing) from exc
        raise
    db.refresh(job)
    logger.info(
        "platform_job enqueued job_id=%s kind=%s source=%s",
        job.public_id,
        kind,
        source,
    )
    return job


def record_cron_platform_result(
    db: Session,
    *,
    kind: JobKind = "fifa_rankings",
    ok: bool,
    summary: dict[str, Any] | None = None,
    error: str | None = None,
) -> PlatformJob:
    """Insert a terminal cron job after inline cron work (full history kept)."""
    now = datetime.now(UTC)
    job = PlatformJob(
        kind=kind,
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
        "platform_job cron recorded job_id=%s kind=%s ok=%s",
        job.public_id,
        kind,
        ok,
    )
    return job


def _json_safe_teams_and_rankings_summary(result: dict[str, Any]) -> dict[str, Any]:
    teams = result.get("teams") if isinstance(result.get("teams"), dict) else {}
    rankings = result.get("rankings") if isinstance(result.get("rankings"), dict) else {}
    snaps = (
        result.get("table_snapshots")
        if isinstance(result.get("table_snapshots"), dict)
        else {}
    )
    out: dict[str, Any] = {
        "ok": result.get("ok"),
        "season_year": result.get("season_year"),
        "teams_created": teams.get("created"),
        "teams_updated": teams.get("updated"),
        "competitions_ok": teams.get("competitions_ok"),
        "competitions_total": teams.get("competitions_total"),
        "rankings_ok": rankings.get("ok"),
        "rankings_skipped": rankings.get("skipped"),
        "created_previous_final": snaps.get("created_previous_final"),
        "created_zeroed_opener": snaps.get("created_zeroed_opener"),
    }
    if isinstance(rankings.get("message"), str):
        out["rankings_message"] = rankings["message"]
    if isinstance(rankings.get("error"), str):
        out["rankings_error"] = rankings["error"]
    catalogs = rankings.get("catalogs")
    if isinstance(catalogs, dict):
        compact: dict[str, Any] = {}
        for key, row in catalogs.items():
            if isinstance(row, dict) and isinstance(row.get("entries"), int):
                compact[str(key)] = {"entries": row["entries"]}
        if compact:
            out["rankings_catalogs"] = compact
    competitions = teams.get("competitions")
    if isinstance(competitions, list):
        fallbacks = [
            f"{c.get('code')}→{c.get('season_year')}"
            for c in competitions
            if isinstance(c, dict) and c.get("ok") and c.get("fell_back_to_latest")
        ]
        if fallbacks:
            out["season_fallbacks"] = fallbacks
    return {k: v for k, v in out.items() if v is not None}


def json_safe_fifa_summary(result: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": result.get("ok")}
    catalogs = result.get("catalogs")
    if isinstance(catalogs, dict):
        compact: dict[str, Any] = {}
        for key, row in catalogs.items():
            if isinstance(row, dict) and isinstance(row.get("entries"), int):
                compact[str(key)] = {"entries": row["entries"]}
        if compact:
            out["rankings_catalogs"] = compact
    return {k: v for k, v in out.items() if v is not None}


def run_platform_job(
    db: Session,
    job_id: UUID,
    provider: FootballDataProvider,
    settings: Settings,
) -> PlatformJob:
    """Claim a pending job and run it to completion."""
    job = (
        db.scalars(
            select(PlatformJob).where(PlatformJob.public_id == job_id).with_for_update()
        ).first()
    )
    if job is None:
        raise ValueError(f"Job not found: {job_id}")
    if job.status != "pending":
        logger.info(
            "platform_job skip job_id=%s status=%s reason=not_pending",
            job.public_id,
            job.status,
        )
        return job

    job.status = "running"
    job.started_at = datetime.now(UTC)
    job.error = None
    db.commit()

    try:
        if job.kind == "teams_and_rankings":
            from app.services.global_sync import sync_all_teams_and_rankings

            params = job.params if isinstance(job.params, dict) else {}
            season_year = params.get("season_year")
            if season_year is not None:
                season_year = int(season_year)
            result = sync_all_teams_and_rankings(
                db,
                provider,
                settings=settings,
                season_year=season_year,
            )
            summary = _json_safe_teams_and_rankings_summary(result)
            if not result.get("ok") and not (result.get("teams") or {}).get("ok"):
                job.status = "failed"
                job.error = str(
                    (result.get("teams") or {}).get("error")
                    or (result.get("rankings") or {}).get("error")
                    or "Sync failed"
                )
                job.summary = summary
            else:
                job.status = "succeeded"
                job.summary = summary
                job.error = None
        else:
            job.status = "failed"
            job.error = f"Unknown job kind: {job.kind}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("platform_job failed job_id=%s kind=%s", job.public_id, job.kind)
        db.rollback()
        refreshed = db.scalars(
            select(PlatformJob).where(PlatformJob.public_id == job_id).with_for_update()
        ).first()
        if refreshed is None:
            raise
        job = refreshed
        job.status = "failed"
        job.error = str(exc)
        job.finished_at = datetime.now(UTC)
        try:
            db.commit()
            db.refresh(job)
        except Exception:
            logger.exception(
                "platform_job could not persist failure status job_id=%s",
                job_id,
            )
            raise exc
        return job

    job.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(job)

    logger.info(
        "platform_job finished job_id=%s status=%s kind=%s",
        job.public_id,
        job.status,
        job.kind,
    )
    return job


def trigger_platform_job_run(job_id: UUID) -> None:
    """Start the job without blocking the enqueue response."""
    import threading

    def _run() -> None:
        settings = get_settings()
        base = f"http://127.0.0.1:{settings.api_port}"
        url = f"{base}/internal/platform-jobs/{job_id}/run"
        try:
            with httpx.Client(timeout=httpx.Timeout(600.0, connect=2.0)) as client:
                response = client.post(
                    url,
                    headers={"X-Cron-Secret": settings.cron_secret},
                )
                logger.info(
                    "platform_job self-invoke done job_id=%s status=%s",
                    job_id,
                    response.status_code,
                )
        except httpx.ConnectError:
            logger.warning(
                "platform_job self-invoke unreachable; running in-process job_id=%s",
                job_id,
            )
            run_platform_job_in_new_session(job_id)
        except Exception:  # noqa: BLE001
            logger.exception("platform_job self-invoke error job_id=%s", job_id)

    threading.Thread(target=_run, daemon=True, name=f"platform-job-{job_id}").start()


def run_platform_job_in_new_session(job_id: UUID) -> None:
    """Open a fresh DB session and football provider to run a job."""
    settings = get_settings()
    db = SessionLocal()
    provider: FootballDataProvider | None = None
    try:
        if not settings.football_data_api_token:
            job = get_platform_job_by_public_id(db, job_id)
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
        run_platform_job(db, job_id, provider, settings)
    except Exception:  # noqa: BLE001
        logger.exception("platform_job background run failed job_id=%s", job_id)
    finally:
        if provider is not None:
            provider.close()
        db.close()
