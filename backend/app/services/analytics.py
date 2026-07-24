"""Analytics rollups over scoring_events + roster ownership."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import League, LeagueMember, ManualBonus, Match, RosterEntry, ScoringEvent, Team
from app.services.scoring import (
    MemberPoints,
    match_passes_phase_filter,
    rank_leaderboard,
)


def _phase_filter(league: League, phase_key: str | None) -> dict[str, Any] | None:
    if not phase_key:
        return None
    for phase in league.leaderboard_phases or []:
        if phase.get("key") == phase_key:
            return phase.get("match_filter")
    raise ValueError(f"unknown phase key: {phase_key}")


def leaderboard(
    db: Session,
    league: League,
    *,
    phase_key: str | None = None,
) -> list[dict[str, Any]]:
    match_filter = _phase_filter(league, phase_key)
    roster = {
        r.team_id: r.member_id
        for r in db.scalars(
            select(RosterEntry).where(RosterEntry.league_id == league.id)
        ).all()
    }
    events = db.scalars(
        select(ScoringEvent).where(ScoringEvent.league_id == league.id)
    ).all()

    event_points: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal(0)))
    event_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[int, Decimal] = defaultdict(lambda: Decimal(0))

    for event in events:
        member_id = roster.get(event.team_id)
        if member_id is None:
            continue
        if not match_passes_phase_filter(
            scheduled_matchweek=event.scheduled_matchweek,
            stage=event.stage,
            match_filter=match_filter,
        ):
            continue
        pts = Decimal(event.points)
        totals[member_id] += pts
        event_points[member_id][event.event_type] += pts
        event_counts[member_id][event.event_type] += 1

    # Manual bonuses: season total only unless phase includes them
    include_bonuses: set[str] = set()
    if phase_key:
        for phase in league.leaderboard_phases or []:
            if phase.get("key") == phase_key:
                include_bonuses = set(phase.get("include_bonus_types") or [])
                break
    else:
        include_bonuses = {"*"}

    bonus_points: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal(0)))
    bonus_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    if include_bonuses:
        from app.models import BonusType

        bonuses = db.scalars(
            select(ManualBonus).where(ManualBonus.league_id == league.id)
        ).all()
        types = {
            bt.id: bt
            for bt in db.scalars(select(BonusType).where(BonusType.league_id == league.id)).all()
        }
        for bonus in bonuses:
            member_id = roster.get(bonus.team_id)
            if member_id is None:
                continue
            bt = types.get(bonus.bonus_type_id)
            if bt is None:
                continue
            if "*" not in include_bonuses and bt.key not in include_bonuses:
                continue
            pts = Decimal(bonus.points)
            totals[member_id] += pts
            bonus_points[member_id][bt.key] += pts
            bonus_counts[member_id][bt.key] += 1

    members = db.scalars(
        select(LeagueMember).where(LeagueMember.league_id == league.id)
    ).all()
    member_points = [
        MemberPoints(
            member_id=m.id,
            total_points=totals.get(m.id, Decimal(0)),
            event_points_by_type=dict(event_points.get(m.id, {})),
            event_counts_by_type=dict(event_counts.get(m.id, {})),
            bonus_points_by_type=dict(bonus_points.get(m.id, {})),
            bonus_counts_by_type=dict(bonus_counts.get(m.id, {})),
        )
        for m in members
    ]
    ranked = rank_leaderboard(member_points, league.leaderboard_tiebreaks or [{"metric": "total_points"}])
    public_by_id = {m.id: m for m in members}
    return [
        {
            "rank": entry.rank,
            "member_id": str(public_by_id[entry.member_id].public_id),
            "total_points": float(entry.total_points),
            "rung_values": [float(v) if isinstance(v, Decimal) else v for v in entry.rung_values],
        }
        for entry in ranked
        if entry.member_id in public_by_id
    ]


def points_per_game(
    db: Session,
    league: League,
    *,
    member_public_id: UUID | None = None,
) -> list[dict[str, Any]]:
    roster_q = select(RosterEntry).where(RosterEntry.league_id == league.id)
    if member_public_id:
        member = db.scalars(
            select(LeagueMember).where(LeagueMember.public_id == member_public_id)
        ).first()
        if member is None:
            return []
        roster_q = roster_q.where(RosterEntry.member_id == member.id)
    roster = list(db.scalars(roster_q).all())
    results: list[dict[str, Any]] = []
    for entry in roster:
        team = db.get(Team, entry.team_id)
        events = db.scalars(
            select(ScoringEvent).where(
                ScoringEvent.league_id == league.id,
                ScoringEvent.team_id == entry.team_id,
            )
        ).all()
        points = sum((Decimal(e.points) for e in events), Decimal(0))
        games = db.scalars(
            select(Match).where(
                Match.league_id == league.id,
                Match.status.in_(("FINISHED", "AWARDED")),
                ((Match.home_team_id == entry.team_id) | (Match.away_team_id == entry.team_id)),
            )
        ).all()
        gp = len(games)
        results.append(
            {
                "team_id": str(team.public_id) if team else None,
                "team_name": team.name if team else None,
                "member_id": str(
                    db.get(LeagueMember, entry.member_id).public_id  # type: ignore[union-attr]
                ),
                "points": float(points),
                "games_played": gp,
                "points_per_game": float(points / gp) if gp else 0.0,
            }
        )
    return results


def matchweek_breakdown(db: Session, league: League) -> list[dict[str, Any]]:
    roster = {
        r.team_id: r.member_id
        for r in db.scalars(select(RosterEntry).where(RosterEntry.league_id == league.id)).all()
    }
    members = {
        m.id: m
        for m in db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    }
    buckets: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal(0))
    for event in db.scalars(select(ScoringEvent).where(ScoringEvent.league_id == league.id)).all():
        if event.scheduled_matchweek is None:
            continue
        member_id = roster.get(event.team_id)
        if member_id is None:
            continue
        buckets[(member_id, event.scheduled_matchweek)] += Decimal(event.points)

    rows = []
    for (member_id, mw), pts in sorted(buckets.items(), key=lambda x: (x[0][1], x[0][0])):
        member = members.get(member_id)
        if not member:
            continue
        rows.append(
            {
                "member_id": str(member.public_id),
                "scheduled_matchweek": mw,
                "points": float(pts),
            }
        )
    return rows


def upset_stats(db: Session, league: League) -> list[dict[str, Any]]:
    roster = {
        r.team_id: r.member_id
        for r in db.scalars(select(RosterEntry).where(RosterEntry.league_id == league.id)).all()
    }
    members = {
        m.id: m
        for m in db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    }
    upset_types = {"minor_upset", "major_upset", "major_upset_draw"}
    stats: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "points": Decimal(0), "by_type": defaultdict(lambda: Decimal(0))}
    )
    for event in db.scalars(select(ScoringEvent).where(ScoringEvent.league_id == league.id)).all():
        if event.event_type not in upset_types:
            continue
        member_id = roster.get(event.team_id)
        if member_id is None:
            continue
        stats[member_id]["count"] += 1
        stats[member_id]["points"] += Decimal(event.points)
        stats[member_id]["by_type"][event.event_type] += Decimal(event.points)

    return [
        {
            "member_id": str(members[mid].public_id),
            "upset_count": data["count"],
            "upset_points": float(data["points"]),
            "by_type": {k: float(v) for k, v in data["by_type"].items()},
        }
        for mid, data in stats.items()
        if mid in members
    ]
