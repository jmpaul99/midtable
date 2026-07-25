"""Unit tests for Mailjet invite email client."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx

from app.services.mailjet import MAILJET_SEND_URL, send_invite_email


def _settings(**overrides):
    base = dict(
        mailjet_api_key_public="pub",
        mailjet_api_key_private="priv",
        mailjet_from_email="from@example.com",
        mailjet_from_name="Midtable",
        public_app_url="http://localhost:3000",
        mailjet_configured=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_send_invite_skipped_when_unconfigured():
    settings = _settings(mailjet_configured=False)
    result = send_invite_email(
        to_email="a@example.com",
        league_name="Test League",
        accept_url="http://localhost/invites/accept?token=x",
        inviter_name="Alex",
        settings=settings,
    )
    assert result.status == "skipped"
    assert result.http_attempts == 0
    assert "not configured" in (result.error or "")


def test_send_invite_success():
    settings = _settings()
    client = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "Messages": [{"To": [{"MessageID": "msg-1", "Email": "a@example.com"}]}]
    }
    client.post.return_value = response

    result = send_invite_email(
        to_email="a@example.com",
        league_name="Test League",
        accept_url="http://localhost/invites/accept?token=x",
        inviter_name="Alex",
        settings=settings,
        client=client,
    )
    assert result.status == "sent"
    assert result.provider_message_id == "msg-1"
    assert result.http_attempts == 1
    client.post.assert_called_once()
    kwargs = client.post.call_args
    assert kwargs.args[0] == MAILJET_SEND_URL
    body = kwargs.kwargs["json"]
    message = body["Messages"][0]
    assert "TemplateID" not in message
    assert "Subject" in message and message["Subject"]
    assert "Test League" in message["Subject"]
    assert "Test League" in message["HTMLPart"]
    assert "Alex" in message["HTMLPart"]
    assert "http://localhost/invites/accept?token=x" in message["HTMLPart"]
    assert "http://localhost/invites/accept?token=x" in message["TextPart"]
    assert "http://localhost:3000/brand/png/lockup-matchday.png" in message["HTMLPart"]
    assert "http://localhost:3000/brand/png/wordmark-matchday.png" in message["HTMLPart"]
    assert 'href="http://localhost:3000"' in message["HTMLPart"]
    assert "{{" not in message["HTMLPart"]


def test_send_invite_retries_then_succeeds(monkeypatch):
    settings = _settings()
    client = MagicMock()
    fail = MagicMock(status_code=503, text="busy")
    ok = MagicMock(status_code=200)
    ok.json.return_value = {"Messages": [{"To": [{"MessageID": "msg-2"}]}]}
    client.post.side_effect = [fail, ok]
    sleeps: list[float] = []
    monkeypatch.setattr("app.services.mailjet.time.sleep", sleeps.append)

    result = send_invite_email(
        to_email="a@example.com",
        league_name="Test League",
        accept_url="http://localhost/invites/accept?token=x",
        inviter_name="Alex",
        settings=settings,
        client=client,
    )
    assert result.status == "sent"
    assert result.http_attempts == 2
    assert len(sleeps) == 1
    assert client.post.call_count == 2


def test_send_invite_hard_failure_no_retry_on_400():
    settings = _settings()
    client = MagicMock()
    client.post.return_value = MagicMock(status_code=400, text="bad request")

    result = send_invite_email(
        to_email="a@example.com",
        league_name="Test League",
        accept_url="http://localhost/invites/accept?token=x",
        inviter_name="Alex",
        settings=settings,
        client=client,
    )
    assert result.status == "failed"
    assert result.http_attempts == 1
    assert "400" in (result.error or "")
    assert client.post.call_count == 1


def test_send_invite_retries_transport_errors(monkeypatch):
    settings = _settings()
    client = MagicMock()
    client.post.side_effect = httpx.ConnectError("down")
    monkeypatch.setattr("app.services.mailjet.time.sleep", lambda *_: None)

    result = send_invite_email(
        to_email="a@example.com",
        league_name="Test League",
        accept_url="http://localhost/invites/accept?token=x",
        inviter_name="Alex",
        settings=settings,
        client=client,
    )
    assert result.status == "failed"
    assert result.http_attempts == 3
    assert "Transport" in (result.error or "")
