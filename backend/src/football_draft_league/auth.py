from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWK

from football_draft_league.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    email: str | None
    role: str
    claims: dict[str, Any]


class SupabaseTokenVerifier:
    """Verify Supabase access tokens using JWKS or the legacy shared secret."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._keys: dict[str, PyJWK] = {}

    async def _get_key(self, token: str) -> Any:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise InvalidTokenError("JWT is missing a key id")
        if kid not in self._keys:
            base_url = str(self.settings.supabase_url).rstrip("/")
            jwks_url = f"{base_url}/auth/v1/.well-known/jwks.json"
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
            key: Any
            algorithms: list[str]
            if self.settings.supabase_jwt_secret:
                key = self.settings.supabase_jwt_secret
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


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    verifier: Annotated[SupabaseTokenVerifier, Depends(get_token_verifier)],
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = await verifier.verify(credentials.credentials)
    try:
        return AuthenticatedUser(
            id=UUID(claims["sub"]),
            email=claims.get("email"),
            role=claims.get("role", "authenticated"),
            claims=claims,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Token subject is invalid") from exc


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
