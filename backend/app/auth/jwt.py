"""Supabase JWT verification and profile helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWK
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Invite, Profile

logger = logging.getLogger(__name__)

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    auth_user_id: UUID | None
    email: str
    role: str
    claims: dict[str, Any]
    bypass: bool = False


class SupabaseTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._keys: dict[str, PyJWK] = {}

    async def _get_key(self, token: str) -> Any:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise InvalidTokenError("JWT is missing a key id")
        if kid not in self._keys:
            jwks_url = f"{self.settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(jwks_url)
                    response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("JWKS fetch failed url=%s error=%s", jwks_url, exc)
                raise
            self._keys = {
                item["kid"]: PyJWK.from_dict(item)
                for item in response.json().get("keys", [])
                if item.get("kid")
            }
        try:
            return self._keys[kid].key
        except KeyError as exc:
            raise InvalidTokenError("Unknown JWT key id") from exc

    async def verify(self, token: str) -> dict[str, Any]:
        try:
            key = await self._get_key(token)
            return jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                audience=self.settings.supabase_jwt_audience,
                issuer=self.settings.jwt_issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except (InvalidTokenError, httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning(
                "JWT verification failed reason=%s",
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc


@lru_cache
def get_token_verifier() -> SupabaseTokenVerifier:
    return SupabaseTokenVerifier(get_settings())


def ensure_invited_email(db: Session, email: str) -> Invite | None:
    """Return a pending/accepted invite for email, or None if not invited anywhere."""
    normalized = email.strip().lower()
    return db.scalars(
        select(Invite).where(
            Invite.email == normalized,
            Invite.status.in_(("pending", "accepted")),
        )
    ).first()


def require_invited_email(db: Session, email: str) -> Invite:
    invite = ensure_invited_email(db, email)
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Signup is invite-only; no pending invite for this email",
        )
    return invite


DEFAULT_DISPLAY_NAME = "Display Name"
MAX_DISPLAY_NAME_LEN = 80


def normalize_display_name(value: str | None) -> str | None:
    """Return a trimmed display name, or None if empty/invalid."""
    if value is None:
        return None
    name = value.strip()
    if not name or len(name) > MAX_DISPLAY_NAME_LEN:
        return None
    return name


def display_name_from_claims(claims: dict[str, Any]) -> str | None:
    meta = claims.get("user_metadata")
    if not isinstance(meta, dict):
        return None
    raw = meta.get("display_name")
    return normalize_display_name(str(raw) if raw is not None else None)


def _find_profile(
    db: Session,
    *,
    email: str,
    auth_user_id: UUID | None,
) -> Profile | None:
    if auth_user_id is not None:
        by_auth = db.scalars(
            select(Profile).where(Profile.auth_user_id == auth_user_id)
        ).first()
        if by_auth is not None:
            return by_auth
    return db.scalars(select(Profile).where(Profile.email == email)).first()


def _require_live_auth_user(db: Session, auth_user_id: UUID | None) -> None:
    """Reject JWTs whose Supabase auth row was already deleted."""
    if auth_user_id is None:
        return
    row = db.execute(
        text("SELECT 1 FROM auth.users WHERE id = :id LIMIT 1"),
        {"id": str(auth_user_id)},
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _apply_profile_updates(
    db: Session,
    profile: Profile,
    *,
    auth_user_id: UUID | None,
    display_name: str | None,
    email: str | None = None,
) -> Profile:
    if auth_user_id and profile.auth_user_id is None:
        profile.auth_user_id = auth_user_id
    if email is not None:
        normalized_email = email.strip().lower()
        if normalized_email and profile.email != normalized_email:
            conflict = db.scalars(
                select(Profile).where(
                    Profile.email == normalized_email,
                    Profile.id != profile.id,
                )
            ).first()
            if conflict is None:
                profile.email = normalized_email
            else:
                logger.warning(
                    "profile email sync skipped conflict profile_id=%s email=%s",
                    profile.public_id,
                    normalized_email,
                )
    chosen = normalize_display_name(display_name)
    if chosen and profile.display_name == DEFAULT_DISPLAY_NAME:
        profile.display_name = chosen
    return profile


def get_or_create_profile(
    db: Session,
    *,
    email: str,
    auth_user_id: UUID | None,
    display_name: str | None = None,
) -> Profile:
    """Create or return a profile for any authenticated user.

    League membership remains gated by personal invite accept or join-link claim.
    Concurrent first-login requests are safe: insert races re-load the winner.
    """
    normalized = email.strip().lower()
    existing = _find_profile(db, email=normalized, auth_user_id=auth_user_id)
    if existing is not None:
        return _apply_profile_updates(
            db,
            existing,
            auth_user_id=auth_user_id,
            display_name=display_name,
            email=normalized,
        )

    chosen = normalize_display_name(display_name) or DEFAULT_DISPLAY_NAME
    try:
        with db.begin_nested():
            profile = Profile(
                email=normalized,
                auth_user_id=auth_user_id,
                display_name=chosen,
            )
            db.add(profile)
            db.flush()
    except IntegrityError:
        # Loser of a concurrent insert may not see the winner immediately;
        # retry the lookup briefly before surfacing the conflict.
        raced: Profile | None = None
        for _ in range(3):
            raced = _find_profile(db, email=normalized, auth_user_id=auth_user_id)
            if raced is not None:
                break
            db.expire_all()
        if raced is None:
            raise
        logger.info(
            "profile create race resolved profile_id=%s",
            raced.public_id,
        )
        return _apply_profile_updates(
            db,
            raced,
            auth_user_id=auth_user_id,
            display_name=display_name,
            email=normalized,
        )

    logger.info("profile created profile_id=%s", profile.public_id)
    logger.debug("profile created email=%s", normalized)
    return profile


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
    verifier: SupabaseTokenVerifier = Depends(get_token_verifier),
) -> AuthenticatedUser:
    if settings.auth_bypass_email:
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AUTH_BYPASS_EMAIL is not allowed in production",
            )
        logger.warning(
            "AUTH_BYPASS_EMAIL active; authenticating as bypass user"
        )
        return AuthenticatedUser(
            auth_user_id=None,
            email=settings.auth_bypass_email.strip().lower(),
            role="admin",
            claims={"bypass": True, "app_metadata": {"role": "admin"}},
            bypass=True,
        )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = await verifier.verify(credentials.credentials)
    email = claims.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Token is missing email claim")
    try:
        auth_user_id = UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Token subject is invalid") from exc
    return AuthenticatedUser(
        auth_user_id=auth_user_id,
        email=str(email).strip().lower(),
        role=str(claims.get("role", "authenticated")),
        claims=claims,
    )


def get_current_profile(
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Profile:
    # Deleted accounts remove auth.users; reject lingering JWTs so they cannot
    # resurrect a profile via get_or_create_profile.
    _require_live_auth_user(db, user.auth_user_id)
    profile = get_or_create_profile(
        db,
        email=user.email,
        auth_user_id=user.auth_user_id,
        display_name=display_name_from_claims(user.claims),
    )
    db.commit()
    db.refresh(profile)
    return profile


def require_existing_profile(
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Profile:
    """Return the caller's profile without creating one.

    Used by destructive endpoints (e.g. account deletion) so a valid JWT
    cannot recreate a profile that was already removed. Does not sync email so
    callers can still purge invites addressed to the previous address.
    """
    _require_live_auth_user(db, user.auth_user_id)
    normalized = user.email.strip().lower()
    profile = _find_profile(db, email=normalized, auth_user_id=user.auth_user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )
    return profile
