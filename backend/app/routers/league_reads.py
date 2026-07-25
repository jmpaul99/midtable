"""League read models."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_commissioner, require_league_member, team_in_league
from app.models import (
    BonusType,
    League,
    LeagueMember,
    ManualBonus,
    Match,
    PoolTeam,
    Profile,
    RosterEntry,
    ScoringEvent,
    StandingsSnapshot,
    SyncStatus,
    Team,
    TeamPool,
)
from app.routers.league_mappers import effective_roster_club_order
from app.services import analytics as analytics_service
from app.services import match_stats as match_stats_service
from app.services.members import member_label
from app.schemas.leagues import (
    BonusAwardRow,
    MatchLogRow,
    MemberClubRow,
    MemberDetailResponse,
    PoolTeamResponse,
    RosterRowResponse,
    ScoringEventMatchRow,
    SnapshotAuditRow,
    SyncStatusResponse,
    TeamDetailResponse,
    TeamFixtureRow,
)

router = APIRouter(tags=["league-reads"])

_FINISHED = frozenset({"FINISHED", "AWARDED"})


@router.get("/leagues/{league_id}/pools/{pool_id}/teams", response_model=list[PoolTeamResponse])
def list_pool_teams(
    pool_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[PoolTeamResponse]:
    league, _ = membership
    pool = db.scalars(
        select(TeamPool).where(TeamPool.public_id == pool_id, TeamPool.league_id == league.id)
    ).first()
    if pool is None:
        raise HTTPException(status_code=404, detail="Pool not found")
    teams = db.scalars(
        select(Team)
        .join(PoolTeam, PoolTeam.team_id == Team.id)
        .where(PoolTeam.pool_id == pool.id)
        .order_by(Team.name)
    ).all()
    roster = {
        r.team_id: r
        for r in db.scalars(
            select(RosterEntry).where(
                RosterEntry.league_id == league.id,
                RosterEntry.pool_id == pool.id,
            )
        ).all()
    }
    members = {
        m.id: m
        for m in db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    }
    out: list[PoolTeamResponse] = []
    for team in teams:
        entry = roster.get(team.id)
        owner = None
        if entry:
            member = members.get(entry.member_id)
            profile = db.get(Profile, member.profile_id) if member else None
            owner = {
                "member_id": str(member.public_id) if member else None,
                "display_name": member_label(member, profile) if member else None,
                "acquired_via": entry.source,
            }
        out.append(
            PoolTeamResponse(
                id=team.public_id,
                name=team.name,
                crest_url=team.crest_url,
                provider_team_id=team.external_id,
                drafted=entry is not None,
                available=entry is None,
                current_owner=owner,
            )
        )
    return out


@router.get("/leagues/{league_id}/rosters", response_model=list[RosterRowResponse])
def list_rosters(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[RosterRowResponse]:
    league, _ = membership
    members = list(db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all())
    pools = sorted(
        list(db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all()),
        key=lambda p: (int(getattr(p, "sort_order", 0) or 0), p.label, p.id),
    )
    entries = list(db.scalars(select(RosterEntry).where(RosterEntry.league_id == league.id)).all())
    by_member_pool: dict[tuple[int, int], list[RosterEntry]] = {}
    for entry in entries:
        by_member_pool.setdefault((entry.member_id, entry.pool_id), []).append(entry)

    standings = analytics_service.leaderboard(db, league, phase_key=None)
    standing_by_member = {row["member_id"]: row for row in standings}
    pick_by_team = match_stats_service.draft_pick_numbers(db, league.id)

    team_ids = {e.team_id for e in entries}
    teams = {
        t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()
    } if team_ids else {}
    events = (
        list(
            db.scalars(
                select(ScoringEvent).where(
                    ScoringEvent.league_id == league.id,
                    ScoringEvent.team_id.in_(team_ids),
                )
            ).all()
        )
        if team_ids
        else []
    )
    bonuses = (
        list(
            db.scalars(
                select(ManualBonus).where(
                    ManualBonus.league_id == league.id,
                    ManualBonus.team_id.in_(team_ids),
                )
            ).all()
        )
        if team_ids
        else []
    )
    points_by_team: dict[int, float] = {}
    for event in events:
        points_by_team[event.team_id] = points_by_team.get(event.team_id, 0.0) + float(event.points)
    for bonus in bonuses:
        points_by_team[bonus.team_id] = points_by_team.get(bonus.team_id, 0.0) + float(bonus.points)
    stage_points_by_team = match_stats_service.points_by_stage_by_team(events)

    matches = (
        list(
            db.scalars(
                select(Match).where(
                    Match.league_id == league.id,
                    Match.status.in_(tuple(_FINISHED)),
                    (Match.home_team_id.in_(team_ids) | Match.away_team_id.in_(team_ids)),
                )
            ).all()
        )
        if team_ids
        else []
    )
    games_by_team: dict[int, int] = {}
    form_by_team: dict[int, list[str]] = {}
    for tid in team_ids:
        results = match_stats_service.team_results_from_matches(matches, tid)
        games_by_team[tid] = len(results)
        form_by_team[tid] = match_stats_service.form_from_results(results, limit=5)["form"]

    member_team_ids: dict[int, list[int]] = {}
    for entry in entries:
        member_team_ids.setdefault(entry.member_id, []).append(entry.team_id)

    member_wdl: dict[int, dict[str, int]] = {}
    for member in members:
        tids = member_team_ids.get(member.id, [])
        member_wdl[member.id] = match_stats_service.aggregate_member_wdl(matches, tids)

    rows: list[RosterRowResponse] = []
    for member in members:
        profile = db.get(Profile, member.profile_id)
        standing = standing_by_member.get(str(member.public_id))
        wdl = member_wdl.get(member.id, {"wins": 0, "draws": 0, "losses": 0, "games_played": 0})
        total_pts = float(standing["total_points"]) if standing else 0.0
        gp = int(wdl["games_played"])
        for pool in pools:
            owned = by_member_pool.get((member.id, pool.id), [])
            for slot in range(1, max(pool.slot_count, 1) + 1):
                entry = owned[slot - 1] if slot - 1 < len(owned) else None
                team = teams.get(entry.team_id) if entry else None
                club_pts = points_by_team.get(team.id, 0.0) if team else None
                club_gp = games_by_team.get(team.id, 0) if team else None
                rows.append(
                    RosterRowResponse(
                        id=entry.public_id if entry else None,
                        member_id=member.public_id,
                        display_name=member_label(member, profile),
                        pool_id=pool.public_id,
                        pool_name=pool.label,
                        pool_sort_order=int(getattr(pool, "sort_order", 0) or 0),
                        slot_number=slot,
                        team_id=team.public_id if team else None,
                        team_name=team.name if team else None,
                        crest_url=team.crest_url if team else None,
                        acquired_via=entry.source if entry else None,
                        draft_pick_number=pick_by_team.get(team.id) if team else None,
                        points=club_pts,
                        games_played=club_gp,
                        points_per_game=(club_pts / club_gp) if club_pts is not None and club_gp else None,
                        form=form_by_team.get(team.id) if team else None,
                        rank=int(standing["rank"]) if standing else None,
                        member_total_points=total_pts,
                        member_points_per_game=(total_pts / gp) if gp else 0.0,
                        member_wins=int(wdl["wins"]),
                        member_draws=int(wdl["draws"]),
                        member_losses=int(wdl["losses"]),
                        member_games_played=gp,
                        points_by_stage=stage_points_by_team.get(team.id, {}) if team else {},
                    )
                )
    return rows


@router.get("/leagues/{league_id}/match-log", response_model=list[MatchLogRow])
def match_log(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[MatchLogRow]:
    league, _ = membership
    matches = db.scalars(
        select(Match).where(Match.league_id == league.id).order_by(Match.kickoff_at.desc())
    ).all()
    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    teams = {
        t.id: t
        for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()
    } if team_ids else {}
    pools = {
        p.id: p
        for p in db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all()
    }
    match_ids = [m.id for m in matches]
    events = (
        list(
            db.scalars(select(ScoringEvent).where(ScoringEvent.match_id.in_(match_ids))).all()
        )
        if match_ids
        else []
    )
    points_by_match_team: dict[tuple[int, int], float] = {}
    for event in events:
        key = (event.match_id, event.team_id)
        points_by_match_team[key] = points_by_match_team.get(key, 0.0) + float(event.points)
    return [
        MatchLogRow(
            id=m.public_id,
            kickoff_at=m.kickoff_at,
            status=m.status,
            scheduled_matchweek=m.scheduled_matchweek,
            home_team_id=teams[m.home_team_id].public_id,
            away_team_id=teams[m.away_team_id].public_id,
            home_team_name=teams[m.home_team_id].name,
            away_team_name=teams[m.away_team_id].name,
            home_goals=m.home_goals,
            away_goals=m.away_goals,
            pool_id=pools[m.pool_id].public_id,
            home_points=points_by_match_team.get((m.id, m.home_team_id)),
            away_points=points_by_match_team.get((m.id, m.away_team_id)),
        )
        for m in matches
        if m.home_team_id in teams and m.away_team_id in teams and m.pool_id in pools
    ]


def _fixture_row(
    *,
    match: Match,
    team_id: int,
    teams: dict[int, Team],
    pools: dict[int, TeamPool],
    points: float | None,
    opponent_table_position: int | None = None,
) -> TeamFixtureRow | None:
    home = teams.get(match.home_team_id)
    away = teams.get(match.away_team_id)
    pool = pools.get(match.pool_id)
    if not home or not away or not pool:
        return None
    is_home = match.home_team_id == team_id
    opponent = away if is_home else home
    return TeamFixtureRow(
        id=match.public_id,
        kickoff_at=match.kickoff_at,
        status=match.status,
        scheduled_matchweek=match.scheduled_matchweek,
        home_team_id=home.public_id,
        away_team_id=away.public_id,
        home_team_name=home.name,
        away_team_name=away.name,
        home_goals=match.home_goals,
        away_goals=match.away_goals,
        pool_id=pool.public_id,
        is_home=is_home,
        points=points,
        opponent_name=opponent.name,
        opponent_id=opponent.public_id,
        opponent_table_position=opponent_table_position,
    )


@router.get("/leagues/{league_id}/members/{member_id}", response_model=MemberDetailResponse)
def member_detail(
    member_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> MemberDetailResponse:
    league, _ = membership
    member = db.scalars(
        select(LeagueMember).where(
            LeagueMember.public_id == member_id,
            LeagueMember.league_id == league.id,
        )
    ).first()
    if member is None:
        raise HTTPException(status_code=404, detail="Manager not found")
    profile = db.get(Profile, member.profile_id)

    standings = analytics_service.leaderboard(db, league, phase_key=None)
    standing = next((row for row in standings if row.get("member_id") == str(member.public_id)), None)

    roster_entries = db.scalars(
        select(RosterEntry).where(
            RosterEntry.league_id == league.id,
            RosterEntry.member_id == member.id,
        )
    ).all()
    team_ids = [e.team_id for e in roster_entries]
    teams = {
        t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()
    } if team_ids else {}
    pools = {
        p.id: p
        for p in db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all()
    }

    events = (
        list(
            db.scalars(
                select(ScoringEvent).where(
                    ScoringEvent.league_id == league.id,
                    ScoringEvent.team_id.in_(team_ids),
                )
            ).all()
        )
        if team_ids
        else []
    )

    event_points: dict[str, float] = {}
    event_counts: dict[str, int] = {}
    points_by_team: dict[int, float] = {}
    total_points = 0.0
    for event in events:
        pts = float(event.points)
        total_points += pts
        event_points[event.event_type] = event_points.get(event.event_type, 0.0) + pts
        event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
        points_by_team[event.team_id] = points_by_team.get(event.team_id, 0.0) + pts

    bonus_points = 0.0
    bonus_by_type: dict[str, float] = {}
    awarded_bonuses: list[BonusAwardRow] = []
    if team_ids:
        bonuses = list(
            db.scalars(
                select(ManualBonus)
                .where(
                    ManualBonus.league_id == league.id,
                    ManualBonus.team_id.in_(team_ids),
                )
                .order_by(ManualBonus.created_at.desc())
            ).all()
        )
        bonus_types = {
            bt.id: bt
            for bt in db.scalars(select(BonusType).where(BonusType.league_id == league.id)).all()
        }
        for bonus in bonuses:
            pts = float(bonus.points)
            bonus_points += pts
            total_points += pts
            bt = bonus_types.get(bonus.bonus_type_id)
            label = (bt.label or bt.key) if bt else "bonus"
            key = bt.key if bt else "bonus"
            bonus_by_type[label] = bonus_by_type.get(label, 0.0) + pts
            points_by_team[bonus.team_id] = points_by_team.get(bonus.team_id, 0.0) + pts
            team = teams.get(bonus.team_id)
            awarded_bonuses.append(
                BonusAwardRow(
                    id=bonus.public_id,
                    team_id=team.public_id if team else None,
                    team_name=team.name if team else None,
                    crest_url=team.crest_url if team else None,
                    bonus_type=key,
                    bonus_type_label=label,
                    points=pts,
                    reason=bonus.notes,
                    awarded_at=bonus.created_at,
                )
            )

    finished = (
        list(
            db.scalars(
                select(Match).where(
                    Match.league_id == league.id,
                    Match.status.in_(tuple(_FINISHED)),
                    (Match.home_team_id.in_(team_ids) | Match.away_team_id.in_(team_ids)),
                )
            ).all()
        )
        if team_ids
        else []
    )
    games_by_team: dict[int, int] = {}
    for match in finished:
        if match.home_team_id in teams:
            games_by_team[match.home_team_id] = games_by_team.get(match.home_team_id, 0) + 1
        if match.away_team_id in teams:
            games_by_team[match.away_team_id] = games_by_team.get(match.away_team_id, 0) + 1

    clubs: list[MemberClubRow] = []
    pick_by_team = match_stats_service.draft_pick_numbers(db, league.id)
    for entry in roster_entries:
        team = teams.get(entry.team_id)
        if team is None:
            continue
        pool = pools.get(entry.pool_id)
        pts = points_by_team.get(team.id, 0.0)
        gp = games_by_team.get(team.id, 0)
        clubs.append(
            MemberClubRow(
                team_id=team.public_id,
                team_name=team.name,
                crest_url=team.crest_url,
                pool_id=pool.public_id if pool else None,
                pool_name=pool.label if pool else None,
                pool_sort_order=int(getattr(pool, "sort_order", 0) or 0) if pool else 0,
                acquired_via=entry.source,
                draft_pick_number=pick_by_team.get(team.id),
                points=pts,
                games_played=gp,
                points_per_game=(pts / gp) if gp else 0.0,
            )
        )

    order_mode = effective_roster_club_order(league)

    def _club_sort_key(c: MemberClubRow) -> tuple[int, int, int, str]:
        if (c.acquired_via or "").lower() == "preassigned":
            draft_rank = 0
        elif c.draft_pick_number is not None:
            draft_rank = int(c.draft_pick_number)
        else:
            draft_rank = 10_000
        pool_rank = int(c.pool_sort_order or 0)
        if order_mode == "competition":
            return (pool_rank, draft_rank, 0, c.team_name)
        return (draft_rank, pool_rank, 0, c.team_name)

    clubs.sort(key=_club_sort_key)

    wdl = match_stats_service.aggregate_member_wdl(finished, team_ids)
    wins = int(wdl["wins"])
    draws = int(wdl["draws"])
    losses = int(wdl["losses"])
    upset_points = float(
        event_points.get("minor_upset", 0)
        + event_points.get("major_upset", 0)
        + event_points.get("major_upset_draw", 0)
    )
    games_played = int(wdl["games_played"])

    return MemberDetailResponse(
        id=member.public_id,
        team_name=member.team_name,
        display_name=profile.display_name if profile else None,
        draft_slot=member.draft_slot,
        rank=int(standing["rank"]) if standing else None,
        stats={
            "total_points": float(standing["total_points"]) if standing else total_points,
            "games_played": games_played,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "upset_points": upset_points,
            "bonus_points": bonus_points,
            "points_per_game": (total_points / games_played) if games_played else 0.0,
            "event_points_by_type": event_points,
            "event_counts_by_type": event_counts,
            "bonus_points_by_type": bonus_by_type,
        },
        clubs=clubs,
        bonuses=awarded_bonuses,
    )


@router.get("/leagues/{league_id}/teams/{team_id}", response_model=TeamDetailResponse)
def team_detail(
    team_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> TeamDetailResponse:
    league, _ = membership
    team = team_in_league(db, league.id, team_id)

    pool_link = db.scalars(
        select(PoolTeam)
        .join(TeamPool, TeamPool.id == PoolTeam.pool_id)
        .where(PoolTeam.team_id == team.id, TeamPool.league_id == league.id)
    ).first()
    pool = db.get(TeamPool, pool_link.pool_id) if pool_link else None

    entry = db.scalars(
        select(RosterEntry).where(
            RosterEntry.league_id == league.id,
            RosterEntry.team_id == team.id,
        )
    ).first()
    owner = None
    if entry:
        member = db.get(LeagueMember, entry.member_id)
        profile = db.get(Profile, member.profile_id) if member else None
        owner = {
            "member_id": str(member.public_id) if member else None,
            "display_name": member_label(member, profile) if member else None,
            "acquired_via": entry.source,
        }

    events = db.scalars(
        select(ScoringEvent).where(
            ScoringEvent.league_id == league.id,
            ScoringEvent.team_id == team.id,
        )
    ).all()
    event_points: dict[str, float] = {}
    event_counts: dict[str, int] = {}
    total_points = 0.0
    points_by_match: dict[int, float] = {}
    for event in events:
        pts = float(event.points)
        total_points += pts
        event_points[event.event_type] = event_points.get(event.event_type, 0.0) + pts
        event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
        points_by_match[event.match_id] = points_by_match.get(event.match_id, 0.0) + pts
    points_by_stage = match_stats_service.points_by_stage_from_events(events)

    bonus_points = 0.0
    bonuses = list(
        db.scalars(
            select(ManualBonus)
            .where(
                ManualBonus.league_id == league.id,
                ManualBonus.team_id == team.id,
            )
            .order_by(ManualBonus.created_at.desc())
        ).all()
    )
    bonus_types = {
        bt.id: bt
        for bt in db.scalars(select(BonusType).where(BonusType.league_id == league.id)).all()
    }
    bonus_by_type: dict[str, float] = {}
    awarded_bonuses: list[BonusAwardRow] = []
    for bonus in bonuses:
        pts = float(bonus.points)
        bonus_points += pts
        bt = bonus_types.get(bonus.bonus_type_id)
        key = bt.key if bt else "bonus"
        label = (bt.label or bt.key) if bt else "bonus"
        bonus_by_type[label] = bonus_by_type.get(label, 0.0) + pts
        awarded_bonuses.append(
            BonusAwardRow(
                id=bonus.public_id,
                team_id=team.public_id,
                team_name=team.name,
                crest_url=team.crest_url,
                bonus_type=key,
                bonus_type_label=label,
                points=pts,
                reason=bonus.notes,
                awarded_at=bonus.created_at,
            )
        )
    total_points += bonus_points

    matches = db.scalars(
        select(Match)
        .where(
            Match.league_id == league.id,
            (Match.home_team_id == team.id) | (Match.away_team_id == team.id),
        )
        .order_by(Match.kickoff_at.desc())
    ).all()
    matches_by_id = {m.id: m for m in matches}
    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches} | {team.id}
    # Include opponents from scoring events even if somehow missing from match list
    for event in events:
        match = matches_by_id.get(event.match_id)
        if match:
            team_ids.add(match.home_team_id)
            team_ids.add(match.away_team_id)
    teams = {
        t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()
    } if team_ids else {}
    pools = {
        p.id: p
        for p in db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all()
    }

    scoring_event_rows: list[ScoringEventMatchRow] = []
    for event in sorted(
        events,
        key=lambda e: (
            -(matches_by_id[e.match_id].kickoff_at.timestamp() if e.match_id in matches_by_id else 0),
            e.event_type,
        ),
    ):
        match = matches_by_id.get(event.match_id)
        if match is None:
            match = db.get(Match, event.match_id)
            if match is None:
                continue
            matches_by_id[match.id] = match
        is_home = match.home_team_id == team.id
        opponent = teams.get(match.away_team_id if is_home else match.home_team_id)
        if opponent is None:
            opponent = db.get(Team, match.away_team_id if is_home else match.home_team_id)
            if opponent:
                teams[opponent.id] = opponent
        if opponent is None:
            continue
        scoring_event_rows.append(
            ScoringEventMatchRow(
                id=event.public_id,
                event_type=event.event_type,
                points=float(event.points),
                match_id=match.public_id,
                kickoff_at=match.kickoff_at,
                scheduled_matchweek=match.scheduled_matchweek,
                status=match.status,
                is_home=is_home,
                home_goals=match.home_goals,
                away_goals=match.away_goals,
                opponent_id=opponent.public_id,
                opponent_name=opponent.name,
                metadata=event.metadata_ or {},
            )
        )

    recent_candidates: list[TeamFixtureRow] = []
    upcoming_candidates: list[TeamFixtureRow] = []
    table_by_team: dict[int, Any] = {}
    if pool is not None:
        table_by_team = match_stats_service.current_table_for_pool(db, pool=pool, league=league)

    team_results = match_stats_service.team_results_from_matches(matches, team.id)
    wdl = match_stats_service.wdl_from_results(team_results)
    goals = match_stats_service.goals_from_results(team_results)
    form = match_stats_service.form_from_results(team_results, limit=5)
    splits = match_stats_service.venue_split(team_results, points_by_match)
    table_row = table_by_team.get(team.id)

    for match in matches:
        finished = match.status in _FINISHED
        opponent_id = match.away_team_id if match.home_team_id == team.id else match.home_team_id
        opp_pos = (table_by_team.get(opponent_id) or {}).get("table_position")
        row = _fixture_row(
            match=match,
            team_id=team.id,
            teams=teams,
            pools=pools,
            points=points_by_match.get(match.id) if finished else None,
            opponent_table_position=opp_pos,
        )
        if row is None:
            continue
        if finished:
            recent_candidates.append(row)
        else:
            upcoming_candidates.append(row)

    recent = recent_candidates[:8]
    upcoming = sorted(upcoming_candidates, key=lambda r: r.kickoff_at)[:8]
    next_three = upcoming[:3]
    opp_ranks = [r.opponent_table_position for r in next_three if r.opponent_table_position]
    upcoming_difficulty = {
        "next_three": [
            {
                "match_id": str(r.id),
                "opponent_name": r.opponent_name,
                "opponent_id": str(r.opponent_id),
                "opponent_table_position": r.opponent_table_position,
                "is_home": r.is_home,
                "kickoff_at": r.kickoff_at.isoformat(),
            }
            for r in next_three
        ],
        "avg_opponent_rank": (sum(opp_ranks) / len(opp_ranks)) if opp_ranks else None,
    }

    wins = int(wdl["wins"])
    draws = int(wdl["draws"])
    losses = int(wdl["losses"])
    upset_points = float(
        event_points.get("minor_upset", 0)
        + event_points.get("major_upset", 0)
        + event_points.get("major_upset_draw", 0)
    )
    games_played = int(wdl["games_played"])

    return TeamDetailResponse(
        id=team.public_id,
        name=team.name,
        crest_url=team.crest_url,
        pool_id=pool.public_id if pool else None,
        pool_name=pool.label if pool else None,
        owner=owner,
        stats={
            "total_points": total_points,
            "games_played": games_played,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "upset_points": upset_points,
            "bonus_points": bonus_points,
            "points_per_game": (total_points / games_played) if games_played else 0.0,
            "event_points_by_type": event_points,
            "event_counts_by_type": event_counts,
            "bonus_points_by_type": bonus_by_type,
            "points_by_stage": points_by_stage,
            "goals_for": goals["goals_for"],
            "goals_against": goals["goals_against"],
            "goal_difference": goals["goal_difference"],
            "table_position": table_row["table_position"] if table_row else None,
            "table_points": table_row["table_points"] if table_row else None,
            "form": form["form"],
            "current_streak": form["current_streak"],
            "home": splits["home"],
            "away": splits["away"],
            "upcoming_difficulty": upcoming_difficulty,
        },
        bonuses=awarded_bonuses,
        scoring_events=scoring_event_rows,
        recent_matches=recent,
        upcoming_matches=upcoming,
    )


@router.get("/leagues/{league_id}/sync-status", response_model=list[SyncStatusResponse])
def sync_status(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> list[SyncStatusResponse]:
    league, _ = membership
    rows = db.scalars(select(SyncStatus).where(SyncStatus.league_id == league.id)).all()
    return [
        SyncStatusResponse(
            id=row.public_id,
            provider=row.provider,
            status="in_progress" if row.in_progress else ("error" if row.last_error else "idle"),
            last_success_at=row.last_sync_at,
            last_attempt_at=row.in_progress_since or row.last_sync_at,
            rate_limit_remaining=row.requests_available_minute,
            last_error=row.last_error,
            last_summary=row.last_summary,
            in_progress=row.in_progress,
        )
        for row in rows
    ]


@router.get("/leagues/{league_id}/snapshot-audit", response_model=list[SnapshotAuditRow])
def snapshot_audit(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[SnapshotAuditRow]:
    league, _ = membership
    pools = {
        p.id: p
        for p in db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all()
    }
    if not pools:
        return []
    snaps = db.scalars(
        select(StandingsSnapshot)
        .where(StandingsSnapshot.pool_id.in_(list(pools)))
        .order_by(StandingsSnapshot.kickoff_at.desc())
    ).all()
    out: list[SnapshotAuditRow] = []
    for snap in snaps:
        pool = pools[snap.pool_id]
        team_ids = [r.team_id for r in snap.rows]
        teams = {
            t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()
        } if team_ids else {}
        out.append(
            SnapshotAuditRow(
                id=snap.public_id,
                pool_id=pool.public_id,
                kickoff_at=snap.kickoff_at,
                stale=snap.stale,
                computed_at=snap.computed_at,
                rows=[
                    {
                        "team_id": str(teams[r.team_id].public_id) if r.team_id in teams else None,
                        "team_name": teams[r.team_id].name if r.team_id in teams else None,
                        "position": r.rank,
                        "played": r.played,
                        "points": r.points,
                        "goals_for": r.goals_for,
                        "goals_against": r.goals_against,
                        "goal_difference": r.goal_difference,
                    }
                    for r in snap.rows
                ],
            )
        )
    return out


