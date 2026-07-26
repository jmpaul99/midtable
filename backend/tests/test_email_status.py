"""Tests for POST /auth/email-status."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import Settings
from app.routers.auth_me import email_status
from app.schemas.auth import EmailStatusRequest


def _settings(**overrides: object) -> Settings:
    base = {
        "turnstile_secret": "test-secret",
        "turnstile_hostnames": "localhost",
        "internal_api_secret": "dev-internal-secret",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@patch("app.routers.auth_me.verify_turnstile_token")
def test_email_status_exists_true(mock_verify: MagicMock):
    db = MagicMock()
    db.execute.return_value.first.return_value = (1,)
    request = MagicMock()
    request.headers.get.return_value = None
    request.client = None
    out = email_status(
        body=EmailStatusRequest(email="User@Example.com", turnstile_token="tok"),
        request=request,
        db=db,
        settings=_settings(),
    )
    assert out.exists is True
    assert db.execute.call_args.args[1] == {"email": "user@example.com"}
    mock_verify.assert_called_once()


@patch("app.routers.auth_me.verify_turnstile_token")
def test_email_status_exists_false(mock_verify: MagicMock):
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    request = MagicMock()
    request.headers.get.return_value = None
    request.client = None
    out = email_status(
        body=EmailStatusRequest(email="new@example.com", turnstile_token="tok"),
        request=request,
        db=db,
        settings=_settings(),
    )
    assert out.exists is False
    mock_verify.assert_called_once()


def test_email_status_rejects_invalid_email():
    with pytest.raises(ValidationError):
        EmailStatusRequest(email="not-an-email", turnstile_token="tok")


def test_email_status_requires_turnstile_token():
    with pytest.raises(ValidationError):
        EmailStatusRequest(email="a@b.com", turnstile_token="")


@patch("app.services.turnstile.httpx.Client")
def test_verify_turnstile_rejects_bad_action(mock_client_cls: MagicMock):
    from app.services.turnstile import verify_turnstile_token

    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "success": True,
        "action": "wrong",
        "hostname": "localhost",
    }
    client.post.return_value = response

    with pytest.raises(HTTPException) as exc:
        verify_turnstile_token(
            token="tok",
            settings=_settings(),
            expected_action="email-status",
        )
    assert exc.value.status_code == 403


def test_turnstile_hostnames_split_comma_space_semicolon():
    settings = _settings(
        turnstile_hostnames="mid-table.com, Other.Example ;localhost",
    )
    assert settings.turnstile_hostname_set == {
        "mid-table.com",
        "other.example",
        "localhost",
    }
