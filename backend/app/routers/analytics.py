from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_league_member
from app.models import League, LeagueMember, Match, ScoringEvent, StandingsSnapshot, Team
from app.services import analytics as analytics_service

router = APIRouter(tags=["analytics"])


@router.get("/leagues/{league_id}/standings")
def standings(
    phase: str | None = Query(default=None),
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[dict]:
    league, _ = membership
    try:
        return analytics_service.leaderboard(db, league, phase_key=phase)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.get("/leagues/{league_id}/matches/{match_id}/events")
def match_events(
    match_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    match = db.scalars(
        select(Match).where(Match.public_id == match_id, Match.league_id == league.id)
    ).first()
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    events = db.scalars(select(ScoringEvent).where(ScoringEvent.match_id == match.id)).all()
    teams = {
        t.id: t
        for t in db.scalars(
            select(Team).where(Team.id.in_([match.home_team_id, match.away_team_id]))
        ).all()
    }
    snapshot = db.scalars(
        select(StandingsSnapshot).where(
            StandingsSnapshot.pool_id == match.pool_id,
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
