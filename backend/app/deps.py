"""Shared FastAPI dependencies."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import AuthenticatedUser, get_current_profile, get_current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.models import League, LeagueMember, Profile


def get_league_by_public_id(db: Session, public_id: UUID) -> League:
    league = db.scalars(select(League).where(League.public_id == public_id)).first()
    if league is None:
        raise HTTPException(status_code=404, detail="League not found")
    return league


def require_league_member(
    league_id: UUID,
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> tuple[League, LeagueMember]:
    league = get_league_by_public_id(db, league_id)
    member = db.scalars(
        select(LeagueMember).where(
            LeagueMember.league_id == league.id,
            LeagueMember.profile_id == profile.id,
        )
    ).first()
    if member is None:
        raise HTTPException(status_code=403, detail="Not a member of this league")
    return league, member


def require_commissioner(
    league_id: UUID,
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> tuple[League, LeagueMember]:
    league, member = require_league_member(league_id, db, profile)
    if not member.is_commissioner:
        raise HTTPException(status_code=403, detail="Commissioner access required")
    return league, member


def require_cron_secret(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.cron_secret or x_cron_secret != settings.cron_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron secret",
        )


# Re-exports for routers
CurrentUser = AuthenticatedUser
SettingsDep = Settings
