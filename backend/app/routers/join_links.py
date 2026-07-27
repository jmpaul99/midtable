"""Open league join links (not email-tied)."""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.config import Settings, get_settings
from app.db import get_db
from app.deps import require_commissioner
from app.models import Invite, League, LeagueMember, Profile
from app.routers.league_mappers import _member_response
from app.schemas.leagues import (
    InviteAcceptResponse,
    JoinLinkClaimRequest,
    JoinLinkPreviewResponse,
    JoinLinkResponse,
    JoinLinkUpdate,
)
from app.services.members import join_or_return_member

logger = logging.getLogger(__name__)

router = APIRouter(tags=["join-links"])


def _join_url(token: str | None, settings: Settings) -> str | None:
    if not token:
        return None
    base = settings.public_app_url.rstrip("/")
    return f"{base}/join?token={token}"


def _join_link_response(league: League, settings: Settings) -> JoinLinkResponse:
    token = league.join_token if league.join_link_enabled else None
    return JoinLinkResponse(
        enabled=bool(league.join_link_enabled and league.join_token),
        token=token,
        join_url=_join_url(token, settings),
    )


@router.get("/leagues/{league_id}/join-link", response_model=JoinLinkResponse)
def get_join_link(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    settings: Settings = Depends(get_settings),
) -> JoinLinkResponse:
    league, _ = membership
    return _join_link_response(league, settings)


@router.post("/leagues/{league_id}/join-link", response_model=JoinLinkResponse)
def update_join_link(
    payload: JoinLinkUpdate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JoinLinkResponse:
    league, _ = membership
    if payload.rotate:
        league.join_token = secrets.token_urlsafe(24)
        league.join_link_enabled = True
        action = "rotate"
    elif payload.enabled is True:
        if not league.join_token:
            league.join_token = secrets.token_urlsafe(24)
        league.join_link_enabled = True
        action = "enable"
    elif payload.enabled is False:
        league.join_link_enabled = False
        league.join_token = None
        action = "disable"
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide enabled=true, enabled=false, or rotate=true",
        )
    db.commit()
    db.refresh(league)
    if action in {"rotate", "disable"}:
        logger.warning(
            "join link %s league_id=%s enabled=%s",
            action,
            league.public_id,
            league.join_link_enabled,
        )
    else:
        logger.info(
            "join link %s league_id=%s enabled=%s",
            action,
            league.public_id,
            league.join_link_enabled,
        )
    return _join_link_response(league, settings)


@router.get("/join-links/preview", response_model=JoinLinkPreviewResponse)
def preview_join_link(
    token: str,
    db: Session = Depends(get_db),
) -> JoinLinkPreviewResponse:
    league = db.scalars(
        select(League).where(
            League.join_token == token,
            League.join_link_enabled.is_(True),
        )
    ).first()
    if league is None:
        raise HTTPException(status_code=404, detail="Join link not found or disabled")
    return JoinLinkPreviewResponse(
        league_name=league.name,
        league_id=league.public_id,
        enabled=True,
        season_label=league.season_label,
    )


@router.post("/join-links/claim", response_model=InviteAcceptResponse)
def claim_join_link(
    payload: JoinLinkClaimRequest,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> InviteAcceptResponse:
    token = payload.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Join token is required")
    league = db.scalars(
        select(League).where(
            League.join_token == token,
            League.join_link_enabled.is_(True),
        )
    ).first()
    if league is None:
        raise HTTPException(status_code=404, detail="Join link not found or disabled")

    member, created = join_or_return_member(db, league, profile)
    _ensure_accepted_invite_audit(db, league=league, profile=profile)
    db.commit()
    if created:
        db.refresh(member)
        logger.info(
            "join link claim new_member league_id=%s profile_id=%s member_id=%s",
            league.public_id,
            profile.public_id,
            member.public_id,
        )
    else:
        logger.info(
            "join link claim existing_member league_id=%s profile_id=%s",
            league.public_id,
            profile.public_id,
        )
    base = _member_response(member, profile)
    return InviteAcceptResponse(**base.model_dump(), league_id=league.public_id)


def _ensure_accepted_invite_audit(
    db: Session,
    *,
    league: League,
    profile: Profile,
) -> None:
    """Record an accepted invite row for join-link joins (audit / email uniqueness)."""
    email = profile.email.strip().lower()
    invite = db.scalars(
        select(Invite).where(Invite.league_id == league.id, Invite.email == email)
    ).first()
    if invite is None:
        db.add(
            Invite(
                league_id=league.id,
                email=email,
                token=None,
                is_commissioner=False,
                draft_slot=None,
                status="accepted",
            )
        )
        return
    invite.status = "accepted"
    invite.is_commissioner = False
