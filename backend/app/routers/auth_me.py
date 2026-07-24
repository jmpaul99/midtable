from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.db import get_db
from app.models import Invite, LeagueMember, Profile
from app.schemas.auth import MeResponse

router = APIRouter(tags=["auth"])


@router.get("/auth/me", response_model=MeResponse)
def auth_me(
    profile: Profile = Depends(get_current_profile),
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
                )
            )
        invite.status = "accepted"
    db.commit()
    db.refresh(profile)
    return MeResponse(
        id=profile.public_id,
        email=profile.email,
        display_name=profile.display_name,
        auth_user_id=profile.auth_user_id,
    )
