from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_league_member
from app.models import League, LeagueMember, Match, ScoringEvent, StandingsSnapshot, Team
from app.services import analytics as analytics_service
from app.services.analytics import phase_match_counts
from app.services.match_queries import matches_for_league, pool_for_match, scoring_pools_for_league


router = APIRouter(tags=["analytics"])


@router.get("/leagues/{league_id}/standings")
def standings(
    phase: str | None = Query(default=None),
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    phases = league.leaderboard_phases or []
    phase_meta = None
    match_filter = None
    if phase:
        phase_meta = next((p for p in phases if p.get("key") == phase), None)
        if phase_meta is None:
            raise HTTPException(status_code=400, detail=f"unknown phase key: {phase}")
        match_filter = phase_meta.get("match_filter")
    elif phases:
        # Season total when phase omitted — do not default to first phase
        phase_meta = None
        phase = None
        match_filter = None
    try:
        entries = analytics_service.leaderboard(db, league, phase_key=phase)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scoring_pools = scoring_pools_for_league(db, league)
    scoring_pool_ids = {p.id for p in scoring_pools}
    matches = matches_for_league(db, league)
    pool_by_match_id: dict[int, int] = {}
    for m in matches:
        pool = pool_for_match(db, league, m)
        if pool:
            pool_by_match_id[m.id] = pool.id
    counts = phase_match_counts(
        matches,
        match_filter=match_filter,
        scoring_pool_ids=scoring_pool_ids or None,
        pool_by_match_id=pool_by_match_id,
    )
    mf = (phase_meta or {}).get("match_filter") or {}
    matchweek_range = mf.get("matchweek_range")
    if not matchweek_range and mf.get("type") == "matchweek_range":
        fr, to = mf.get("from"), mf.get("to")
        if fr is not None and to is not None:
            matchweek_range = [int(fr), int(to)]
    return {
        "phase": {
            "key": (phase_meta or {}).get("key") or phase or "season",
            "name": (phase_meta or {}).get("name")
            or (phase_meta or {}).get("label")
            or phase
            or "Season",
            "matchweek_range": matchweek_range,
            "stage_in": mf.get("stage_in") or mf.get("stages"),
            "include_bonus_types": (phase_meta or {}).get("include_bonus_types") or [],
            **counts,
        },
        "entries": entries,
    }


@router.get("/leagues/{league_id}/stats/points-per-game")
def points_per_game(
    member_id: UUID | None = Query(default=None),
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[dict]:
    league, _ = membership
    return analytics_service.points_per_game(db, league, member_public_id=member_id)


@router.get("/leagues/{league_id}/stats/matchweeks")
def matchweek_stats(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[dict]:
    league, _ = membership
    return analytics_service.matchweek_breakdown(db, league)


@router.get("/leagues/{league_id}/stats/upsets")
def upset_stats(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[dict]:
    league, _ = membership
    return analytics_service.upset_stats(db, league)


@router.get("/leagues/{league_id}/stats/form")
def form_stats(
    member_id: UUID | None = Query(default=None),
    team_id: UUID | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=20),
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[dict]:
    league, _ = membership
    from app.services import match_stats as match_stats_service

    return match_stats_service.form_stats(
        db,
        league,
        member_public_id=member_id,
        team_public_id=team_id,
        limit=limit,
    )


@router.get("/leagues/{league_id}/stats/splits")
def venue_splits(
    member_id: UUID | None = Query(default=None),
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[dict]:
    league, _ = membership
    from app.services import match_stats as match_stats_service

    return match_stats_service.venue_splits(db, league, member_public_id=member_id)


@router.get("/leagues/{league_id}/stats/highlights")
def member_highlights(
    member_id: UUID = Query(...),
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    from app.services import match_stats as match_stats_service

    result = match_stats_service.member_highlights(db, league, member_public_id=member_id)
    if not result:
        raise HTTPException(status_code=404, detail="Manager not found")
    return result


@router.get("/leagues/{league_id}/matches/{match_id}/events")
def match_events(
    match_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    match = db.scalars(select(Match).where(Match.public_id == match_id)).first()
    if match is None or pool_for_match(db, league, match) is None:
        raise HTTPException(status_code=404, detail="Match not found")
    events = db.scalars(
        select(ScoringEvent).where(
            ScoringEvent.league_id == league.id,
            ScoringEvent.match_id == match.id,
        )
    ).all()
    teams = {
        t.id: t
        for t in db.scalars(
            select(Team).where(Team.id.in_([match.home_team_id, match.away_team_id]))
        ).all()
    }
    snapshot = db.scalars(
        select(StandingsSnapshot).where(
            StandingsSnapshot.provider == match.provider,
            StandingsSnapshot.competition_code == match.competition_code,
            StandingsSnapshot.season_year == match.season_year,
            StandingsSnapshot.kickoff_at == match.kickoff_at,
        )
    ).first()
    return {
        "match_id": str(match.public_id),
        "kickoff_at": match.kickoff_at.isoformat(),
        "home_team_id": str(teams[match.home_team_id].public_id),
        "away_team_id": str(teams[match.away_team_id].public_id),
        "home_goals": match.home_goals,
        "away_goals": match.away_goals,
        "snapshot_id": str(snapshot.public_id) if snapshot else None,
        "events": [
            {
                "id": str(e.public_id),
                "team_id": str(teams[e.team_id].public_id) if e.team_id in teams else None,
                "event_type": e.event_type,
                "points": float(e.points),
                "metadata": e.metadata_,
            }
            for e in events
        ],
    }
