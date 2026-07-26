"""Pending invites inbox for the signed-in user."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.routers.invites import list_pending_invites


def _profile(*, email: str = "manager@example.com"):
    return SimpleNamespace(
        id=7,
        public_id=uuid4(),
        email=email,
        display_name="Manager",
    )


def _league(**kwargs):
    data = dict(
        id=1,
        public_id=uuid4(),
        name="Sunday League",
        season_label="2026/27",
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _invite(**kwargs):
    data = dict(
        public_id=uuid4(),
        league_id=1,
        email="manager@example.com",
        token="tok-pending",
        is_commissioner=False,
        draft_slot=3,
        status="pending",
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_list_pending_invites_returns_matching_pending():
    profile = _profile(email="Manager@Example.com")
    league = _league()
    invite = _invite(email="manager@example.com")
    db = MagicMock()
    db.execute.return_value.all.return_value = [(invite, league)]

    out = list_pending_invites(profile=profile, db=db)

    assert len(out) == 1
    assert out[0].id == invite.public_id
    assert out[0].league_id == league.public_id
    assert out[0].league_name == "Sunday League"
    assert out[0].season_label == "2026/27"
    assert out[0].role == "member"
    assert out[0].token == "tok-pending"
    assert out[0].draft_slot == 3
    db.execute.assert_called_once()


def test_list_pending_invites_empty_when_none():
    db = MagicMock()
    db.execute.return_value.all.return_value = []

    out = list_pending_invites(profile=_profile(), db=db)

    assert out == []


def test_list_pending_invites_commissioner_role():
    profile = _profile()
    league = _league()
    invite = _invite(is_commissioner=True, draft_slot=None)
    db = MagicMock()
    db.execute.return_value.all.return_value = [(invite, league)]

    out = list_pending_invites(profile=profile, db=db)

    assert out[0].role == "commissioner"
    assert out[0].is_commissioner is True
