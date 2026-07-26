"""Tests for POST /auth/email-status."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.routers.auth_me import email_status
from app.schemas.auth import EmailStatusRequest


def test_email_status_exists_true():
    db = MagicMock()
    db.execute.return_value.first.return_value = (1,)
    out = email_status(body=EmailStatusRequest(email="User@Example.com"), db=db)
    assert out.exists is True
    assert db.execute.call_args.args[1] == {"email": "user@example.com"}


def test_email_status_exists_false():
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    out = email_status(body=EmailStatusRequest(email="new@example.com"), db=db)
    assert out.exists is False


def test_email_status_rejects_invalid_email():
    with pytest.raises(ValidationError):
        EmailStatusRequest(email="not-an-email")
