"""Shared FastAPI dependencies."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import AuthenticatedUser, get_current_profile, get_current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.models import League, LeagueMember, PoolTeam, Profile, Team, TeamPool
from app.providers.football_data import FootballDataProvider

logger = logging.getLogger(__name__)


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
        logger.warning(
            "authz denied reason=not_manager league_id=%s profile_id=%s",
            league_id,
            profile.public_id,
        )
        raise HTTPException(status_code=403, detail="Not a manager in this league")
    return league, member


def require_commissioner(
    league_id: UUID,
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> tuple[League, LeagueMember]:
    league, member = require_league_member(league_id, db, profile)
    if not member.is_commissioner:
        logger.warning(
            "authz denied reason=not_commissioner league_id=%s profile_id=%s",
            league.public_id,
            profile.public_id,
        )
        raise HTTPException(status_code=403, detail="Commissioner access required")
    return league, member


def is_platform_admin(user: AuthenticatedUser) -> bool:
    meta = user.claims.get("app_metadata") or {}
    return bool(user.bypass or meta.get("role") == "admin" or user.role == "admin")


def require_platform_admin(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    if is_platform_admin(user):
        return user
    logger.warning(
        "authz denied reason=not_platform_admin email=%s",
        user.email,
    )
    raise HTTPException(status_code=403, detail="Platform admin access required")


def require_cron_secret(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.cron_secret or x_cron_secret != settings.cron_secret:
        logger.warning("Rejected request with invalid cron secret")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron secret",
        )


def get_football_provider(
    settings: Settings = Depends(get_settings),
) -> Iterator[FootballDataProvider]:
    """Yield a configured football-data.org provider; closes the HTTP client after use."""
    if not settings.football_data_api_token:
        logger.error("football-data.org token not configured")
        raise HTTPException(
            status_code=503, detail="football-data.org token not configured"
        )
    provider = FootballDataProvider(
        settings.football_data_api_token, base_url=settings.football_data_base_url
    )
    try:
        yield provider
    finally:
        provider.close()


FootballProviderDep = Annotated[FootballDataProvider, Depends(get_football_provider)]


def team_in_league(db: Session, league_id: int, team_public_id: UUID) -> Team:
    team = db.scalars(
        select(Team)
        .join(PoolTeam, PoolTeam.team_id == Team.id)
        .join(TeamPool, TeamPool.id == PoolTeam.pool_id)
        .where(TeamPool.league_id == league_id, Team.public_id == team_public_id)
    ).first()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found in this league")
    return team
