"""Analytics rollups over scoring_events + roster ownership."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    League,
    LeagueMember,
    ManualBonus,
    Match,
    Profile,
    RosterEntry,
    ScoringEvent,
    Team,
)
from app.services.members import member_label
from app.services.payouts import apply_payouts
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
    points_by_id = {m.member_id: m for m in member_points}
    profiles = {m.id: db.get(Profile, m.profile_id) for m in members}
    tiebreaks = league.leaderboard_tiebreaks or [{"metric": "total_points", "direction": "desc"}]
    entries = []
    for entry in ranked:
        member = public_by_id.get(entry.member_id)
        if member is None:
            continue
        profile = profiles.get(member.id)
        mp = points_by_id.get(entry.member_id)
        upset = 0.0
        win_count = 0
        if mp:
            upset = float(
                mp.event_points_by_type.get("minor_upset", 0)
                + mp.event_points_by_type.get("major_upset", 0)
                + mp.event_points_by_type.get("major_upset_draw", 0)
            )
            win_count = int(mp.event_counts_by_type.get("win", 0) or 0)
        metric_values = []
        for idx, rung in enumerate(tiebreaks):
            value = entry.rung_values[idx] if idx < len(entry.rung_values) else 0
            if isinstance(rung, dict):
                metric_values.append(
                    {**rung, "value": float(value) if isinstance(value, Decimal) else value}
                )
            else:
                metric_values.append(
                    {"metric": str(rung), "value": float(value) if isinstance(value, Decimal) else value}
                )
        entries.append(
            {
                "rank": entry.rank,
                "member_id": str(member.public_id),
                "display_name": member_label(member, profile),
                "team_name": member.team_name,
                "owner_name": (profile.display_name if profile else None) or None,
                "total_points": float(entry.total_points),
                "upset_points": upset,
                "win_count": win_count,
                "payout": 0,
                "metric_values": metric_values,
                "rung_values": [
                    float(v) if isinstance(v, Decimal) else v for v in entry.rung_values
                ],
            }
        )
    return apply_payouts(entries, league.payouts, phase_key)


def phase_match_counts(
    matches: list[Any],
    *,
    match_filter: dict[str, Any] | None,
    scoring_pool_ids: set[int] | None = None,
) -> dict[str, Any]:
    """Count matches in a phase slice for completeness / payout readiness."""
    finished_statuses = {"FINISHED", "AWARDED"}
    matching = 0
    finished = 0
    for match in matches:
        if scoring_pool_ids is not None and getattr(match, "pool_id", None) not in scoring_pool_ids:
            continue
        if not match_passes_phase_filter(
            scheduled_matchweek=getattr(match, "scheduled_matchweek", None),
            stage=getattr(match, "stage", None),
            match_filter=match_filter,
        ):
            continue
        matching += 1
        if getattr(match, "status", None) in finished_statuses:
            finished += 1
    remaining = matching - finished
    return {
        "matching_matches": matching,
        "finished_matches": finished,
        "remaining_matches": remaining,
        "is_final": matching > 0 and remaining == 0,
    }


def points_per_game(
    db: Session,
    league: League,
    *,
    member_public_id: UUID | None = None,
) -> list[dict[str, Any]]:
    roster_q = select(RosterEntry).where(RosterEntry.league_id == league.id)
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
        member = db.get(LeagueMember, entry.member_id)
        profile = db.get(Profile, member.profile_id) if member else None
        results.append(
            {
                "team_id": str(team.public_id) if team else None,
                "team_name": team.name if team else None,
                "member_id": str(member.public_id) if member else None,
                "display_name": member_label(member, profile) if member else None,
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
        profile = db.get(Profile, member.profile_id)
        rows.append(
            {
                "member_id": str(member.public_id),
                "display_name": member_label(member, profile),
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
            "display_name": member_label(
                members[mid],
                db.get(Profile, members[mid].profile_id),
            ),
            "count": data["count"],
            "points": float(data["points"]),
            "upset_count": data["count"],
            "upset_points": float(data["points"]),
            "by_type": {k: float(v) for k, v in data["by_type"].items()},
        }
        for mid, data in stats.items()
        if mid in members
    ]
