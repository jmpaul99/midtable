"""League invites."""
from __future__ import annotations

import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.db import get_db
from app.deps import require_commissioner
from app.models import Invite, League, LeagueMember, Profile
from app.routers.league_mappers import _member_response
from app.schemas.leagues import (
    InviteAcceptRequest,
    InviteAcceptResponse,
    InviteCreate,
    InviteResponse,
)
from app.services.members import default_team_name

router = APIRouter(tags=["invites"])

@router.get("/leagues/{league_id}/invites", response_model=list[InviteResponse])
def list_invites(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> list[InviteResponse]:
    league, _ = membership
    invites = db.scalars(select(Invite).where(Invite.league_id == league.id)).all()
    return [
        InviteResponse(
            id=i.public_id,
            email=i.email,
            is_commissioner=i.is_commissioner,
            draft_slot=i.draft_slot,
            status=i.status,
            token=i.token,
            role="commissioner" if i.is_commissioner else "member",
        )
        for i in invites
    ]


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
        token=secrets.token_urlsafe(24),
        is_commissioner=payload.is_commissioner,
        draft_slot=payload.draft_slot,
        status="pending",
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return InviteResponse(
        id=invite.public_id,
        email=invite.email,
        is_commissioner=invite.is_commissioner,
        draft_slot=invite.draft_slot,
        status=invite.status,
        token=invite.token,
        role="commissioner" if invite.is_commissioner else "member",
    )


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


@router.patch("/leagues/{league_id}/invites/{invite_id}", response_model=InviteResponse)
def update_invite(
    invite_id: UUID,
    payload: InviteCreate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> InviteResponse:
    league, _ = membership
    invite = db.scalars(
        select(Invite).where(
            Invite.public_id == invite_id,
            Invite.league_id == league.id,
        )
    ).first()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending invites can be updated")
    invite.email = payload.email.strip().lower()
    invite.is_commissioner = payload.is_commissioner
    if payload.draft_slot is not None:
        invite.draft_slot = payload.draft_slot
    db.commit()
    db.refresh(invite)
    return InviteResponse(
        id=invite.public_id,
        email=invite.email,
        is_commissioner=invite.is_commissioner,
        draft_slot=invite.draft_slot,
        status=invite.status,
        token=invite.token,
        role="commissioner" if invite.is_commissioner else "member",
    )


@router.post("/invites/accept", response_model=InviteAcceptResponse)
def accept_invite(
    payload: InviteAcceptRequest,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> InviteAcceptResponse:
    invite = db.scalars(
        select(Invite).where(Invite.token == payload.token, Invite.status == "pending")
    ).first()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found or already used")
    if invite.email.lower() != profile.email.lower():
        raise HTTPException(status_code=403, detail="Invite email does not match signed-in user")
    league = db.get(League, invite.league_id)
    if league is None:
        raise HTTPException(status_code=404, detail="League not found")
    if league.status not in {"pre_draft", "drafting"}:
        raise HTTPException(status_code=409, detail="League is not accepting new managers")
    existing = db.scalars(
        select(LeagueMember).where(
            LeagueMember.league_id == invite.league_id,
            LeagueMember.profile_id == profile.id,
        )
    ).first()
    if existing:
        invite.status = "accepted"
        db.commit()
        base = _member_response(existing, profile)
        return InviteAcceptResponse(**base.model_dump(), league_id=league.public_id)

    member_count = len(
        list(db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all())
    )
    config = league.config or {}
    max_members: int | None = None
    if "max_members" in config and config.get("max_members") is not None:
        try:
            max_members = max(2, int(config["max_members"]))
        except (TypeError, ValueError):
            max_members = None
    if max_members is not None and member_count >= max_members:
        raise HTTPException(
            status_code=409,
            detail=f"League is full ({max_members} managers)",
        )

    draft_slot = invite.draft_slot
    if draft_slot is not None:
        taken = db.scalars(
            select(LeagueMember).where(
                LeagueMember.league_id == league.id,
                LeagueMember.draft_slot == draft_slot,
            )
        ).first()
        if taken is not None:
            raise HTTPException(status_code=409, detail=f"Draft slot {draft_slot} already taken")

    member = LeagueMember(
        league_id=invite.league_id,
        profile_id=profile.id,
        is_commissioner=invite.is_commissioner,
        draft_slot=draft_slot,
        team_name=default_team_name(profile.display_name),
    )
    db.add(member)
    invite.status = "accepted"
    db.commit()
    db.refresh(member)
    base = _member_response(member, profile)
    return InviteAcceptResponse(**base.model_dump(), league_id=league.public_id)


