from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from football_draft_league.auth import SupabaseTokenVerifier


@pytest.mark.asyncio
async def test_supabase_hs_token_requires_expected_audience_and_issuer() -> None:
    secret = "test-secret-with-sufficient-entropy"
    settings = SimpleNamespace(
        supabase_jwt_secret=secret,
        supabase_jwt_audience="authenticated",
        jwt_issuer="https://example.supabase.co/auth/v1",
    )
    verifier = SupabaseTokenVerifier(settings)
    now = datetime.now(UTC)
    subject = uuid4()
    token = jwt.encode(
        {
            "sub": str(subject),
            "aud": "authenticated",
            "iss": settings.jwt_issuer,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "email": "member@example.com",
        },
        secret,
        algorithm="HS256",
    )
    claims = await verifier.verify(token)
    assert claims["sub"] == str(subject)


@pytest.mark.asyncio
async def test_supabase_token_rejects_wrong_audience() -> None:
    secret = "test-secret-with-sufficient-entropy"
    settings = SimpleNamespace(
        supabase_jwt_secret=secret,
        supabase_jwt_audience="authenticated",
        jwt_issuer="https://example.supabase.co/auth/v1",
    )
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "aud": "wrong",
            "iss": settings.jwt_issuer,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as error:
        await SupabaseTokenVerifier(settings).verify(token)
    assert error.value.status_code == 401
