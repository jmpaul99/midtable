"""League invites."""
from __future__ import annotations

import logging
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth.jwt import get_current_profile
from app.config import Settings, get_settings
from app.db import get_db
from app.deps import require_commissioner
from app.models import Invite, InviteEmailDelivery, League, LeagueMember, Profile
from app.routers.league_mappers import _member_response
from app.schemas.leagues import (
    InviteAcceptRequest,
    InviteAcceptResponse,
    InviteCreate,
    InviteEmailDeliveryResponse,
    InviteResponse,
    PendingInviteResponse,
)
from app.services.mailjet import send_invite_email
from app.services.members import default_team_name, required_manager_count

logger = logging.getLogger(__name__)

router = APIRouter(tags=["invites"])


def _accept_url(token: str | None, settings: Settings) -> str | None:
    if not token:
        return None
    base = settings.public_app_url.rstrip("/")
    return f"{base}/invites/accept?token={token}"


def _delivery_response(d: InviteEmailDelivery) -> InviteEmailDeliveryResponse:
    return InviteEmailDeliveryResponse(
        id=d.public_id,
        status=d.status,
        trigger=d.trigger,
        error=d.error,
        provider_message_id=d.provider_message_id,
        http_attempts=d.http_attempts,
        created_at=d.created_at,
    )


def _invite_response(
    invite: Invite,
    settings: Settings,
    *,
    include_send_status: bool = False,
) -> InviteResponse:
    deliveries = sorted(
        invite.email_deliveries or [],
        key=lambda d: d.created_at,
        reverse=True,
    )
    latest = deliveries[0] if deliveries else None
    email_sent: bool | None = None
    email_error: str | None = None
    if include_send_status and latest is not None:
        email_sent = latest.status == "sent"
        email_error = latest.error if latest.status != "sent" else None
    elif include_send_status:
        email_sent = False
        email_error = "No delivery attempt recorded"
    return InviteResponse(
        id=invite.public_id,
        email=invite.email,
        is_commissioner=invite.is_commissioner,
        draft_slot=invite.draft_slot,
        status=invite.status,
        token=invite.token,
        role="commissioner" if invite.is_commissioner else "member",
        accept_url=_accept_url(invite.token, settings),
        email_sent=email_sent,
        email_error=email_error,
        email_deliveries=[_delivery_response(d) for d in deliveries],
    )


def _inviter_display_name(db: Session, member: LeagueMember) -> str:
    profile = member.profile
    if profile is None:
        profile = db.get(Profile, member.profile_id)
    if profile is None:
        return "a commissioner"
    name = (profile.display_name or "").strip()
    return name or profile.email or "a commissioner"


def _send_and_record(
    db: Session,
    invite: Invite,
    league: League,
    actor: LeagueMember,
    *,
    trigger: str,
    settings: Settings,
) -> InviteEmailDelivery:
    accept = _accept_url(invite.token, settings)
    result = send_invite_email(
        to_email=invite.email,
        league_name=league.name,
        accept_url=accept or "",
        inviter_name=_inviter_display_name(db, actor),
        settings=settings,
    )
    delivery = InviteEmailDelivery(
        invite_id=invite.id,
        status=result.status,
        trigger=trigger,
        error=result.error,
        provider="mailjet",
        provider_message_id=result.provider_message_id,
        http_attempts=result.http_attempts,
    )
    db.add(delivery)
    db.commit()
    db.refresh(invite)
    db.refresh(delivery)
    logger.info(
        "invite email delivery invite_id=%s league_id=%s trigger=%s status=%s",
        invite.public_id,
        league.public_id,
        trigger,
        result.status,
    )
    return delivery


def _load_invite_with_deliveries(
    db: Session,
    *,
    invite_id: UUID,
    league_id: int,
) -> Invite | None:
    return db.scalars(
        select(Invite)
        .options(selectinload(Invite.email_deliveries))
        .where(Invite.public_id == invite_id, Invite.league_id == league_id)
    ).first()


@router.get("/invites/pending", response_model=list[PendingInviteResponse])
def list_pending_invites(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> list[PendingInviteResponse]:
    normalized = profile.email.strip().lower()
    rows = db.execute(
        select(Invite, League)
        .join(League, League.id == Invite.league_id)
        .where(
            Invite.email == normalized,
            Invite.status == "pending",
        )
        .order_by(Invite.created_at.desc())
    ).all()
    return [
        PendingInviteResponse(
            id=invite.public_id,
            league_id=league.public_id,
            league_name=league.name,
            season_label=league.season_label,
            is_commissioner=invite.is_commissioner,
            draft_slot=invite.draft_slot,
            role="commissioner" if invite.is_commissioner else "member",
            token=invite.token,
        )
        for invite, league in rows
    ]


@router.get("/leagues/{league_id}/invites", response_model=list[InviteResponse])
def list_invites(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[InviteResponse]:
    league, _ = membership
    invites = db.scalars(
        select(Invite)
        .options(selectinload(Invite.email_deliveries))
        .where(Invite.league_id == league.id)
    ).all()
    return [_invite_response(i, settings) for i in invites]


@router.post("/leagues/{league_id}/invites", response_model=InviteResponse)
def create_invite(
    payload: InviteCreate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> InviteResponse:
    league, actor = membership
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
    _send_and_record(db, invite, league, actor, trigger="create", settings=settings)
    invite = _load_invite_with_deliveries(db, invite_id=invite.public_id, league_id=league.id)
    assert invite is not None
    logger.info(
        "invite created invite_id=%s league_id=%s",
        invite.public_id,
        league.public_id,
    )
    logger.debug("invite created email=%s", invite.email)
    return _invite_response(invite, settings, include_send_status=True)


@router.post(
    "/leagues/{league_id}/invites/{invite_id}/resend",
    response_model=InviteResponse,
)
def resend_invite(
    invite_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> InviteResponse:
    league, actor = membership
    invite = _load_invite_with_deliveries(db, invite_id=invite_id, league_id=league.id)
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending invites can be resent")
    _send_and_record(db, invite, league, actor, trigger="resend", settings=settings)
    invite = _load_invite_with_deliveries(db, invite_id=invite_id, league_id=league.id)
    assert invite is not None
    return _invite_response(invite, settings, include_send_status=True)


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
    logger.info(
        "invite revoked invite_id=%s league_id=%s",
        invite.public_id,
        league.public_id,
    )


@router.patch("/leagues/{league_id}/invites/{invite_id}", response_model=InviteResponse)
def update_invite(
    invite_id: UUID,
    payload: InviteCreate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> InviteResponse:
    league, _ = membership
    invite = _load_invite_with_deliveries(db, invite_id=invite_id, league_id=league.id)
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
    invite = _load_invite_with_deliveries(db, invite_id=invite_id, league_id=league.id)
    assert invite is not None
    logger.info(
        "invite updated invite_id=%s league_id=%s is_commissioner=%s",
        invite.public_id,
        league.public_id,
        invite.is_commissioner,
    )
    return _invite_response(invite, settings)


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
        logger.info(
            "invite accepted existing_member invite_id=%s league_id=%s profile_id=%s",
            invite.public_id,
            league.public_id,
            profile.public_id,
        )
        base = _member_response(existing, profile)
        return InviteAcceptResponse(**base.model_dump(), league_id=league.public_id)

    member_count = len(
        list(db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all())
    )
    max_members = required_manager_count(league)
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
    logger.info(
        "invite accepted new_member invite_id=%s league_id=%s profile_id=%s member_id=%s",
        invite.public_id,
        league.public_id,
        profile.public_id,
        member.public_id,
    )
    base = _member_response(member, profile)
    return InviteAcceptResponse(**base.model_dump(), league_id=league.public_id)
