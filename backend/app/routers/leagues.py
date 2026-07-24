from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.db import get_db
from app.deps import require_commissioner, require_league_member
from app.models import (
    CompetitionTemplate,
    Invite,
    League,
    LeagueMember,
    Profile,
    RosterEntry,
    Team,
    TeamPool,
)
from app.schemas.leagues import (
    BootstrapSeasonRequest,
    DraftOrderUpdate,
    InviteCreate,
    InviteResponse,
    LeagueCreate,
    LeagueResponse,
    LeagueSettingsUpdate,
    MemberResponse,
    PreassignRequest,
)
from app.services.bootstrap import bootstrap_season, prior_leagues_blocking

router = APIRouter(tags=["leagues"])


def _league_response(league: League) -> LeagueResponse:
    return LeagueResponse.model_validate(league)


@router.get("/leagues", response_model=list[LeagueResponse])
def list_leagues(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> list[LeagueResponse]:
    memberships = db.scalars(
        select(LeagueMember).where(LeagueMember.profile_id == profile.id)
    ).all()
    league_ids = [m.league_id for m in memberships]
    if not league_ids:
        return []
    leagues = db.scalars(select(League).where(League.id.in_(league_ids))).all()
    return [_league_response(league) for league in leagues]


@router.post("/leagues", response_model=LeagueResponse)
def create_league(
    payload: LeagueCreate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> LeagueResponse:
    template = None
    if payload.template_id:
        template = db.scalars(
            select(CompetitionTemplate).where(
                CompetitionTemplate.public_id == payload.template_id
            )
        ).first()
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
    league = League(
        template_id=template.id if template else None,
        name=payload.name,
        season_label=payload.season_label,
        draft_style=payload.draft_style if not template else template.draft_style,
        preassign_mode=payload.preassign_mode if not template else template.preassign_mode,
        result_points=(template.result_points if template else {"win": 3, "draw": 1}),
        upset_rules=(template.upset_rules if template else {}),
        leaderboard_phases=(template.leaderboard_phases if template else []),
        leaderboard_tiebreaks=(
            template.leaderboard_tiebreaks
            if template
            else [{"metric": "total_points", "direction": "desc"}]
        ),
        buy_in=(template.buy_in if template else 0),
        payouts=(template.payouts if template else []),
    )
    db.add(league)
    db.flush()
    db.add(
        LeagueMember(
            league_id=league.id,
            profile_id=profile.id,
            is_commissioner=True,
            draft_slot=1,
        )
    )
    db.commit()
    db.refresh(league)
    return _league_response(league)


@router.get("/leagues/{league_id}", response_model=LeagueResponse)
def get_league(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
) -> LeagueResponse:
    league, _ = membership
    return _league_response(league)


@router.get("/leagues/{league_id}/members", response_model=list[MemberResponse])
def list_members(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[MemberResponse]:
    league, _ = membership
    members = db.scalars(
        select(LeagueMember).where(LeagueMember.league_id == league.id)
    ).all()
    out: list[MemberResponse] = []
    for member in members:
        profile = db.get(Profile, member.profile_id)
        out.append(
            MemberResponse(
                id=member.public_id,
                is_commissioner=member.is_commissioner,
                draft_slot=member.draft_slot,
                profile_id=profile.public_id if profile else None,
                email=profile.email if profile else None,
                display_name=profile.display_name if profile else None,
            )
        )
    return out


@router.get("/leagues/{league_id}/invites", response_model=list[InviteResponse])
def list_invites(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> list[InviteResponse]:
    league, _ = membership
    invites = db.scalars(select(Invite).where(Invite.league_id == league.id)).all()
    return [InviteResponse.model_validate(invite) for invite in invites]


@router.post("/leagues/{league_id}/invites", response_model=InviteResponse)
def create_invite(
    payload: InviteCreate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> InviteResponse:
    league, _ = membership
    invite = Invite(
        league_id=league.id,
        email=payload.email.strip().lower(),
        is_commissioner=payload.is_commissioner,
        draft_slot=payload.draft_slot,
        status="pending",
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return InviteResponse.model_validate(invite)


@router.delete("/leagues/{league_id}/invites/{invite_id}", status_code=204)
def revoke_invite(
    invite_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> None:
    league, _ = membership
    invite = db.scalars(
        select(Invite).where(
            Invite.public_id == invite_id,
            Invite.league_id == league.id,
        )
    ).first()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    invite.status = "revoked"
    db.commit()


@router.put("/leagues/{league_id}/draft-order", response_model=list[MemberResponse])
def set_draft_order(
    payload: DraftOrderUpdate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> list[MemberResponse]:
    league, _ = membership
    if league.status == "drafting":
        raise HTTPException(status_code=409, detail="Draft order locked once drafting")
    members = {
        m.public_id: m
        for m in db.scalars(
            select(LeagueMember).where(LeagueMember.league_id == league.id)
        ).all()
    }
    if set(payload.member_ids) != set(members):
        raise HTTPException(status_code=400, detail="member_ids must include every member exactly once")
    for index, mid in enumerate(payload.member_ids, start=1):
        members[mid].draft_slot = index
    db.commit()
    out: list[MemberResponse] = []
    for member in sorted(members.values(), key=lambda m: m.draft_slot or 0):
        profile = db.get(Profile, member.profile_id)
        out.append(
            MemberResponse(
                id=member.public_id,
                is_commissioner=member.is_commissioner,
                draft_slot=member.draft_slot,
                profile_id=profile.public_id if profile else None,
                email=profile.email if profile else None,
                display_name=profile.display_name if profile else None,
            )
        )
    return out


@router.post("/leagues/{league_id}/preassigns", status_code=201)
def preassign_team(
    payload: PreassignRequest,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    member = db.scalars(
        select(LeagueMember).where(
            LeagueMember.public_id == payload.member_id,
            LeagueMember.league_id == league.id,
        )
    ).first()
    team = db.scalars(select(Team).where(Team.public_id == payload.team_id)).first()
    pool = db.scalars(
        select(TeamPool).where(
            TeamPool.public_id == payload.pool_id,
            TeamPool.league_id == league.id,
        )
    ).first()
    if not member or not team or not pool:
        raise HTTPException(status_code=404, detail="member/team/pool not found")
    existing = db.scalars(
        select(RosterEntry).where(
            RosterEntry.league_id == league.id,
            RosterEntry.team_id == team.id,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Team already assigned")
    entry = RosterEntry(
        league_id=league.id,
        member_id=member.id,
        team_id=team.id,
        pool_id=pool.id,
        source="preassigned",
    )
    db.add(entry)
    db.commit()
    return {"id": str(entry.public_id)}


@router.patch("/leagues/{league_id}/settings", response_model=LeagueResponse)
def update_settings(
    payload: LeagueSettingsUpdate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> LeagueResponse:
    league, _ = membership
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(league, key, value)
    db.commit()
    db.refresh(league)
    return _league_response(league)


@router.get("/leagues/premier-league/bootstrap-gates")
def bootstrap_gates(
    _: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> dict:
    return {"blockers": prior_leagues_blocking(db, template_key="premier_league")}


@router.post("/leagues/premier-league/seasons", response_model=LeagueResponse)
def start_pl_season(
    payload: BootstrapSeasonRequest,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> LeagueResponse:
    from app.config import get_settings
    from app.providers.football_data import FootballDataProvider

    settings = get_settings()
    if not settings.football_data_api_token:
        raise HTTPException(status_code=503, detail="football-data.org token not configured")
    template = db.scalars(
        select(CompetitionTemplate).where(CompetitionTemplate.key == payload.template_key)
    ).first()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    with FootballDataProvider(
        settings.football_data_api_token, base_url=settings.football_data_base_url
    ) as provider:
        league = bootstrap_season(
            db,
            template=template,
            name=payload.name,
            season_label=payload.season_label,
            provider=provider,
            pool_provider_params=payload.pool_provider_params,
            scheduled_start_date=payload.scheduled_start_date,
            scheduled_end_date=payload.scheduled_end_date,
            force=payload.force,
        )
    db.add(
        LeagueMember(
            league_id=league.id,
            profile_id=profile.id,
            is_commissioner=True,
            draft_slot=1,
        )
    )
    db.commit()
    db.refresh(league)
    return _league_response(league)
