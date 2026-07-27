"""Analytics rollups over scoring_events + roster ownership."""

from __future__ import annotations

import logging
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
from app.services.match_queries import FINISHED_STATUSES, matches_for_league
from app.services.match_stats import UPSET_TYPES, finished_games_for_team, sum_upset_points
from app.services.members import member_label
from app.services.payouts import apply_payouts
from app.services.roster_owners import member_id_by_team_id_for_league
from app.services.scoring import (
    MemberPoints,
    match_passes_phase_filter,
    rank_leaderboard,
)

logger = logging.getLogger(__name__)


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
    roster = member_id_by_team_id_for_league(db, league)
    events = db.scalars(
        select(ScoringEvent).where(ScoringEvent.league_id == league.id)
    ).all()

    event_points: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal(0)))
    event_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[int, Decimal] = defaultdict(lambda: Decimal(0))
    orphan_events = 0

    for event in events:
        member_id = roster.get(event.team_id)
        if member_id is None:
            orphan_events += 1
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

    if orphan_events:
        logger.warning(
            "leaderboard orphan scoring events league_id=%s count=%s phase_key=%s",
            league.public_id,
            orphan_events,
            phase_key,
        )

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

        bonuses = list(
            db.scalars(select(ManualBonus).where(ManualBonus.league_id == league.id)).all()
        )
        types = {
            bt.id: bt
            for bt in db.scalars(select(BonusType).where(BonusType.league_id == league.id)).all()
        }
        match_ids = {b.match_id for b in bonuses if b.match_id is not None}
        matches_by_id = {
            m.id: m
            for m in db.scalars(select(Match).where(Match.id.in_(match_ids or [0]))).all()
        }
        for bonus in bonuses:
            if bonus.member_id is not None:
                member_id = bonus.member_id
            elif bonus.team_id is not None:
                member_id = roster.get(bonus.team_id)
            else:
                continue
            if member_id is None:
                continue
            bt = types.get(bonus.bonus_type_id)
            if bt is None:
                continue
            if "*" not in include_bonuses and bt.key not in include_bonuses:
                continue
            if bonus.match_id is not None:
                match = matches_by_id.get(bonus.match_id)
                if match is None:
                    continue
                if not match_passes_phase_filter(
                    scheduled_matchweek=match.scheduled_matchweek,
                    stage=match.stage,
                    match_filter=match_filter,
                ):
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
            upset = sum_upset_points(
                {k: float(v) for k, v in mp.event_points_by_type.items()}
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
    pool_by_match_id: dict[int, int] | None = None,
) -> dict[str, Any]:
    """Count matches in a phase slice for completeness / payout readiness."""
    matching = 0
    finished = 0
    for match in matches:
        if scoring_pool_ids is not None:
            pool_id = (
                pool_by_match_id.get(match.id)
                if pool_by_match_id is not None
                else getattr(match, "pool_id", None)
            )
            if pool_id not in scoring_pool_ids:
                continue
        if not match_passes_phase_filter(
            scheduled_matchweek=getattr(match, "scheduled_matchweek", None),
            stage=getattr(match, "stage", None),
            match_filter=match_filter,
        ):
            continue
        matching += 1
        if getattr(match, "status", None) in FINISHED_STATUSES:
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
    if not roster:
        return []

    team_ids = {e.team_id for e in roster}
    member_ids = {e.member_id for e in roster}
    teams = {
        t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()
    }
    members = {
        m.id: m
        for m in db.scalars(select(LeagueMember).where(LeagueMember.id.in_(member_ids))).all()
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
    all_matches = matches_for_league(db, league)
    events_by_team: dict[int, list[ScoringEvent]] = defaultdict(list)
    for event in db.scalars(
        select(ScoringEvent).where(
            ScoringEvent.league_id == league.id,
            ScoringEvent.team_id.in_(team_ids),
        )
    ).all():
        events_by_team[event.team_id].append(event)

    results: list[dict[str, Any]] = []
    for entry in roster:
        team = teams.get(entry.team_id)
        events = events_by_team.get(entry.team_id, [])
        points = sum((Decimal(e.points) for e in events), Decimal(0))
        gp = finished_games_for_team(all_matches, entry.team_id)
        member = members.get(entry.member_id)
        profile = profiles.get(member.profile_id) if member and member.profile_id else None
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
    roster = member_id_by_team_id_for_league(db, league)
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
    roster = member_id_by_team_id_for_league(db, league)
    members = {
        m.id: m
        for m in db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    }
    stats: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "points": Decimal(0), "by_type": defaultdict(lambda: Decimal(0))}
    )
    for event in db.scalars(select(ScoringEvent).where(ScoringEvent.league_id == league.id)).all():
        if event.event_type not in UPSET_TYPES:
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
