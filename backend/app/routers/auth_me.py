import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.auth.jwt import AuthenticatedUser, get_current_profile, get_current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.deps import is_platform_admin, require_internal_secret
from app.logging_config import log_id
from app.models import Invite, League, LeagueMember, Profile
from app.schemas.auth import EmailStatusRequest, EmailStatusResponse, MeResponse, MeUpdate
from app.services.members import is_sole_commissioner
from app.services.turnstile import EMAIL_STATUS_ACTION, verify_turnstile_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

_BLOCKING_LEAGUE_STATUSES = frozenset({"drafting", "active"})
_DELETABLE_SOLE_COMM_STATUSES = frozenset({"pre_draft", "complete"})


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
    return _me_response(profile, platform_admin=is_platform_admin(profile, user))


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
    return _me_response(profile, platform_admin=is_platform_admin(profile, user))


@router.delete("/auth/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> Response:
    """Permanently delete the current account, profile, and related app data."""
    memberships = list(
        db.scalars(select(LeagueMember).where(LeagueMember.profile_id == profile.id)).all()
    )
    league_ids = [m.league_id for m in memberships]
    leagues_by_id: dict[int, League] = {}
    members_by_league: dict[int, list[LeagueMember]] = {}
    if league_ids:
        leagues_by_id = {
            league.id: league
            for league in db.scalars(select(League).where(League.id.in_(league_ids))).all()
        }
        for member in db.scalars(
            select(LeagueMember).where(LeagueMember.league_id.in_(league_ids))
        ).all():
            members_by_league.setdefault(member.league_id, []).append(member)

    blocking_names: list[str] = []
    leagues_to_delete: list[League] = []
    for membership in memberships:
        league = leagues_by_id.get(membership.league_id)
        if league is None:
            continue
        league_members = members_by_league.get(membership.league_id, [])
        if not is_sole_commissioner(membership, league_members):
            continue
        if league.status in _BLOCKING_LEAGUE_STATUSES:
            blocking_names.append(league.name)
        elif league.status in _DELETABLE_SOLE_COMM_STATUSES:
            leagues_to_delete.append(league)

    if blocking_names:
        names = ", ".join(blocking_names)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete account while you are the only commissioner of "
                f"in-progress leagues: {names}. Promote another commissioner or "
                "delete those leagues first."
            ),
        )

    for league in leagues_to_delete:
        logger.warning(
            "league deleted with account league_id=%s name=%s status=%s profile_id=%s",
            log_id(league),
            getattr(league, "name", "?"),
            getattr(league, "status", "?"),
            log_id(profile),
        )
        db.delete(league)

    db.execute(delete(Invite).where(func.lower(Invite.email) == profile.email.lower()))

    auth_user_id = profile.auth_user_id
    logger.warning(
        "account deleted profile_id=%s auth_user_id=%s email=%s",
        log_id(profile),
        auth_user_id,
        profile.email,
    )
    db.delete(profile)
    db.flush()

    if auth_user_id is not None:
        result = db.execute(
            text("DELETE FROM auth.users WHERE id = :id"),
            {"id": str(auth_user_id)},
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete auth user",
            )

    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
