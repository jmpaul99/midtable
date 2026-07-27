"""Tests for commissioner remove / appoint member endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.leagues_core import remove_member, update_member
from app.schemas.leagues import MemberAdminUpdate
from app.models import League
from app.services.members import (
    count_commissioners,
    is_sole_commissioner,
    join_or_return_member,
    next_draft_slot,
    renumber_draft_slots,
)


def _member(
    *,
    mid: int,
    public_id=None,
    is_commissioner: bool = False,
    draft_slot: int | None = None,
    profile_id: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=mid,
        public_id=public_id or uuid4(),
        is_commissioner=is_commissioner,
        draft_slot=draft_slot,
        profile_id=profile_id,
        team_name=None,
    )


def test_renumber_draft_slots_contiguous_preserving_order():
    a = _member(mid=1, draft_slot=2)
    b = _member(mid=2, draft_slot=5)
    c = _member(mid=3, draft_slot=None)
    renumber_draft_slots([b, c, a])
    assert a.draft_slot == 1
    assert b.draft_slot == 2
    assert c.draft_slot == 3


def test_next_draft_slot_starts_at_one():
    db = MagicMock()
    db.scalar.side_effect = [None, None]
    assert next_draft_slot(db, league_id=1) == 1
    db.get.assert_called_once_with(League, 1, with_for_update=True)
    assert db.scalar.call_count == 2


def test_next_draft_slot_appends_after_max():
    db = MagicMock()
    db.scalar.side_effect = [3, None]
    assert next_draft_slot(db, league_id=1) == 4
    db.get.assert_called_once_with(League, 1, with_for_update=True)


def test_next_draft_slot_respects_pending_invite_reservations():
    db = MagicMock()
    # Members occupy up to 2; a pending invite reserves slot 5.
    db.scalar.side_effect = [2, 5]
    assert next_draft_slot(db, league_id=1) == 6


def test_join_assigns_next_draft_slot():
    league = SimpleNamespace(id=1, status="pre_draft", config={"max_members": 4})
    profile = SimpleNamespace(id=7, display_name="Joiner")
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    db.scalars.return_value.all.return_value = [SimpleNamespace()]
    db.scalar.side_effect = [1, None]

    member, created = join_or_return_member(db, league, profile)
    assert created is True
    assert member.draft_slot == 2
    db.add.assert_called_once_with(member)
    db.get.assert_called_once_with(League, 1, with_for_update=True)


def test_join_keeps_explicit_draft_slot():
    league = SimpleNamespace(id=1, status="pre_draft", config=None)
    profile = SimpleNamespace(id=7, display_name="Joiner")
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    db.scalars.return_value.all.return_value = []

    member, created = join_or_return_member(db, league, profile, draft_slot=3)
    assert created is True
    assert member.draft_slot == 3
    db.scalar.assert_not_called()
    db.get.assert_not_called()


def test_is_sole_commissioner():
    sole = _member(mid=1, is_commissioner=True)
    other = _member(mid=2, is_commissioner=False)
    assert is_sole_commissioner(sole, [sole, other])
    second = _member(mid=3, is_commissioner=True)
    assert not is_sole_commissioner(sole, [sole, other, second])
    assert count_commissioners([sole, other, second]) == 2


def test_remove_member_success_renumbers_slots():
    actor = _member(mid=1, is_commissioner=True, draft_slot=1, profile_id=10)
    target = _member(mid=2, is_commissioner=False, draft_slot=2, profile_id=20)
    keep = _member(mid=3, is_commissioner=False, draft_slot=3, profile_id=30)
    league = SimpleNamespace(id=99, status="pre_draft")
    members = [actor, target, keep]

    db = MagicMock()
    scalars_out = MagicMock()
    scalars_out.all.return_value = members
    db.scalars.return_value = scalars_out

    result = remove_member(
        member_id=target.public_id,
        membership=(league, actor),
        db=db,
    )
    assert result.status_code == 204
    db.delete.assert_called_once_with(target)
    db.flush.assert_called_once()
    db.commit.assert_called_once()
    assert actor.draft_slot == 1
    assert keep.draft_slot == 2


def test_remove_member_rejects_when_not_pre_draft():
    actor = _member(mid=1, is_commissioner=True, draft_slot=1)
    target = _member(mid=2, draft_slot=2)
    league = SimpleNamespace(id=1, status="drafting")
    with pytest.raises(HTTPException) as exc:
        remove_member(
            member_id=target.public_id,
            membership=(league, actor),
            db=MagicMock(),
        )
    assert exc.value.status_code == 409
    assert "before the draft" in exc.value.detail


def test_remove_member_rejects_sole_commissioner_self():
    actor = _member(mid=1, is_commissioner=True, draft_slot=1)
    other = _member(mid=2, is_commissioner=False, draft_slot=2)
    league = SimpleNamespace(id=1, status="pre_draft")
    db = MagicMock()
    scalars_out = MagicMock()
    scalars_out.all.return_value = [actor, other]
    db.scalars.return_value = scalars_out

    with pytest.raises(HTTPException) as exc:
        remove_member(
            member_id=actor.public_id,
            membership=(league, actor),
            db=db,
        )
    assert exc.value.status_code == 409
    assert "last commissioner" in exc.value.detail
    db.delete.assert_not_called()


def test_remove_member_allows_self_when_another_commissioner_exists():
    actor = _member(mid=1, is_commissioner=True, draft_slot=1)
    other_commish = _member(mid=2, is_commissioner=True, draft_slot=2)
    league = SimpleNamespace(id=1, status="pre_draft")
    members = [actor, other_commish]
    db = MagicMock()
    scalars_out = MagicMock()
    scalars_out.all.return_value = members
    db.scalars.return_value = scalars_out

    result = remove_member(
        member_id=actor.public_id,
        membership=(league, actor),
        db=db,
    )
    assert result.status_code == 204
    db.delete.assert_called_once_with(actor)
    assert other_commish.draft_slot == 1


def test_remove_other_commissioner_succeeds():
    actor = _member(mid=1, is_commissioner=True, draft_slot=1)
    other = _member(mid=2, is_commissioner=True, draft_slot=2)
    league = SimpleNamespace(id=1, status="pre_draft")
    db = MagicMock()
    scalars_out = MagicMock()
    scalars_out.all.return_value = [actor, other]
    db.scalars.return_value = scalars_out

    result = remove_member(
        member_id=other.public_id,
        membership=(league, actor),
        db=db,
    )
    assert result.status_code == 204
    db.delete.assert_called_once_with(other)


def test_remove_member_404_when_missing():
    actor = _member(mid=1, is_commissioner=True, draft_slot=1)
    league = SimpleNamespace(id=1, status="pre_draft")
    db = MagicMock()
    scalars_out = MagicMock()
    scalars_out.all.return_value = [actor]
    db.scalars.return_value = scalars_out

    with pytest.raises(HTTPException) as exc:
        remove_member(
            member_id=uuid4(),
            membership=(league, actor),
            db=db,
        )
    assert exc.value.status_code == 404


def test_update_member_promote_and_demote():
    actor = _member(mid=1, is_commissioner=True, draft_slot=1, profile_id=10)
    target = _member(mid=2, is_commissioner=False, draft_slot=2, profile_id=20)
    league = SimpleNamespace(id=1, status="active")
    db = MagicMock()
    scalars_out = MagicMock()
    scalars_out.all.return_value = [actor, target]
    db.scalars.return_value = scalars_out
    db.get.return_value = SimpleNamespace(
        public_id=uuid4(), email="a@b.co", display_name="Alex"
    )

    out = update_member(
        member_id=target.public_id,
        payload=MemberAdminUpdate(is_commissioner=True),
        membership=(league, actor),
        db=db,
    )
    assert target.is_commissioner is True
    assert out.is_commissioner is True
    db.commit.assert_called()

    out2 = update_member(
        member_id=target.public_id,
        payload=MemberAdminUpdate(is_commissioner=False),
        membership=(league, actor),
        db=db,
    )
    assert target.is_commissioner is False
    assert out2.is_commissioner is False


def test_update_member_rejects_demote_sole_commissioner():
    actor = _member(mid=1, is_commissioner=True, draft_slot=1)
    other = _member(mid=2, is_commissioner=False, draft_slot=2)
    league = SimpleNamespace(id=1, status="pre_draft")
    db = MagicMock()
    scalars_out = MagicMock()
    scalars_out.all.return_value = [actor, other]
    db.scalars.return_value = scalars_out

    with pytest.raises(HTTPException) as exc:
        update_member(
            member_id=actor.public_id,
            payload=MemberAdminUpdate(is_commissioner=False),
            membership=(league, actor),
            db=db,
        )
    assert exc.value.status_code == 409
    assert "last commissioner" in exc.value.detail
