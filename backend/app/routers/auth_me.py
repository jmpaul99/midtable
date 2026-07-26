import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.jwt import AuthenticatedUser, get_current_profile, get_current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.deps import is_platform_admin, require_internal_secret
from app.models import Profile
from app.schemas.auth import EmailStatusRequest, EmailStatusResponse, MeResponse, MeUpdate
from app.services.turnstile import EMAIL_STATUS_ACTION, verify_turnstile_token

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


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client:
        return request.client.host
    return None


@router.post(
    "/auth/email-status",
    response_model=EmailStatusResponse,
    dependencies=[Depends(require_internal_secret)],
)
def email_status(
    body: EmailStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> EmailStatusResponse:
    """Return whether an auth account exists (BFF-only; requires Turnstile)."""
    verify_turnstile_token(
        token=body.turnstile_token,
        settings=settings,
        expected_action=EMAIL_STATUS_ACTION,
        remote_ip=_client_ip(request),
    )
    row = db.execute(
        text("SELECT 1 FROM auth.users WHERE lower(email) = :email LIMIT 1"),
        {"email": body.email},
    ).first()
    return EmailStatusResponse(exists=row is not None)


@router.get("/auth/me", response_model=MeResponse)
def auth_me(
    profile: Profile = Depends(get_current_profile),
    user: AuthenticatedUser = Depends(get_current_user),
) -> MeResponse:
    """Return current profile."""
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
    logger.debug(
        "profile display_name updated profile_id=%s name=%s",
        profile.public_id,
        body.display_name,
    )
    return _me_response(profile, platform_admin=is_platform_admin(user))
