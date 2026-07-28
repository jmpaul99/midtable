"""League read models."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_commissioner, require_league_member, team_in_league
from app.models import (
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
from app.services.bonuses import (
    accumulate_bonus_awards,
    load_bonus_context,
)
from app.services.match_queries import (
    FINISHED_STATUSES,
    MatchSort,
    competition_key_predicate_for,
    competition_keys_from_pools,
    matches_for_league,
    paginate_matches,
    pool_for_match,
    pool_lookup_for_league,
    scoring_pools_for_league,
)
from app.services.members import member_label
from app.services.roster_owners import (
    owner_by_team_id_for_league,
    owner_dict,
    roster_entries_for_member,
    team_ids_for_member,
)
from app.schemas.leagues import (
    MatchLogPage,
    MatchLogRow,
    MemberClubRow,
    MemberDetailResponse,
    PoolTeamResponse,
    RosterRowResponse,
    ScoringEventMatchRow,
    SnapshotAuditRow,
    SyncStatusResponse,
    TeamDetailResponse,
    TeamFixturePage,
    TeamFixtureRow,
)

router = APIRouter(tags=["league-reads"])

_FINISHED = FINISHED_STATUSES


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
        raise HTTPException(status_code=404, detail="Competition not found")
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
    profile_ids = {m.profile_id for m in members.values() if m.profile_id}
    profiles = {
        p.id: p
        for p in (
            db.scalars(select(Profile).where(Profile.id.in_(profile_ids))).all()
            if profile_ids
            else []
        )
    }
    out: list[PoolTeamResponse] = []
    for team in teams:
        entry = roster.get(team.id)
        owner = None
        if entry:
            member = members.get(entry.member_id)
            if member:
                profile = profiles.get(member.profile_id) if member.profile_id else None
                owner = owner_dict(member, profile, entry.source)
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
        [
            m
            for m in matches_for_league(db, league)
            if m.status in _FINISHED
            and (m.home_team_id in team_ids or m.away_team_id in team_ids)
        ]
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


@router.get("/leagues/{league_id}/match-log", response_model=MatchLogPage)
def match_log(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
    section: str | None = Query(default=None, pattern="^(upcoming|results)$"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    pool_id: UUID | None = None,
    team_id: UUID | None = None,
    member_id: UUID | None = None,
    mine: bool = False,
    sort: str = Query(default="kickoff", pattern="^(kickoff|points)$"),
    q: str | None = Query(default=None, max_length=80),
) -> MatchLogPage:
    league, current_member = membership
    pools = scoring_pools_for_league(db, league)
    pool_by_key = pool_lookup_for_league(db, league, pools=pools)

    if pool_id is not None:
        pool = next((p for p in pools if p.public_id == pool_id), None)
        if pool is None:
            raise HTTPException(status_code=404, detail="Competition not found")
        if pool.competition_code is None or pool.season_year is None:
            return MatchLogPage(items=[], has_more=False)
        keys = [(pool.provider, pool.competition_code, pool.season_year)]
    else:
        keys = competition_keys_from_pools(pools)

    if not keys:
        return MatchLogPage(items=[], has_more=False)

    filters: list[Any] = []
    if section == "results":
        filters.append(Match.status.in_(list(_FINISHED)))
    elif section == "upcoming":
        filters.append(Match.status.notin_(list(_FINISHED)))

    if team_id is not None:
        club = team_in_league(db, league.id, team_id)
        filters.append(or_(Match.home_team_id == club.id, Match.away_team_id == club.id))

    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        matching_team_ids = select(Team.id).where(
            or_(
                Team.name.ilike(like),
                Team.short_name.ilike(like),
                Team.tla.ilike(like),
            )
        )
        filters.append(
            or_(
                Match.home_team_id.in_(matching_team_ids),
                Match.away_team_id.in_(matching_team_ids),
            )
        )

    owner_member: LeagueMember | None = None
    if mine:
        owner_member = current_member
    elif member_id is not None:
        owner_member = db.scalars(
            select(LeagueMember).where(
                LeagueMember.league_id == league.id,
                LeagueMember.public_id == member_id,
            )
        ).first()
        if owner_member is None:
            raise HTTPException(status_code=404, detail="Manager not found")
    if owner_member is not None:
        owned_team_ids = team_ids_for_member(
            db, league_id=league.id, member_id=owner_member.id
        )
        if not owned_team_ids:
            return MatchLogPage(items=[], has_more=False)
        filters.append(
            or_(
                Match.home_team_id.in_(owned_team_ids),
                Match.away_team_id.in_(owned_team_ids),
            )
        )

    use_points_sort = sort == "points" and section == "results"
    order: MatchSort
    if use_points_sort:
        order = "points_desc"
    elif section == "upcoming":
        order = "kickoff_asc"
    else:
        order = "kickoff_desc"

    matches, has_more = paginate_matches(
        db,
        keys=keys,
        limit=limit,
        offset=offset,
        filters=filters,
        order=order,
        league_id=league.id if use_points_sort else None,
    )

    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    teams = {
        t.id: t
        for t in (
            db.scalars(select(Team).where(Team.id.in_(team_ids))).all() if team_ids else []
        )
    }
    match_ids = [m.id for m in matches]
    events = (
        list(
            db.scalars(
                select(ScoringEvent).where(
                    ScoringEvent.league_id == league.id,
                    ScoringEvent.match_id.in_(match_ids),
                )
            ).all()
        )
        if match_ids
        else []
    )
    points_by_match_team = match_stats_service.points_by_match_team(events)
    owner_by_team_id = owner_by_team_id_for_league(db, league)

    rows: list[MatchLogRow] = []
    for m in matches:
        pool = pool_by_key.get((m.provider, m.competition_code, m.season_year))
        if pool is None or m.home_team_id not in teams or m.away_team_id not in teams:
            continue
        home_pts = points_by_match_team.get((m.id, m.home_team_id))
        away_pts = points_by_match_team.get((m.id, m.away_team_id))
        rows.append(
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
                pool_id=pool.public_id,
                pool_label=pool.label,
                home_points=home_pts,
                away_points=away_pts,
                home_owner=owner_by_team_id.get(m.home_team_id),
                away_owner=owner_by_team_id.get(m.away_team_id),
            )
        )

    return MatchLogPage(items=rows, has_more=has_more)


def _fixture_row(
    *,
    match: Match,
    team_id: int,
    teams: dict[int, Team],
    pool: TeamPool | None,
    points: float | None,
    opponent_table_position: int | None = None,
    opponent_owner: dict[str, Any] | None = None,
) -> TeamFixtureRow | None:
    home = teams.get(match.home_team_id)
    away = teams.get(match.away_team_id)
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
        opponent_owner=opponent_owner,
    )


def _resolve_member(db: Session, league: League, member_id: UUID) -> LeagueMember:
    member = db.scalars(
        select(LeagueMember).where(
            LeagueMember.public_id == member_id,
            LeagueMember.league_id == league.id,
        )
    ).first()
    if member is None:
        raise HTTPException(status_code=404, detail="Manager not found")
    return member


def _league_competition_keys(db: Session, league: League) -> list[tuple[str, str, int]]:
    return competition_keys_from_pools(scoring_pools_for_league(db, league))


def _member_fixture_page(
    db: Session,
    league: League,
    member: LeagueMember,
    *,
    section: str,
    limit: int,
    offset: int,
    club_id: UUID | None = None,
    opponent_member_id: UUID | None = None,
) -> TeamFixturePage:
    owned_team_ids = team_ids_for_member(
        db, league_id=league.id, member_id=member.id
    )
    if not owned_team_ids:
        return TeamFixturePage(items=[], has_more=False)

    focus_club_id: int | None = None
    if club_id is not None:
        club = team_in_league(db, league.id, club_id)
        if club.id not in owned_team_ids:
            raise HTTPException(status_code=404, detail="Club not on this roster")
        focus_club_id = club.id

    opponent_team_ids: set[int] | None = None
    if opponent_member_id is not None:
        opponent_member = _resolve_member(db, league, opponent_member_id)
        opponent_team_ids = team_ids_for_member(
            db, league_id=league.id, member_id=opponent_member.id
        )
        if not opponent_team_ids:
            return TeamFixturePage(items=[], has_more=False)

    keys = _league_competition_keys(db, league)
    if not keys:
        return TeamFixturePage(items=[], has_more=False)

    filters: list[Any] = []
    if section == "recent":
        filters.append(Match.status.in_(list(_FINISHED)))
    else:
        filters.append(Match.status.notin_(list(_FINISHED)))

    focus_set = {focus_club_id} if focus_club_id is not None else owned_team_ids
    if opponent_team_ids is not None:
        filters.append(
            or_(
                and_(
                    Match.home_team_id.in_(focus_set),
                    Match.away_team_id.in_(opponent_team_ids),
                ),
                and_(
                    Match.away_team_id.in_(focus_set),
                    Match.home_team_id.in_(opponent_team_ids),
                ),
            )
        )
    elif focus_club_id is not None:
        filters.append(
            or_(Match.home_team_id == focus_club_id, Match.away_team_id == focus_club_id)
        )
    else:
        filters.append(
            or_(
                Match.home_team_id.in_(owned_team_ids),
                Match.away_team_id.in_(owned_team_ids),
            )
        )

    matches, has_more = paginate_matches(
        db,
        keys=keys,
        limit=limit,
        offset=offset,
        filters=filters,
        order="kickoff_asc" if section == "upcoming" else "kickoff_desc",
    )

    involved_team_ids = (
        {m.home_team_id for m in matches}
        | {m.away_team_id for m in matches}
        | owned_team_ids
    )
    teams = {
        t.id: t
        for t in (
            db.scalars(select(Team).where(Team.id.in_(involved_team_ids))).all()
            if involved_team_ids
            else []
        )
    }
    pool_lookup = pool_lookup_for_league(db, league)
    owner_by_team_id = owner_by_team_id_for_league(db, league)
    match_ids = [m.id for m in matches]
    events = (
        list(
            db.scalars(
                select(ScoringEvent).where(
                    ScoringEvent.league_id == league.id,
                    ScoringEvent.team_id.in_(owned_team_ids),
                    ScoringEvent.match_id.in_(match_ids),
                )
            ).all()
        )
        if match_ids
        else []
    )
    points_by_match_team = match_stats_service.points_by_match_team(events)

    rows: list[TeamFixtureRow] = []
    for match in matches:
        # Club filter: focus that club when it plays (including as away in a derby).
        # Otherwise one row per fixture, preferring the home owned club.
        if focus_club_id is not None:
            if match.home_team_id == focus_club_id:
                focus_id = match.home_team_id
            elif match.away_team_id == focus_club_id:
                focus_id = match.away_team_id
            else:
                continue
        elif match.home_team_id in owned_team_ids:
            focus_id = match.home_team_id
        elif match.away_team_id in owned_team_ids:
            focus_id = match.away_team_id
        else:
            continue
        opponent_id = (
            match.away_team_id if match.home_team_id == focus_id else match.home_team_id
        )
        if opponent_team_ids is not None and opponent_id not in opponent_team_ids:
            continue
        is_finished = match.status in _FINISHED
        intra_roster = opponent_id in owned_team_ids
        if is_finished:
            if intra_roster:
                points = (
                    points_by_match_team.get((match.id, match.home_team_id), 0.0)
                    + points_by_match_team.get((match.id, match.away_team_id), 0.0)
                )
            else:
                points = points_by_match_team.get((match.id, focus_id))
        else:
            points = None
        row = _fixture_row(
            match=match,
            team_id=focus_id,
            teams=teams,
            pool=pool_for_match(db, league, match, lookup=pool_lookup),
            points=points,
            # Same-owner derbies still expose opponent_owner when filtering by that
            # manager so the Opponent filter stays consistent with the row payload.
            opponent_owner=owner_by_team_id.get(opponent_id)
            if (intra_roster and opponent_member_id is not None)
            else (None if intra_roster else owner_by_team_id.get(opponent_id)),
        )
        if row is not None:
            rows.append(row)

    return TeamFixturePage(items=rows, has_more=has_more)


def _team_fixture_page(
    db: Session,
    league: League,
    team: Team,
    *,
    section: str,
    limit: int,
    offset: int,
    opponent_member_id: UUID | None = None,
) -> TeamFixturePage:
    opponent_team_ids: set[int] | None = None
    if opponent_member_id is not None:
        opponent_member = _resolve_member(db, league, opponent_member_id)
        opponent_team_ids = team_ids_for_member(
            db, league_id=league.id, member_id=opponent_member.id
        )
        if not opponent_team_ids:
            return TeamFixturePage(items=[], has_more=False)

    keys = _league_competition_keys(db, league)
    if not keys:
        return TeamFixturePage(items=[], has_more=False)

    filters: list[Any] = [
        or_(Match.home_team_id == team.id, Match.away_team_id == team.id),
    ]
    if section == "recent":
        filters.append(Match.status.in_(list(_FINISHED)))
    else:
        filters.append(Match.status.notin_(list(_FINISHED)))
    if opponent_team_ids is not None:
        filters.append(
            or_(
                and_(
                    Match.home_team_id == team.id,
                    Match.away_team_id.in_(opponent_team_ids),
                ),
                and_(
                    Match.away_team_id == team.id,
                    Match.home_team_id.in_(opponent_team_ids),
                ),
            )
        )

    matches, has_more = paginate_matches(
        db,
        keys=keys,
        limit=limit,
        offset=offset,
        filters=filters,
        order="kickoff_asc" if section == "upcoming" else "kickoff_desc",
    )

    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches} | {
        team.id
    }
    teams = {
        t.id: t
        for t in (
            db.scalars(select(Team).where(Team.id.in_(team_ids))).all() if team_ids else []
        )
    }
    pool_lookup = pool_lookup_for_league(db, league)
    owner_by_team_id = owner_by_team_id_for_league(db, league)
    match_ids = [m.id for m in matches]
    events = (
        list(
            db.scalars(
                select(ScoringEvent).where(
                    ScoringEvent.league_id == league.id,
                    ScoringEvent.team_id == team.id,
                    ScoringEvent.match_id.in_(match_ids),
                )
            ).all()
        )
        if match_ids
        else []
    )
    points_by_match: dict[int, float] = {}
    for event in events:
        points_by_match[event.match_id] = points_by_match.get(event.match_id, 0.0) + float(
            event.points
        )

    pool_link = db.scalars(
        select(PoolTeam)
        .join(TeamPool, TeamPool.id == PoolTeam.pool_id)
        .where(PoolTeam.team_id == team.id, TeamPool.league_id == league.id)
    ).first()
    pool = db.get(TeamPool, pool_link.pool_id) if pool_link else None
    table_by_team: dict[int, Any] = {}
    if pool is not None:
        table_by_team = match_stats_service.current_table_for_pool(db, pool=pool, league=league)

    rows: list[TeamFixtureRow] = []
    for match in matches:
        finished = match.status in _FINISHED
        opponent_id = (
            match.away_team_id if match.home_team_id == team.id else match.home_team_id
        )
        if opponent_team_ids is not None and opponent_id not in opponent_team_ids:
            continue
        opp_pos = (table_by_team.get(opponent_id) or {}).get("table_position")
        row = _fixture_row(
            match=match,
            team_id=team.id,
            teams=teams,
            pool=pool_for_match(db, league, match, lookup=pool_lookup),
            points=points_by_match.get(match.id) if finished else None,
            opponent_table_position=opp_pos,
            opponent_owner=owner_by_team_id.get(opponent_id),
        )
        if row is not None:
            rows.append(row)

    return TeamFixturePage(items=rows, has_more=has_more)


@router.get(
    "/leagues/{league_id}/members/{member_id}/fixtures",
    response_model=TeamFixturePage,
)
def member_fixtures(
    member_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
    section: str = Query(default="recent", pattern="^(recent|upcoming)$"),
    limit: int = Query(default=5, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    club_id: UUID | None = None,
    opponent_member_id: UUID | None = None,
) -> TeamFixturePage:
    league, _ = membership
    member = _resolve_member(db, league, member_id)
    return _member_fixture_page(
        db,
        league,
        member,
        section=section,
        limit=limit,
        offset=offset,
        club_id=club_id,
        opponent_member_id=opponent_member_id,
    )


@router.get(
    "/leagues/{league_id}/teams/{team_id}/fixtures",
    response_model=TeamFixturePage,
)
def team_fixtures(
    team_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
    section: str = Query(default="recent", pattern="^(recent|upcoming)$"),
    limit: int = Query(default=5, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    opponent_member_id: UUID | None = None,
) -> TeamFixturePage:
    league, _ = membership
    team = team_in_league(db, league.id, team_id)
    return _team_fixture_page(
        db,
        league,
        team,
        section=section,
        limit=limit,
        offset=offset,
        opponent_member_id=opponent_member_id,
    )


@router.get("/leagues/{league_id}/members/{member_id}", response_model=MemberDetailResponse)
def member_detail(
    member_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> MemberDetailResponse:
    league, _ = membership
    member = _resolve_member(db, league, member_id)
    profile = db.get(Profile, member.profile_id)

    standings = analytics_service.leaderboard(db, league, phase_key=None)
    standing = next((row for row in standings if row.get("member_id") == str(member.public_id)), None)

    roster_entries = roster_entries_for_member(
        db, league_id=league.id, member_id=member.id
    )
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

    event_points, event_counts, total_points = match_stats_service.aggregate_event_points(
        events
    )
    points_by_team: dict[int, float] = {}
    for event in events:
        points_by_team[event.team_id] = points_by_team.get(event.team_id, 0.0) + float(
            event.points
        )

    bonus_conditions = [ManualBonus.member_id == member.id]
    if team_ids:
        bonus_conditions.append(ManualBonus.team_id.in_(team_ids))
    bonuses = list(
        db.scalars(
            select(ManualBonus)
            .where(
                ManualBonus.league_id == league.id,
                or_(*bonus_conditions),
            )
            .order_by(ManualBonus.created_at.desc())
        ).all()
    )
    bonus_types, bonus_teams, bonus_matches = load_bonus_context(
        db, league.id, bonuses, known_teams=teams
    )
    acc = accumulate_bonus_awards(
        bonuses,
        bonus_types=bonus_types,
        teams=bonus_teams,
        matches=bonus_matches,
        points_by_team=points_by_team,
    )
    bonus_points = acc.bonus_points
    bonus_by_type = acc.bonus_by_type
    awarded_bonuses = acc.awarded
    total_points += bonus_points

    owned_team_ids = set(team_ids)
    member_matches = (
        [
            m
            for m in matches_for_league(db, league)
            if m.home_team_id in owned_team_ids or m.away_team_id in owned_team_ids
        ]
        if team_ids
        else []
    )
    member_matches.sort(key=lambda m: m.kickoff_at, reverse=True)
    finished = [m for m in member_matches if m.status in _FINISHED]
    games_by_team: dict[int, int] = {
        tid: match_stats_service.finished_games_for_team(finished, tid) for tid in team_ids
    }
    games_total_by_team: dict[int, int] = {
        tid: match_stats_service.scheduled_games_for_team(member_matches, tid)
        for tid in team_ids
    }

    clubs: list[MemberClubRow] = []
    pick_by_team = match_stats_service.draft_pick_numbers(db, league.id)
    for entry in roster_entries:
        team = teams.get(entry.team_id)
        if team is None:
            continue
        pool = pools.get(entry.pool_id)
        pts = points_by_team.get(team.id, 0.0)
        gp = games_by_team.get(team.id, 0)
        gt = games_total_by_team.get(team.id, 0)
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
                games_total=gt,
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
    upset_points = match_stats_service.sum_upset_points(event_points)
    games_played = int(wdl["games_played"])
    games_total = sum(games_total_by_team.values())

    matches_by_id = {m.id: m for m in member_matches}
    involved_team_ids = (
        {m.home_team_id for m in member_matches}
        | {m.away_team_id for m in member_matches}
        | owned_team_ids
    )
    for event in events:
        match = matches_by_id.get(event.match_id)
        if match:
            involved_team_ids.add(match.home_team_id)
            involved_team_ids.add(match.away_team_id)
    if involved_team_ids - set(teams):
        for t in db.scalars(select(Team).where(Team.id.in_(involved_team_ids))).all():
            teams[t.id] = t

    scoring_event_rows: list[ScoringEventMatchRow] = []
    for event in sorted(
        events,
        key=lambda e: (
            -(
                matches_by_id[e.match_id].kickoff_at.timestamp()
                if e.match_id in matches_by_id
                else 0
            ),
            e.event_type,
        ),
    ):
        match = matches_by_id.get(event.match_id)
        if match is None:
            match = db.get(Match, event.match_id)
            if match is None:
                continue
            matches_by_id[match.id] = match
        is_home = match.home_team_id == event.team_id
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

    return MemberDetailResponse(
        id=member.public_id,
        team_name=member.team_name,
        display_name=profile.display_name if profile else None,
        draft_slot=member.draft_slot,
        rank=int(standing["rank"]) if standing else None,
        stats={
            "total_points": float(standing["total_points"]) if standing else total_points,
            "games_played": games_played,
            "games_total": games_total,
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
        scoring_events=scoring_event_rows,
        # Fixtures are loaded via GET .../members/{id}/fixtures (paginated).
        recent_matches=[],
        upcoming_matches=[],
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

    owner_by_team_id = owner_by_team_id_for_league(db, league)
    owner = owner_by_team_id.get(team.id)

    events = db.scalars(
        select(ScoringEvent).where(
            ScoringEvent.league_id == league.id,
            ScoringEvent.team_id == team.id,
        )
    ).all()
    event_points, event_counts, total_points = match_stats_service.aggregate_event_points(
        events
    )
    points_by_match: dict[int, float] = {}
    for event in events:
        points_by_match[event.match_id] = points_by_match.get(event.match_id, 0.0) + float(
            event.points
        )
    points_by_stage = match_stats_service.points_by_stage_from_events(events)

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
    bonus_types, bonus_teams, bonus_matches = load_bonus_context(
        db, league.id, bonuses, known_teams={team.id: team}
    )
    acc = accumulate_bonus_awards(
        bonuses,
        bonus_types=bonus_types,
        teams=bonus_teams,
        matches=bonus_matches,
    )
    bonus_points = acc.bonus_points
    bonus_by_type = acc.bonus_by_type
    awarded_bonuses = acc.awarded
    total_points += bonus_points

    matches = [
        m
        for m in matches_for_league(db, league)
        if m.home_team_id == team.id or m.away_team_id == team.id
    ]
    matches.sort(key=lambda m: m.kickoff_at, reverse=True)
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

    table_by_team: dict[int, Any] = {}
    if pool is not None:
        table_by_team = match_stats_service.current_table_for_pool(db, pool=pool, league=league)

    team_results = match_stats_service.team_results_from_matches(matches, team.id)
    wdl = match_stats_service.wdl_from_results(team_results)
    goals = match_stats_service.goals_from_results(team_results)
    form = match_stats_service.form_from_results(team_results, limit=5)
    splits = match_stats_service.venue_split(team_results, points_by_match)
    table_row = table_by_team.get(team.id)

    next_three = _team_fixture_page(
        db, league, team, section="upcoming", limit=3, offset=0
    ).items
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
    upset_points = match_stats_service.sum_upset_points(event_points)
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
        # Fixtures are loaded via GET .../teams/{id}/fixtures (paginated).
        recent_matches=[],
        upcoming_matches=[],
    )


@router.get("/leagues/{league_id}/sync-status", response_model=list[SyncStatusResponse])
def sync_status(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> list[SyncStatusResponse]:
    league, _ = membership
    scoring_pools = scoring_pools_for_league(db, league)
    keys = competition_keys_from_pools(scoring_pools)
    if not keys:
        return []
    key_pred = competition_key_predicate_for(SyncStatus, keys)
    if key_pred is None:
        return []
    rows = db.scalars(select(SyncStatus).where(key_pred)).all()
    return [
        SyncStatusResponse(
            id=row.public_id,
            provider=row.provider,
            competition_code=row.competition_code,
            season_year=row.season_year,
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
    scoring_pools = scoring_pools_for_league(db, league)
    keys = competition_keys_from_pools(scoring_pools)
    if not keys:
        return []
    pool_by_key = pool_lookup_for_league(db, league, pools=scoring_pools)
    key_pred = competition_key_predicate_for(StandingsSnapshot, keys)
    if key_pred is None:
        return []
    snaps = db.scalars(
        select(StandingsSnapshot)
        .where(key_pred)
        .order_by(StandingsSnapshot.kickoff_at.desc())
    ).all()
    out: list[SnapshotAuditRow] = []
    for snap in snaps:
        pool = pool_by_key.get((snap.provider, snap.competition_code, snap.season_year))
        if pool is None:
            continue
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


