"""Shared league response mappers."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BonusType,
    CompetitionTemplate,
    League,
    LeagueMember,
    Profile,
    TeamPool,
)
from app.schemas.leagues import (
    LeagueDetailResponse,
    LeagueResponse,
    MemberResponse,
    PhaseResponse,
    PoolResponse,
)
from app.services.members import member_label

def _member_role(member: LeagueMember) -> str:
    return "commissioner" if member.is_commissioner else "member"


def _member_response(member: LeagueMember, profile: Profile | None) -> MemberResponse:
    return MemberResponse(
        id=member.public_id,
        is_commissioner=member.is_commissioner,
        draft_slot=member.draft_slot,
        profile_id=profile.public_id if profile else None,
        email=profile.email if profile else None,
        display_name=profile.display_name if profile else None,
        team_name=member.team_name,
        role=_member_role(member),
    )


def _max_members(league: League) -> int | None:
    config = league.config or {}
    if "max_members" not in config or config.get("max_members") is None:
        return None
    try:
        return max(2, int(config["max_members"]))
    except (TypeError, ValueError):
        return None


def _phases(league: League) -> list[PhaseResponse]:
    out: list[PhaseResponse] = []
    for phase in league.leaderboard_phases or []:
        mf = phase.get("match_filter") or {}
        matchweek_range = mf.get("matchweek_range") or phase.get("matchweek_range")
        if not matchweek_range and mf.get("type") == "matchweek_range":
            fr, to = mf.get("from"), mf.get("to")
            if fr is not None and to is not None:
                matchweek_range = [int(fr), int(to)]
        stage_in = mf.get("stages") or mf.get("stage_in") or phase.get("stage_in")
        out.append(
            PhaseResponse(
                key=str(phase.get("key", "")),
                name=str(phase.get("name") or phase.get("label") or phase.get("key") or ""),
                matchweek_range=matchweek_range,
                stage_in=stage_in,
                is_final=bool(phase.get("is_final", False)),
            )
        )
    return out


def _league_response(
    league: League,
    *,
    role: str | None = None,
    my_rank: int | None = None,
    member_count: int | None = None,
    my_points: float | None = None,
    my_draft_slot: int | None = None,
    has_scored: bool = False,
) -> LeagueResponse:
    template_public = None
    return LeagueResponse(
        id=league.public_id,
        name=league.name,
        season_label=league.season_label,
        status=league.status,
        draft_style=league.draft_style,
        preassign_mode=league.preassign_mode,
        result_points=league.result_points,
        upset_rules=league.upset_rules,
        leaderboard_phases=league.leaderboard_phases,
        leaderboard_tiebreaks=league.leaderboard_tiebreaks,
        buy_in=league.buy_in,
        payouts=league.payouts,
        scheduled_start_date=league.scheduled_start_date,
        scheduled_end_date=league.scheduled_end_date,
        template_id=template_public,
        max_members=_max_members(league),
        role=role,
        my_rank=my_rank,
        member_count=member_count,
        my_points=my_points,
        my_draft_slot=my_draft_slot,
        has_scored=has_scored,
    )


def _league_detail(
    db: Session,
    league: League,
    current: LeagueMember,
) -> LeagueDetailResponse:
    members = db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    pools = db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all()
    bonuses = db.scalars(select(BonusType).where(BonusType.league_id == league.id)).all()
    template_id = None
    if league.template_id:
        template = db.get(CompetitionTemplate, league.template_id)
        template_id = template.public_id if template else None
    member_rows = []
    for member in members:
        profile = db.get(Profile, member.profile_id)
        member_rows.append(_member_response(member, profile))
    max_members = _max_members(league)
    return LeagueDetailResponse(
        id=league.public_id,
        name=league.name,
        season_label=league.season_label,
        status=league.status,
        draft_style=league.draft_style,
        preassign_mode=league.preassign_mode,
        result_points=league.result_points,
        upset_rules=league.upset_rules,
        leaderboard_phases=league.leaderboard_phases,
        leaderboard_tiebreaks=league.leaderboard_tiebreaks,
        buy_in=league.buy_in,
        payouts=league.payouts,
        scheduled_start_date=league.scheduled_start_date,
        scheduled_end_date=league.scheduled_end_date,
        template_id=template_id,
        max_members=max_members,
        current_member_id=current.public_id,
        role=_member_role(current),
        settings={
            "draft_style": league.draft_style,
            "preassign_mode": league.preassign_mode,
            "result_points": league.result_points,
            "upset_rules": league.upset_rules,
            "format": league.draft_style,
            "max_members": max_members,
        },
        members=member_rows,
        pools=[
            PoolResponse(
                id=p.public_id,
                key=p.key,
                label=p.label,
                scores_match_results=p.scores_match_results,
                slot_count=p.slot_count,
                sort_order=int(getattr(p, "sort_order", 0) or 0),
                provider=p.provider,
                competition_code=p.competition_code,
                season_year=p.season_year,
                tie_break_order=list(p.tie_break_order or []),
            )
            for p in sorted(
                pools,
                key=lambda pool: (int(getattr(pool, "sort_order", 0) or 0), pool.label, pool.id),
            )
        ],
        phases=_phases(league),
        bonus_type_keys=[b.key for b in bonuses],
        provider_params={
            p.key: {
                "provider": p.provider,
                "competition_code": p.competition_code,
                "season_year": p.season_year,
            }
            for p in pools
        },
    )


