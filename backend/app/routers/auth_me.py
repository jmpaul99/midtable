import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import AuthenticatedUser, get_current_profile, get_current_user
from app.db import get_db
from app.deps import is_platform_admin
from app.models import Invite, League, LeagueMember, Profile
from app.schemas.auth import MeResponse, MeUpdate
from app.services.members import default_team_name

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


def _me_response(profile: Profile, *, platform_admin: bool = False) -> MeResponse:
    return MeResponse(
        id=profile.public_id,
        email=profile.email,
        display_name=profile.display_name,
        auth_user_id=profile.auth_user_id,
        is_platform_admin=platform_admin,
    )


@router.get("/auth/me", response_model=MeResponse)
def auth_me(
    profile: Profile = Depends(get_current_profile),
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    """Return current profile; accept pending invites matching email on first login."""
    pending = db.scalars(
        select(Invite).where(
            Invite.email == profile.email,
            Invite.status == "pending",
        )
    ).all()
    joined_league_ids: list[str] = []
    for invite in pending:
        existing = db.scalars(
            select(LeagueMember).where(
                LeagueMember.league_id == invite.league_id,
                LeagueMember.profile_id == profile.id,
            )
        ).first()
        if existing is None:
            db.add(
                LeagueMember(
                    league_id=invite.league_id,
                    profile_id=profile.id,
                    is_commissioner=invite.is_commissioner,
                    draft_slot=invite.draft_slot,
                    team_name=default_team_name(profile.display_name),
                )
            )
            league = db.get(League, invite.league_id)
            if league is not None:
                joined_league_ids.append(str(league.public_id))
        invite.status = "accepted"
    db.commit()
    db.refresh(profile)
    if pending:
        logger.info(
            "auth_me auto-accepted invites profile_id=%s accepted=%s new_memberships=%s "
            "league_ids=%s",
            profile.public_id,
            len(pending),
            len(joined_league_ids),
            joined_league_ids,
        )
    return _me_response(profile, platform_admin=is_platform_admin(user))


@router.patch("/auth/me", response_model=MeResponse)
def update_me(
    body: MeUpdate,
    profile: Profile = Depends(get_current_profile),
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    """Update the current user's display name."""
    profile.display_name = body.display_name
    db.commit()
    db.refresh(profile)
    logger.info("profile display_name updated profile_id=%s", profile.public_id)
    logger.debug("profile display_name updated profile_id=%s name=%s", profile.public_id, body.display_name)
    return _me_response(profile, platform_admin=is_platform_admin(user))
