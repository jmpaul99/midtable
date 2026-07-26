"""Integration checks for default-deny auth against the FastAPI app."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


def test_unauthenticated_league_list_blocked_when_no_bypass():
    settings = Settings(
        app_env="production",
        auth_bypass_email="",
        cron_secret="prod-cron-secret-value",
        internal_api_secret="prod-internal-secret-value",
        turnstile_secret="turnstile-secret",
        turnstile_hostnames="mid-table.com",
        public_app_url="https://mid-table.com",
        mailjet_api_key_public="x",
        mailjet_api_key_private="y",
        mailjet_from_email="noreply@mid-table.com",
        cors_origins="https://mid-table.com",
        supabase_url="https://example.supabase.co",
    )
    with patch("app.middleware.get_settings", return_value=settings):
        with patch("app.main.get_settings", return_value=settings):
            client = TestClient(app)
            response = client.get("/leagues")
    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token required"


def test_join_link_preview_public():
    settings = Settings(auth_bypass_email="")
    with patch("app.middleware.get_settings", return_value=settings):
        client = TestClient(app)
        # 404 from handler is fine — gate must not return 401
        response = client.get("/join-links/preview", params={"token": "nope"})
    assert response.status_code != 401
