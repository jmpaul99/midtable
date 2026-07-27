"""Join link enable/claim tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth.jwt import get_or_create_profile
from app.routers.join_links import claim_join_link, preview_join_link, update_join_link
from app.schemas.leagues import JoinLinkClaimRequest, JoinLinkUpdate


def _settings():
    return SimpleNamespace(public_app_url="http://localhost:3000")


def _league(**kwargs):
    data = dict(
        id=1,
        public_id=uuid4(),
        name="Open League",
        season_label="2026/27",
        status="pre_draft",
        join_token=None,
        join_link_enabled=False,
        config={"max_members": 4},
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _profile(*, email: str = "joiner@example.com"):
    return SimpleNamespace(
        id=7,
        public_id=uuid4(),
        email=email,
        display_name="Joiner",
        auth_user_id=None,
    )


def test_update_join_link_enable_and_disable():
    league = _league()
    actor = SimpleNamespace(id=1)
    db = MagicMock()
    settings = _settings()

    enabled = update_join_link(
        payload=JoinLinkUpdate(enabled=True),
        membership=(league, actor),
        db=db,
        settings=settings,
    )
    assert enabled.enabled is True
    assert enabled.token
    assert enabled.join_url and enabled.token in enabled.join_url
    assert league.join_link_enabled is True

    disabled = update_join_link(
        payload=JoinLinkUpdate(enabled=False),
        membership=(league, actor),
        db=db,
        settings=settings,
    )
    assert disabled.enabled is False
    assert disabled.token is None
    assert league.join_token is None


def test_update_join_link_rotate_changes_token():
    league = _league(join_token="old-token", join_link_enabled=True)
    actor = SimpleNamespace(id=1)
    out = update_join_link(
        payload=JoinLinkUpdate(rotate=True),
        membership=(league, actor),
        db=MagicMock(),
        settings=_settings(),
    )
    assert out.enabled is True
    assert out.token != "old-token"
    assert league.join_token == out.token


def test_preview_join_link_not_found():
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    with pytest.raises(HTTPException) as exc:
        preview_join_link(token="missing", db=db)
    assert exc.value.status_code == 404


def test_claim_join_link_success():
    league = _league(join_token="join-tok", join_link_enabled=True)
    profile = _profile()
    db = MagicMock()
    # league lookup, existing member (none), member count, invite audit (none)
    db.scalars.return_value.first.side_effect = [league, None, None]
    db.scalars.return_value.all.return_value = []
    db.scalar.return_value = None  # no existing draft slots → assign 1
    db.get = MagicMock()

    with patch("app.routers.join_links._member_response") as member_resp:
        member_resp.return_value = SimpleNamespace(
            model_dump=lambda: {
                "id": uuid4(),
                "display_name": "Joiner",
                "team_name": "Joiner's Team",
                "email": profile.email,
                "is_commissioner": False,
                "draft_slot": 1,
                "role": "member",
            }
        )
        out = claim_join_link(
            payload=JoinLinkClaimRequest(token="join-tok"),
            profile=profile,
            db=db,
        )
    assert out.league_id == league.public_id
    assert db.add.call_count >= 1
    added_member = db.add.call_args_list[0].args[0]
    assert added_member.draft_slot == 1
    db.commit.assert_called()


def test_claim_rejects_disabled_or_rotated():
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    with pytest.raises(HTTPException) as exc:
        claim_join_link(
            payload=JoinLinkClaimRequest(token="stale"),
            profile=_profile(),
            db=db,
        )
    assert exc.value.status_code == 404


def test_claim_rejects_full_league():
    league = _league(join_token="join-tok", join_link_enabled=True, config={"max_members": 2})
    profile = _profile()
    db = MagicMock()
    db.scalars.return_value.first.side_effect = [league, None]
    db.scalars.return_value.all.return_value = [SimpleNamespace(), SimpleNamespace()]
    with pytest.raises(HTTPException) as exc:
        claim_join_link(
            payload=JoinLinkClaimRequest(token="join-tok"),
            profile=profile,
            db=db,
        )
    assert exc.value.status_code == 409
    assert "full" in exc.value.detail


def test_claim_rejects_wrong_status():
    league = _league(
        join_token="join-tok",
        join_link_enabled=True,
        status="active",
    )
    db = MagicMock()
    # league lookup, then no existing membership → status gate fires
    db.scalars.return_value.first.side_effect = [league, None]
    with pytest.raises(HTTPException) as exc:
        claim_join_link(
            payload=JoinLinkClaimRequest(token="join-tok"),
            profile=_profile(),
            db=db,
        )
    assert exc.value.status_code == 409


def test_claim_already_member_idempotent():
    league = _league(join_token="join-tok", join_link_enabled=True)
    profile = _profile()
    existing = SimpleNamespace(id=3, public_id=uuid4())
    db = MagicMock()
    db.scalars.return_value.first.side_effect = [league, existing, None]

    with patch("app.routers.join_links._member_response") as member_resp:
        member_resp.return_value = SimpleNamespace(
            model_dump=lambda: {
                "id": existing.public_id,
                "display_name": "Joiner",
                "team_name": "Joiner's Team",
                "email": profile.email,
                "is_commissioner": False,
                "draft_slot": 1,
                "role": "member",
            }
        )
        out = claim_join_link(
            payload=JoinLinkClaimRequest(token="join-tok"),
            profile=profile,
            db=db,
        )
    assert out.league_id == league.public_id
    db.commit.assert_called()


def test_claim_already_member_allows_closed_league():
    """Returning members can reopen the join link after draft/season starts."""
    league = _league(
        join_token="join-tok",
        join_link_enabled=True,
        status="active",
    )
    profile = _profile()
    existing = SimpleNamespace(id=3, public_id=uuid4())
    db = MagicMock()
    db.scalars.return_value.first.side_effect = [league, existing, None]

    with patch("app.routers.join_links._member_response") as member_resp:
        member_resp.return_value = SimpleNamespace(
            model_dump=lambda: {
                "id": existing.public_id,
                "display_name": "Joiner",
                "team_name": "Joiner's Team",
                "email": profile.email,
                "is_commissioner": False,
                "draft_slot": 1,
                "role": "member",
            }
        )
        out = claim_join_link(
            payload=JoinLinkClaimRequest(token="join-tok"),
            profile=profile,
            db=db,
        )
    assert out.league_id == league.public_id
    db.commit.assert_called()


def test_get_or_create_profile_without_invite():
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    profile = get_or_create_profile(
        db,
        email="newbie@example.com",
        auth_user_id=uuid4(),
        display_name="Newbie",
    )
    assert profile.email == "newbie@example.com"
    db.add.assert_called_once()
    db.flush.assert_called_once()
    db.begin_nested.assert_called_once()


def test_get_or_create_profile_resolves_insert_race():
    from sqlalchemy.exc import IntegrityError

    auth_id = uuid4()
    existing = SimpleNamespace(
        public_id=uuid4(),
        email="racer@example.com",
        auth_user_id=auth_id,
        display_name="Display Name",
    )
    db = MagicMock()
    # First pass: no profile by auth or email. After flush race: find by auth.
    db.scalars.return_value.first.side_effect = [None, None, existing]
    nested = MagicMock()
    nested.__enter__.return_value = nested
    nested.__exit__.return_value = None
    db.begin_nested.return_value = nested
    db.flush.side_effect = IntegrityError("stmt", {}, Exception("duplicate"))

    profile = get_or_create_profile(
        db,
        email="racer@example.com",
        auth_user_id=auth_id,
        display_name="Racer",
    )
    assert profile is existing
    assert profile.display_name == "Racer"
    db.add.assert_called_once()
    db.flush.assert_called_once()


def test_get_or_create_profile_syncs_stale_email():
    auth_id = uuid4()
    existing = SimpleNamespace(
        public_id=uuid4(),
        email="old@example.com",
        auth_user_id=auth_id,
        display_name="Alex",
    )
    db = MagicMock()
    db.scalars.return_value.first.return_value = existing

    profile = get_or_create_profile(
        db,
        email="new@example.com",
        auth_user_id=auth_id,
        display_name=None,
    )
    assert profile is existing
    assert profile.email == "new@example.com"
    db.add.assert_not_called()


def test_require_existing_profile_raises_when_missing():
    from fastapi import HTTPException

    from app.auth.jwt import AuthenticatedUser, require_existing_profile

    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    user = AuthenticatedUser(
        auth_user_id=uuid4(),
        email="gone@example.com",
        role="authenticated",
        claims={},
    )

    with pytest.raises(HTTPException) as exc:
        require_existing_profile(user=user, db=db)

    assert exc.value.status_code == 404
    db.commit.assert_not_called()
    db.add.assert_not_called()


def test_require_existing_profile_returns_without_creating():
    from app.auth.jwt import AuthenticatedUser, require_existing_profile

    auth_id = uuid4()
    existing = SimpleNamespace(
        public_id=uuid4(),
        email="old@example.com",
        auth_user_id=auth_id,
        display_name="Alex",
    )
    db = MagicMock()
    db.scalars.return_value.first.return_value = existing
    user = AuthenticatedUser(
        auth_user_id=auth_id,
        email="new@example.com",
        role="authenticated",
        claims={},
    )

    profile = require_existing_profile(user=user, db=db)

    assert profile is existing
    assert profile.email == "new@example.com"
    db.add.assert_not_called()
    db.commit.assert_not_called()
