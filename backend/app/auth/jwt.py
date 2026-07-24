"""Supabase JWT verification and invite-only gating helpers."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWK
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Invite, Profile

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
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(jwks_url)
                response.raise_for_status()
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
            if self.settings.supabase_jwt_secret:
                key: Any = self.settings.supabase_jwt_secret
                algorithms = ["HS256"]
            else:
                key = await self._get_key(token)
                algorithms = ["RS256", "ES256"]
            return jwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience=self.settings.supabase_jwt_audience,
                issuer=self.settings.jwt_issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except (InvalidTokenError, httpx.HTTPError, KeyError, ValueError) as exc:
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


def get_or_create_profile(
    db: Session,
    *,
    email: str,
    auth_user_id: UUID | None,
    display_name: str | None = None,
    skip_invite_gate: bool = False,
) -> Profile:
    normalized = email.strip().lower()
    profile = db.scalars(select(Profile).where(Profile.email == normalized)).first()
    if profile:
        if auth_user_id and profile.auth_user_id is None:
            profile.auth_user_id = auth_user_id
        return profile
    if not skip_invite_gate:
        require_invited_email(db, normalized)
    profile = Profile(
        email=normalized,
        auth_user_id=auth_user_id,
        display_name=display_name or normalized.split("@")[0],
    )
    db.add(profile)
    db.flush()
    return profile


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
    verifier: SupabaseTokenVerifier = Depends(get_token_verifier),
) -> AuthenticatedUser:
    if settings.auth_bypass_email:
        return AuthenticatedUser(
            auth_user_id=None,
            email=settings.auth_bypass_email.strip().lower(),
            role="authenticated",
            claims={"bypass": True},
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
    return get_or_create_profile(
        db,
        email=user.email,
        auth_user_id=user.auth_user_id,
        skip_invite_gate=user.bypass,
    )
