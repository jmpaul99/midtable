"""Tests for DELETE /auth/me account deletion."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.auth_me import delete_me


def _profile(*, pid: int = 10, auth_user_id=None, email: str = "user@example.com"):
    return SimpleNamespace(
        id=pid,
        public_id=uuid4(),
        auth_user_id=auth_user_id if auth_user_id is not None else uuid4(),
        email=email,
    )


def _member(
    *,
    mid: int,
    league_id: int,
    profile_id: int,
    is_commissioner: bool = False,
):
    return SimpleNamespace(
        id=mid,
        public_id=uuid4(),
        league_id=league_id,
        profile_id=profile_id,
        is_commissioner=is_commissioner,
    )


def _league(*, lid: int, name: str, status: str):
    return SimpleNamespace(id=lid, public_id=uuid4(), name=name, status=status)


def _db_with_memberships(
    *,
    memberships: list,
    leagues: list,
    all_members: list,
    auth_rowcount: int = 1,
) -> MagicMock:
    db = MagicMock()
    membership_scalars = MagicMock()
    membership_scalars.all.return_value = memberships
    league_scalars = MagicMock()
    league_scalars.all.return_value = leagues
    all_members_scalars = MagicMock()
    all_members_scalars.all.return_value = all_members
    if memberships:
        db.scalars.side_effect = [membership_scalars, league_scalars, all_members_scalars]
    else:
        db.scalars.side_effect = [membership_scalars]

    auth_result = MagicMock()
    auth_result.rowcount = auth_rowcount
    db.execute.side_effect = [
        MagicMock(),  # delete invites
        auth_result,  # delete auth.users
    ]
    return db


def test_delete_me_blocks_sole_commissioner_of_active_league():
    profile = _profile()
    league = _league(lid=1, name="World Cup", status="active")
    sole = _member(mid=1, league_id=1, profile_id=profile.id, is_commissioner=True)
    other = _member(mid=2, league_id=1, profile_id=99, is_commissioner=False)
    db = _db_with_memberships(
        memberships=[sole],
        leagues=[league],
        all_members=[sole, other],
    )

    with pytest.raises(HTTPException) as exc:
        delete_me(profile=profile, db=db)

    assert exc.value.status_code == 409
    assert "World Cup" in exc.value.detail
    db.commit.assert_not_called()
    db.delete.assert_not_called()


def test_delete_me_blocks_sole_commissioner_of_drafting_league():
    profile = _profile()
    league = _league(lid=1, name="Draft Night", status="drafting")
    sole = _member(mid=1, league_id=1, profile_id=profile.id, is_commissioner=True)
    db = _db_with_memberships(
        memberships=[sole],
        leagues=[league],
        all_members=[sole],
    )

    with pytest.raises(HTTPException) as exc:
        delete_me(profile=profile, db=db)

    assert exc.value.status_code == 409
    assert "Draft Night" in exc.value.detail
    db.commit.assert_not_called()


def test_delete_me_deletes_pre_draft_sole_comm_league_profile_and_auth_user():
    auth_user_id = uuid4()
    profile = _profile(auth_user_id=auth_user_id)
    league = _league(lid=1, name="Setup League", status="pre_draft")
    sole = _member(mid=1, league_id=1, profile_id=profile.id, is_commissioner=True)
    db = _db_with_memberships(
        memberships=[sole],
        leagues=[league],
        all_members=[sole],
    )

    result = delete_me(profile=profile, db=db)

    assert result.status_code == 204
    assert db.delete.call_args_list == [call(league), call(profile)]
    assert db.execute.call_count == 2
    auth_call = db.execute.call_args_list[1]
    assert "DELETE FROM auth.users" in str(auth_call.args[0])
    assert auth_call.args[1]["id"] == str(auth_user_id)
    db.commit.assert_called_once()


def test_delete_me_deletes_complete_sole_comm_league():
    profile = _profile()
    league = _league(lid=1, name="Finished", status="complete")
    sole = _member(mid=1, league_id=1, profile_id=profile.id, is_commissioner=True)
    db = _db_with_memberships(
        memberships=[sole],
        leagues=[league],
        all_members=[sole],
    )

    result = delete_me(profile=profile, db=db)

    assert result.status_code == 204
    db.delete.assert_any_call(league)
    db.delete.assert_any_call(profile)
    db.commit.assert_called_once()


def test_delete_me_allows_non_commissioner_in_active_league():
    auth_user_id = uuid4()
    profile = _profile(auth_user_id=auth_user_id)
    league = _league(lid=1, name="Active League", status="active")
    member = _member(mid=1, league_id=1, profile_id=profile.id, is_commissioner=False)
    commissioner = _member(mid=2, league_id=1, profile_id=99, is_commissioner=True)
    db = _db_with_memberships(
        memberships=[member],
        leagues=[league],
        all_members=[member, commissioner],
    )

    result = delete_me(profile=profile, db=db)

    assert result.status_code == 204
    db.delete.assert_called_once_with(profile)
    db.commit.assert_called_once()


def test_delete_me_allows_co_commissioner_in_active_league():
    profile = _profile()
    league = _league(lid=1, name="Shared", status="active")
    self_member = _member(mid=1, league_id=1, profile_id=profile.id, is_commissioner=True)
    other_comm = _member(mid=2, league_id=1, profile_id=99, is_commissioner=True)
    db = _db_with_memberships(
        memberships=[self_member],
        leagues=[league],
        all_members=[self_member, other_comm],
    )

    result = delete_me(profile=profile, db=db)

    assert result.status_code == 204
    db.delete.assert_called_once_with(profile)
    db.commit.assert_called_once()


def test_delete_me_fails_when_auth_user_missing():
    auth_user_id = uuid4()
    profile = _profile(auth_user_id=auth_user_id)
    db = _db_with_memberships(
        memberships=[],
        leagues=[],
        all_members=[],
        auth_rowcount=0,
    )

    with pytest.raises(HTTPException) as exc:
        delete_me(profile=profile, db=db)

    assert exc.value.status_code == 500
    assert "auth user" in exc.value.detail.lower()
    db.commit.assert_not_called()


def test_delete_me_skips_auth_delete_when_auth_user_id_null():
    profile = _profile()
    profile.auth_user_id = None
    db = MagicMock()
    membership_scalars = MagicMock()
    membership_scalars.all.return_value = []
    db.scalars.side_effect = [membership_scalars]
    db.execute.side_effect = [MagicMock()]  # delete invites

    result = delete_me(profile=profile, db=db)

    assert result.status_code == 204
    db.delete.assert_called_once_with(profile)
    assert db.execute.call_count == 1
    db.commit.assert_called_once()
