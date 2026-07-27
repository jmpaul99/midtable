import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.db import get_db
from app.deps import get_football_provider, require_commissioner, require_cron_secret
from app.models import League, LeagueJob, LeagueMember, Profile
from app.providers.football_data import FootballDataProvider
from app.schemas.leagues import (
    LatestLeagueJobsResponse,
    LeagueJobResponse,
)
from app.services.league_jobs import (
    ActiveJobConflict,
    enqueue_league_job,
    get_job_by_public_id,
    latest_jobs_for_league,
    run_league_job,
    trigger_job_run,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])


def _job_response(job: LeagueJob) -> LeagueJobResponse:
    return LeagueJobResponse(
        id=job.public_id,
        kind=job.kind,
        source=job.source,
        status=job.status,
        error=job.error,
        summary=job.summary,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _enqueue_and_trigger(
    *,
    db: Session,
    league: League,
    kind: str,
    profile: Profile,
    response: Response,
) -> LeagueJobResponse:
    try:
        job = enqueue_league_job(
            db,
            league,
            kind=kind,  # type: ignore[arg-type]
            source="commissioner",
            created_by_profile_id=profile.id,
        )
    except ActiveJobConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "job": _job_response(exc.job).model_dump(mode="json"),
            },
        ) from exc
    trigger_job_run(job.public_id)
    response.status_code = status.HTTP_202_ACCEPTED
    return _job_response(job)


@router.post("/leagues/{league_id}/sync", response_model=LeagueJobResponse)
def commissioner_sync(
    response: Response,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> LeagueJobResponse:
    league, _ = membership
    logger.info(
        "commissioner_sync enqueue actor=commissioner league_id=%s",
        league.public_id,
    )
    return _enqueue_and_trigger(
        db=db, league=league, kind="sync", profile=profile, response=response
    )


@router.get(
    "/leagues/{league_id}/jobs/latest",
    response_model=LatestLeagueJobsResponse,
)
def latest_league_jobs(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> LatestLeagueJobsResponse:
    league, _ = membership
    latest = latest_jobs_for_league(db, league.id)
    return LatestLeagueJobsResponse(
        manual=_job_response(latest["manual"]) if latest["manual"] else None,
        cron=_job_response(latest["cron"]) if latest["cron"] else None,
    )


@router.get(
    "/leagues/{league_id}/jobs/{job_id}",
    response_model=LeagueJobResponse,
)
def get_league_job(
    job_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> LeagueJobResponse:
    league, _ = membership
    job = get_job_by_public_id(db, job_id)
    if job is None or job.league_id != league.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_response(job)


@router.post(
    "/internal/league-jobs/{job_id}/run",
    dependencies=[Depends(require_cron_secret)],
)
def run_league_job_internal(
    job_id: UUID,
    db: Session = Depends(get_db),
    provider: FootballDataProvider = Depends(get_football_provider),
) -> dict:
    logger.info("league_job internal run start job_id=%s", job_id)
    try:
        job = run_league_job(db, job_id, provider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "ok": job.status == "succeeded",
        "job": _job_response(job).model_dump(mode="json"),
    }
