from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import AuthenticatedUser, get_current_profile, get_current_user
from app.db import get_db
from app.deps import is_platform_admin
from app.models import Invite, LeagueMember, Profile
from app.schemas.auth import MeResponse, MeUpdate
from app.services.members import default_team_name

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
        invite.status = "accepted"
    db.commit()
    db.refresh(profile)
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
    return _me_response(profile, platform_admin=is_platform_admin(user))
