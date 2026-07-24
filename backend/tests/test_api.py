# ruff: noqa: E402, I001

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-with-sufficient-entropy")

from football_draft_league.auth import AuthenticatedUser
from football_draft_league.main import app
from football_draft_league.routes import _require_admin


def test_protected_api_requires_bearer_token() -> None:
    response = TestClient(app).get("/api/leagues")
    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token required"


def test_protected_api_rejects_invalid_token() -> None:
    response = TestClient(app).get(
        "/api/leagues", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert response.status_code == 401


def test_template_mutation_requires_admin_claim() -> None:
    member = AuthenticatedUser(uuid4(), "member@example.com", "authenticated", {})
    with pytest.raises(HTTPException) as error:
        _require_admin(member)
    assert error.value.status_code == 403

    admin = AuthenticatedUser(uuid4(), "admin@example.com", "admin", {})
    _require_admin(admin)
