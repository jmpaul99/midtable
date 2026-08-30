from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_league_member
from app.models import League, LeagueMember, Match, ScoringEvent, StandingsSnapshot, Team
from app.schemas.analytics import (
    FormStatRow,
    MatchEventsResponse,
    MatchweekStatRow,
    MemberHighlightsResponse,
    PointsPerGameRow,
    StandingsResponse,
    UpsetStatRow,
    VenueSplitRow,
)
from app.services import analytics as analytics_service
from app.services.analytics import phase_match_counts
from app.services import match_stats as match_stats_service
from app.services.match_queries import (
    FINISHED_STATUSES,
    matches_for_league,
    pool_for_match,
    pool_lookup_for_league,
    scoring_pools_for_league,
)
from app.services.phases import phase_match_filter_fields
from app.services.roster_owners import owner_by_team_id_for_league


router = APIRouter(tags=["analytics"])


@router.get("/leagues/{league_id}/standings", response_model=StandingsResponse)
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
    pool_lookup = pool_lookup_for_league(db, league, pools=scoring_pools)
    pool_by_match_id: dict[int, int] = {}
    for m in matches:
        pool = pool_for_match(db, league, m, lookup=pool_lookup)
        if pool:
            pool_by_match_id[m.id] = pool.id
    counts = phase_match_counts(
        matches,
        match_filter=match_filter,
        scoring_pool_ids=scoring_pool_ids or None,
        pool_by_match_id=pool_by_match_id,
    )
    fields = phase_match_filter_fields((phase_meta or {}).get("match_filter") or {})
    return {
        "phase": {
            "key": (phase_meta or {}).get("key") or phase or "season",
            "name": (phase_meta or {}).get("name")
            or (phase_meta or {}).get("label")
            or phase
            or "Season",
            "matchweek_range": fields.matchweek_range,
            "stage_in": fields.stage_in,
            "include_bonus_types": (phase_meta or {}).get("include_bonus_types") or [],
            **counts,
        },
        "entries": entries,
    }


@router.get("/leagues/{league_id}/stats/points-per-game", response_model=list[PointsPerGameRow])
def points_per_game(
    member_id: UUID | None = Query(default=None),
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[dict]:
    league, _ = membership
    return analytics_service.points_per_game(db, league, member_public_id=member_id)


@router.get("/leagues/{league_id}/stats/matchweeks", response_model=list[MatchweekStatRow])
def matchweek_stats(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[dict]:
    league, _ = membership
    return analytics_service.matchweek_breakdown(db, league)


@router.get("/leagues/{league_id}/stats/upsets", response_model=list[UpsetStatRow])
def upset_stats(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[dict]:
    league, _ = membership
    return analytics_service.upset_stats(db, league)


@router.get("/leagues/{league_id}/stats/form", response_model=list[FormStatRow])
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


@router.get("/leagues/{league_id}/stats/splits", response_model=list[VenueSplitRow])
def venue_splits(
    member_id: UUID | None = Query(default=None),
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[dict]:
    league, _ = membership
    from app.services import match_stats as match_stats_service

    return match_stats_service.venue_splits(db, league, member_public_id=member_id)


@router.get("/leagues/{league_id}/stats/highlights", response_model=MemberHighlightsResponse)
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


@router.get("/leagues/{league_id}/matches/{match_id}/events", response_model=MatchEventsResponse)
def match_events(
    match_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    match = db.scalars(select(Match).where(Match.public_id == match_id)).first()
    pool = pool_for_match(db, league, match) if match is not None else None
    if match is None or pool is None:
        raise HTTPException(status_code=404, detail="Match not found")
    events = list(
        db.scalars(
            select(ScoringEvent).where(
                ScoringEvent.league_id == league.id,
                ScoringEvent.match_id == match.id,
            )
        ).all()
    )
    teams = {
        t.id: t
        for t in db.scalars(
            select(Team).where(Team.id.in_([match.home_team_id, match.away_team_id]))
        ).all()
    }
    home = teams.get(match.home_team_id)
    away = teams.get(match.away_team_id)
    if home is None or away is None:
        raise HTTPException(status_code=404, detail="Match not found")
    snapshot = db.scalars(
        select(StandingsSnapshot).where(
            StandingsSnapshot.provider == match.provider,
            StandingsSnapshot.competition_code == match.competition_code,
            StandingsSnapshot.season_year == match.season_year,
            StandingsSnapshot.kickoff_at == match.kickoff_at,
        )
    ).first()
    points_by_team = match_stats_service.points_by_match_team(events)
    owners = owner_by_team_id_for_league(db, league)
    finished = match.status in FINISHED_STATUSES
    home_pts = points_by_team.get((match.id, match.home_team_id))
    away_pts = points_by_team.get((match.id, match.away_team_id))
    if finished:
        home_pts = home_pts if home_pts is not None else 0.0
        away_pts = away_pts if away_pts is not None else 0.0
    return {
        "match_id": str(match.public_id),
        "kickoff_at": match.kickoff_at.isoformat(),
        "status": match.status,
        "scheduled_matchweek": match.scheduled_matchweek,
        "duration": match.duration,
        "stage": match.stage,
        "pool_label": pool.label,
        "home_team_id": str(home.public_id),
        "away_team_id": str(away.public_id),
        "home_team_name": home.name,
        "away_team_name": away.name,
        "home_goals": match.home_goals,
        "away_goals": match.away_goals,
        "home_points": home_pts,
        "away_points": away_pts,
        "home_owner": owners.get(match.home_team_id),
        "away_owner": owners.get(match.away_team_id),
        "snapshot_id": str(snapshot.public_id) if snapshot else None,
        "events": [
            {
                "id": str(e.public_id),
                "team_id": str(teams[e.team_id].public_id) if e.team_id in teams else None,
                "team_name": teams[e.team_id].name if e.team_id in teams else None,
                "event_type": e.event_type,
                "points": float(e.points),
                "metadata": e.metadata_,
            }
            for e in events
        ],
    }
