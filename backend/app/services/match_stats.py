"""Match-derived club/member stats (WDL, form, goals, home/away splits)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Literal, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DraftPick,
    League,
    LeagueMember,
    Match,
    Profile,
    RosterEntry,
    ScoringEvent,
    Team,
    TeamPool,
)
from app.services.match_adapters import match_to_input
from app.services.match_queries import (
    FINISHED_STATUSES,
    matches_for_league,
    matches_for_pool,
)
from app.services.members import member_label
from app.services.period_labels import (
    build_period_catalog,
    events_by_competition_type,
    expanded_stages,
    period_kind,
    resolve_period_key,
    scoring_competition_type,
)
from app.services.scoring import Result, build_standings_before_kickoff, result_for
from app.services.standings import (
    DEFAULT_TIEBREAKS,
    FOOTBALL_TABLE_POINTS,
    initial_rows_for_competition,
)

FINISHED = FINISHED_STATUSES
# Fallback when a league has no threshold keys configured yet.
DEFAULT_UPSET_TYPES = frozenset({"minor_upset", "major_upset", "major_upset_draw"})
UPSET_TYPES = DEFAULT_UPSET_TYPES
ResultLetter = Literal["W", "D", "L"]


def upset_types_for_league(league: League | None) -> frozenset[str]:
    """Event-type keys that count as upsets for this league's thresholds."""
    rules = (getattr(league, "upset_rules", None) if league is not None else None) or {}
    keys = {
        str(item.get("key"))
        for item in (rules.get("thresholds") or [])
        if isinstance(item, dict) and item.get("key")
    }
    return frozenset(keys) if keys else DEFAULT_UPSET_TYPES


def points_by_match_team(events: Iterable[Any]) -> dict[tuple[int, int], float]:
    """Fold scoring events into (match_id, team_id) → points."""
    out: dict[tuple[int, int], float] = {}
    for event in events:
        key = (event.match_id, event.team_id)
        out[key] = out.get(key, 0.0) + float(event.points)
    return out


def aggregate_event_points(
    events: Iterable[Any],
) -> tuple[dict[str, float], dict[str, int], float]:
    """Return (points_by_type, counts_by_type, total_points)."""
    event_points: dict[str, float] = {}
    event_counts: dict[str, int] = {}
    total = 0.0
    for event in events:
        pts = float(event.points)
        total += pts
        event_points[event.event_type] = event_points.get(event.event_type, 0.0) + pts
        event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
    return event_points, event_counts, total


def sum_upset_points(
    event_points: dict[str, float],
    upset_types: frozenset[str] | None = None,
) -> float:
    types = upset_types if upset_types is not None else DEFAULT_UPSET_TYPES
    return float(sum(event_points.get(t, 0.0) for t in types))


@dataclass(frozen=True)
class TeamMatchResult:
    match_id: int
    match_public_id: UUID
    kickoff_at: datetime
    scheduled_matchweek: int | None
    is_home: bool
    goals_for: int
    goals_against: int
    result: Result
    letter: ResultLetter
    opponent_team_id: int


def letter_for(result: Result) -> ResultLetter:
    if result is Result.WIN:
        return "W"
    if result is Result.DRAW:
        return "D"
    return "L"


def team_results_from_matches(
    matches: Sequence[Match],
    team_id: int,
) -> list[TeamMatchResult]:
    out: list[TeamMatchResult] = []
    for match in matches:
        if match.status not in FINISHED:
            continue
        if match.home_goals is None or match.away_goals is None:
            continue
        if match.home_team_id == team_id:
            gf, ga = match.home_goals, match.away_goals
            is_home = True
            opponent = match.away_team_id
        elif match.away_team_id == team_id:
            gf, ga = match.away_goals, match.home_goals
            is_home = False
            opponent = match.home_team_id
        else:
            continue
        result = result_for(gf, ga)
        out.append(
            TeamMatchResult(
                match_id=match.id,
                match_public_id=match.public_id,
                kickoff_at=match.kickoff_at,
                scheduled_matchweek=match.scheduled_matchweek,
                is_home=is_home,
                goals_for=gf,
                goals_against=ga,
                result=result,
                letter=letter_for(result),
                opponent_team_id=opponent,
            )
        )
    out.sort(key=lambda r: (r.kickoff_at, r.match_id))
    return out


def finished_games_for_team(matches: Sequence[Match], team_id: int) -> int:
    """Games played with recorded goals (same rule as club/PPG stats)."""
    return len(team_results_from_matches(matches, team_id))


def scheduled_games_for_team(matches: Sequence[Match], team_id: int) -> int:
    """All fixtures involving the team (finished + remaining)."""
    return sum(
        1 for m in matches if m.home_team_id == team_id or m.away_team_id == team_id
    )


def wdl_from_results(results: Sequence[TeamMatchResult]) -> dict[str, int]:
    wins = draws = losses = 0
    for row in results:
        if row.result is Result.WIN:
            wins += 1
        elif row.result is Result.DRAW:
            draws += 1
        else:
            losses += 1
    return {"wins": wins, "draws": draws, "losses": losses, "games_played": len(results)}


def goals_from_results(results: Sequence[TeamMatchResult]) -> dict[str, int]:
    gf = sum(r.goals_for for r in results)
    ga = sum(r.goals_against for r in results)
    return {"goals_for": gf, "goals_against": ga, "goal_difference": gf - ga}


def form_from_results(results: Sequence[TeamMatchResult], *, limit: int = 5) -> dict[str, Any]:
    recent = list(results[-limit:]) if limit else list(results)
    letters = [r.letter for r in recent]
    streak_letter: ResultLetter | None = None
    streak_count = 0
    if results:
        streak_letter = results[-1].letter
        for row in reversed(results):
            if row.letter != streak_letter:
                break
            streak_count += 1
    return {
        "form": letters,
        "current_streak": {"result": streak_letter, "count": streak_count} if streak_letter else None,
    }


def venue_split(
    results: Sequence[TeamMatchResult],
    points_by_match: dict[int, float] | None = None,
) -> dict[str, Any]:
    points_by_match = points_by_match or {}

    def bucket(rows: Sequence[TeamMatchResult]) -> dict[str, Any]:
        wdl = wdl_from_results(rows)
        pts = sum(points_by_match.get(r.match_id, 0.0) for r in rows)
        gp = wdl["games_played"]
        return {
            **wdl,
            "points": pts,
            "points_per_game": (pts / gp) if gp else 0.0,
        }

    home = [r for r in results if r.is_home]
    away = [r for r in results if not r.is_home]
    return {"home": bucket(home), "away": bucket(away)}


def current_table_for_pool(
    db: Session,
    *,
    pool: TeamPool,
    league: League,
) -> dict[int, Any]:
    """Live competition table including all finished matches for the pool's season."""
    if not pool.competition_code or not pool.season_year:
        return {}
    matches = [
        match_to_input(m, pool_id=pool.id) for m in matches_for_pool(db, pool)
    ]
    finished = [m for m in matches if m.status in FINISHED]
    far_future = datetime(9999, 1, 1, tzinfo=UTC)
    ranked = build_standings_before_kickoff(
        team_rows=initial_rows_for_competition(
            db,
            provider=pool.provider,
            competition_code=pool.competition_code,
            season_year=pool.season_year,
        ),
        finished_matches=finished,
        kickoff_at=far_future,
        pool_id=pool.id,
        result_points=FOOTBALL_TABLE_POINTS,
        tiebreaks=DEFAULT_TIEBREAKS,
    )
    return {
        row.team_id: {
            "table_position": row.rank,
            "played": row.played,
            "table_points": row.points,
            "goals_for": row.goals_for,
            "goals_against": row.goals_against,
            "goal_difference": row.goal_difference,
        }
        for row in ranked
    }


def aggregate_member_wdl(
    matches: Sequence[Match],
    team_ids: Iterable[int],
) -> dict[str, int]:
    team_set = set(team_ids)
    wins = draws = losses = 0
    games = 0
    for team_id in team_set:
        for row in team_results_from_matches(matches, team_id):
            games += 1
            if row.result is Result.WIN:
                wins += 1
            elif row.result is Result.DRAW:
                draws += 1
            else:
                losses += 1
    return {"wins": wins, "draws": draws, "losses": losses, "games_played": games}


def form_stats(
    db: Session,
    league: League,
    *,
    member_public_id: UUID | None = None,
    team_public_id: UUID | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    roster = list(db.scalars(select(RosterEntry).where(RosterEntry.league_id == league.id)).all())
    if member_public_id:
        member = db.scalars(
            select(LeagueMember).where(
                LeagueMember.public_id == member_public_id,
                LeagueMember.league_id == league.id,
            )
        ).first()
        if member is None:
            return []
        roster = [r for r in roster if r.member_id == member.id]
    if team_public_id:
        team = db.scalars(select(Team).where(Team.public_id == team_public_id)).first()
        if team is None:
            return []
        roster = [r for r in roster if r.team_id == team.id]

    team_ids = {r.team_id for r in roster}
    if not team_ids:
        return []
    matches = [
        m
        for m in matches_for_league(db, league)
        if m.home_team_id in team_ids or m.away_team_id in team_ids
    ]
    members = {
        m.id: m
        for m in db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    }
    teams = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()}
    out: list[dict[str, Any]] = []
    for entry in roster:
        team = teams.get(entry.team_id)
        member = members.get(entry.member_id)
        if not team or not member:
            continue
        results = team_results_from_matches(matches, entry.team_id)
        form = form_from_results(results, limit=limit)
        profile = db.get(Profile, member.profile_id)
        out.append(
            {
                "team_id": str(team.public_id),
                "team_name": team.name,
                "member_id": str(member.public_id),
                "display_name": member_label(member, profile),
                **form,
                **wdl_from_results(results),
            }
        )
    return out


def venue_splits(
    db: Session,
    league: League,
    *,
    member_public_id: UUID | None = None,
) -> list[dict[str, Any]]:
    roster_q = select(RosterEntry).where(RosterEntry.league_id == league.id)
    member: LeagueMember | None = None
    if member_public_id:
        member = db.scalars(
            select(LeagueMember).where(
                LeagueMember.public_id == member_public_id,
                LeagueMember.league_id == league.id,
            )
        ).first()
        if member is None:
            return []
        roster_q = roster_q.where(RosterEntry.member_id == member.id)
    roster = list(db.scalars(roster_q).all())
    team_ids = {r.team_id for r in roster}
    if not team_ids:
        return []

    matches = [
        m
        for m in matches_for_league(db, league)
        if m.home_team_id in team_ids or m.away_team_id in team_ids
    ]
    events = list(
        db.scalars(
            select(ScoringEvent).where(
                ScoringEvent.league_id == league.id,
                ScoringEvent.team_id.in_(team_ids),
            )
        ).all()
    )
    points_by_team_match: dict[tuple[int, int], float] = defaultdict(float)
    for event in events:
        points_by_team_match[(event.team_id, event.match_id)] += float(event.points)

    members = {
        m.id: m
        for m in db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    }
    teams = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()}

    # Per-member rollup when filtering by member; else per-team rows.
    if member_public_id and member is not None:
        all_results: list[TeamMatchResult] = []
        points_by_match: dict[int, float] = defaultdict(float)
        for entry in roster:
            results = team_results_from_matches(matches, entry.team_id)
            all_results.extend(results)
            for r in results:
                points_by_match[r.match_id] += points_by_team_match.get((entry.team_id, r.match_id), 0.0)
        profile = db.get(Profile, member.profile_id)
        return [
            {
                "member_id": str(member.public_id),
                "display_name": member_label(member, profile),
                "team_id": None,
                "team_name": None,
                **venue_split(all_results, points_by_match),
            }
        ]

    out: list[dict[str, Any]] = []
    for entry in roster:
        team = teams.get(entry.team_id)
        mem = members.get(entry.member_id)
        if not team or not mem:
            continue
        results = team_results_from_matches(matches, entry.team_id)
        pts = {
            r.match_id: points_by_team_match.get((entry.team_id, r.match_id), 0.0) for r in results
        }
        profile = db.get(Profile, mem.profile_id)
        out.append(
            {
                "member_id": str(mem.public_id),
                "display_name": member_label(mem, profile),
                "team_id": str(team.public_id),
                "team_name": team.name,
                **venue_split(results, pts),
            }
        )
    return out


def member_highlights(
    db: Session,
    league: League,
    *,
    member_public_id: UUID,
) -> dict[str, Any]:
    member = db.scalars(
        select(LeagueMember).where(
            LeagueMember.public_id == member_public_id,
            LeagueMember.league_id == league.id,
        )
    ).first()
    if member is None:
        return {}
    roster = list(
        db.scalars(
            select(RosterEntry).where(
                RosterEntry.league_id == league.id,
                RosterEntry.member_id == member.id,
            )
        ).all()
    )
    team_ids = [r.team_id for r in roster]
    profile = db.get(Profile, member.profile_id)

    empty = {
        "member_id": str(member.public_id),
        "display_name": member_label(member, profile),
        "best_matchweek": None,
        "worst_matchweek": None,
        "biggest_upset": None,
        "top_club": None,
        "period_kind": None,
    }
    if not team_ids:
        return empty

    pools = list(db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all())
    competition_type = scoring_competition_type(pools)
    kind = period_kind(competition_type)
    empty["period_kind"] = kind

    events = list(
        db.scalars(
            select(ScoringEvent).where(
                ScoringEvent.league_id == league.id,
                ScoringEvent.team_id.in_(team_ids),
            )
        ).all()
    )
    match_ids = {e.match_id for e in events}
    matches_by_id = {
        m.id: m
        for m in db.scalars(select(Match).where(Match.id.in_(match_ids))).all()
    } if match_ids else {}
    opp_ids: set[int] = set()
    for event in events:
        match = matches_by_id.get(event.match_id)
        if not match:
            continue
        opp_ids.add(
            match.away_team_id if match.home_team_id == event.team_id else match.home_team_id
        )
    all_team_ids = set(team_ids) | opp_ids
    teams = {
        t.id: t for t in db.scalars(select(Team).where(Team.id.in_(all_team_ids))).all()
    } if all_team_ids else {}

    period_defs: dict[tuple[int, str], Any] = {}
    period_points: dict[tuple[int, str], float] = defaultdict(float)
    team_points: dict[int, float] = defaultdict(float)
    biggest_upset: dict[str, Any] | None = None
    upset_types = upset_types_for_league(league)
    for group_i, (_competition_code, event_competition_type, grouped_events) in enumerate(
        events_by_competition_type(events, matches_by_id, pools)
    ):
        catalog = build_period_catalog(
            [(e.stage, e.scheduled_matchweek) for e in grouped_events],
            competition_type=event_competition_type,
        )
        expanded = expanded_stages(catalog)
        by_key = {period.key: period for period in catalog}
        for period_key, period in by_key.items():
            period_defs[(group_i, period_key)] = period
        for event in grouped_events:
            pts = float(event.points)
            team_points[event.team_id] += pts
            period_key = resolve_period_key(
                event.stage, event.scheduled_matchweek, expanded=expanded
            )
            if period_key is not None and period_key in by_key:
                period_points[(group_i, period_key)] += pts
            if event.event_type in upset_types:
                meta = event.metadata_ or {}
                gap = meta.get("gap")
                candidate = {
                    "event_type": event.event_type,
                    "points": pts,
                    "gap": gap,
                    "match_id": None,
                    "team_id": (
                        str(teams[event.team_id].public_id)
                        if event.team_id in teams
                        else None
                    ),
                    "team_name": (
                        teams[event.team_id].name if event.team_id in teams else None
                    ),
                    "underdog_rank": meta.get("underdog_rank"),
                    "opponent_rank": meta.get("opponent_rank"),
                }
                match = matches_by_id.get(event.match_id)
                if match:
                    candidate["match_id"] = str(match.public_id)
                    opp_id = (
                        match.away_team_id
                        if match.home_team_id == event.team_id
                        else match.home_team_id
                    )
                    opp = teams.get(opp_id)
                    candidate["opponent_name"] = opp.name if opp else None
                if biggest_upset is None:
                    biggest_upset = candidate
                else:
                    prev_gap = biggest_upset.get("gap")
                    if gap is not None and (prev_gap is None or gap > prev_gap):
                        biggest_upset = candidate
                    elif gap == prev_gap and pts > float(
                        biggest_upset.get("points") or 0
                    ):
                        biggest_upset = candidate

    def period_payload(
        key: tuple[int, str], points: float
    ) -> dict[str, Any]:
        period = period_defs[key]
        return {
            "period_key": period.key,
            "label": period.label,
            "stage": period.stage,
            "scheduled_matchweek": period.scheduled_matchweek,
            "points": points,
        }

    best_period = max(period_points.items(), key=lambda x: x[1]) if period_points else None
    worst_period = min(period_points.items(), key=lambda x: x[1]) if period_points else None
    top_team_id = max(team_points.items(), key=lambda x: x[1])[0] if team_points else None
    top_club = None
    if top_team_id is not None and top_team_id in teams:
        top_club = {
            "team_id": str(teams[top_team_id].public_id),
            "team_name": teams[top_team_id].name,
            "points": team_points[top_team_id],
        }

    return {
        "member_id": str(member.public_id),
        "display_name": member_label(member, profile),
        "best_matchweek": (
            period_payload(best_period[0], best_period[1]) if best_period else None
        ),
        "worst_matchweek": (
            period_payload(worst_period[0], worst_period[1]) if worst_period else None
        ),
        "biggest_upset": biggest_upset,
        "top_club": top_club,
        "period_kind": kind,
    }


def draft_pick_numbers(db: Session, league_id: int) -> dict[int, int]:
    """Map team_id → draft pick_number for the league."""
    picks = db.scalars(select(DraftPick).where(DraftPick.league_id == league_id)).all()
    return {p.team_id: p.pick_number for p in picks}


def points_by_stage_from_events(events: Sequence[Any]) -> dict[str, float]:
    """Sum fantasy points by match stage code (skips blank/null stages)."""
    out: dict[str, float] = {}
    for event in events:
        stage = (getattr(event, "stage", None) or "").strip()
        if not stage:
            continue
        out[stage] = out.get(stage, 0.0) + float(event.points)
    return out


def points_by_stage_by_team(events: Sequence[Any]) -> dict[int, dict[str, float]]:
    """Map team_id → {stage_code: points} from scoring events."""
    out: dict[int, dict[str, float]] = {}
    for event in events:
        stage = (getattr(event, "stage", None) or "").strip()
        if not stage:
            continue
        team_id = int(event.team_id)
        bucket = out.setdefault(team_id, {})
        bucket[stage] = bucket.get(stage, 0.0) + float(event.points)
    return out

