"""Invite create soft-fail + delivery history recording."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.routers.invites import create_invite, resend_invite
from app.schemas.leagues import InviteCreate
from app.services.mailjet import MailSendResult


def _settings():
    return SimpleNamespace(public_app_url="http://localhost:3000")


def _league():
    return SimpleNamespace(id=1, name="Test League", public_id=uuid4())


def _invite(*, status: str = "pending"):
    return SimpleNamespace(
        id=10,
        public_id=uuid4(),
        league_id=1,
        email="manager@example.com",
        token="tok-abc",
        is_commissioner=False,
        draft_slot=None,
        status=status,
        email_deliveries=[],
    )


@patch("app.routers.invites.send_invite_email")
def test_create_invite_soft_fails_and_records_delivery(mock_send):
    mock_send.return_value = MailSendResult(
        status="failed",
        error="Mailjet HTTP 500: boom",
        http_attempts=3,
    )
    league = _league()
    actor = SimpleNamespace(
        id=1,
        profile_id=99,
        profile=SimpleNamespace(display_name="Alex", email="alex@example.com"),
    )
    invite = _invite()
    delivery = SimpleNamespace(
        public_id=uuid4(),
        status="failed",
        trigger="create",
        error="Mailjet HTTP 500: boom",
        provider_message_id=None,
        http_attempts=3,
        created_at=datetime.now(timezone.utc),
    )

    db = MagicMock()

    def refresh(obj):
        if obj is invite:
            invite.email_deliveries = [delivery]

    db.refresh.side_effect = refresh

    # create path: add invite, commit, refresh, then _send_and_record adds delivery
    # _load_invite_with_deliveries returns invite with deliveries
    loaded = _invite()
    loaded.email_deliveries = [delivery]
    loaded.public_id = invite.public_id
    db.scalars.return_value.first.return_value = loaded

    # Capture Invite constructed in create_invite
    created: list = []

    def add(obj):
        created.append(obj)
        if hasattr(obj, "email") and not hasattr(obj, "trigger"):
            obj.id = invite.id
            obj.public_id = invite.public_id
            obj.token = invite.token
            obj.email_deliveries = []

    db.add.side_effect = add

    out = create_invite(
        payload=InviteCreate(email="manager@example.com"),
        membership=(league, actor),
        db=db,
        settings=_settings(),
    )
    assert out.email_sent is False
    assert out.email_error == "Mailjet HTTP 500: boom"
    assert out.accept_url and "tok-abc" in (loaded.token or out.token or "")
    assert len(out.email_deliveries) == 1
    assert out.email_deliveries[0].status == "failed"
    mock_send.assert_called_once()
    assert any(hasattr(o, "trigger") and o.trigger == "create" for o in created)


@patch("app.routers.invites.send_invite_email")
def test_resend_appends_delivery(mock_send):
    mock_send.return_value = MailSendResult(
        status="sent",
        provider_message_id="m1",
        http_attempts=1,
    )
    league = _league()
    actor = SimpleNamespace(
        id=1,
        profile_id=99,
        profile=SimpleNamespace(display_name="Alex", email="alex@example.com"),
    )
    first = SimpleNamespace(
        public_id=uuid4(),
        status="failed",
        trigger="create",
        error="old",
        provider_message_id=None,
        http_attempts=1,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    second = SimpleNamespace(
        public_id=uuid4(),
        status="sent",
        trigger="resend",
        error=None,
        provider_message_id="m1",
        http_attempts=1,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    invite = _invite()
    invite.email_deliveries = [first]
    invite_id = invite.public_id

    db = MagicMock()
    # first load for resend check, second after send
    loaded_after = _invite()
    loaded_after.public_id = invite_id
    loaded_after.email_deliveries = [second, first]
    db.scalars.return_value.first.side_effect = [invite, loaded_after]

    out = resend_invite(
        invite_id=invite_id,
        membership=(league, actor),
        db=db,
        settings=_settings(),
    )
    assert out.email_sent is True
    assert out.email_error is None
    assert len(out.email_deliveries) == 2
    assert out.email_deliveries[0].trigger == "resend"
