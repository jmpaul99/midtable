"""Draft state includes preassigns; pool-full picks raise a clear conflict."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.errors import ConflictError


def test_build_draft_state_includes_preassigns(monkeypatch):
    from app.routers import draft as draft_router

    member_pid = uuid4()
    team_pid = uuid4()
    pool_pid = uuid4()
    state_pid = uuid4()

    state = SimpleNamespace(
        public_id=state_pid,
        status="pending",
        current_pick_number=1,
        pick_deadline_at=None,
    )
    league = SimpleNamespace(
        id=1,
        public_id=uuid4(),
        status="pre_draft",
        draft_style="linear",
        pick_timer_seconds=None,
        draft_scheduled_at=None,
    )
    member = SimpleNamespace(id=10, public_id=member_pid, draft_slot=1)
    team = SimpleNamespace(
        id=20, public_id=team_pid, name="Arsenal", crest_url="https://example/a.png"
    )
    pool = SimpleNamespace(id=30, public_id=pool_pid, slot_count=2, label="PL")
    entry = SimpleNamespace(
        member_id=10, team_id=20, pool_id=30, source="preassigned"
    )

    db = MagicMock()
    call_i = {"n": 0}

    def scalars(stmt):
        idx = call_i["n"]
        call_i["n"] += 1
        out = MagicMock()
        if idx == 0:
            out.first.return_value = state
            return out
        if idx == 1:
            out.all.return_value = [member]
            return out
        if idx == 2:
            out.all.return_value = [pool]
            return out
        if idx == 3:
            # DraftPick list
            out.all.return_value = []
            return out
        if idx == 4:
            # preassign RosterEntry list
            out.all.return_value = [entry]
            return out
        if idx == 5:
            # teams by id
            out.all.return_value = [team]
            return out
        if idx == 6:
            # pools by id
            out.all.return_value = [pool]
            return out
        out.first.return_value = None
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars

    resp = draft_router._build_draft_state(db, league)
    assert len(resp.preassigns) == 1
    assert resp.preassigns[0].member_id == member_pid
    assert resp.preassigns[0].team_id == team_pid
    assert resp.preassigns[0].pool_id == pool_pid
    assert resp.preassigns[0].team_name == "Arsenal"
    assert resp.picks == []


def test_make_pick_rejects_when_competition_slot_full(monkeypatch):
    import app.services.draft as draft_mod

    state = SimpleNamespace(status="open", current_pick_number=1)
    league = SimpleNamespace(id=1, draft_style="linear", status="drafting")
    member = SimpleNamespace(id=7, is_commissioner=False, public_id=uuid4())
    team = SimpleNamespace(id=3, public_id=uuid4())
    pool = SimpleNamespace(id=4, slot_count=1, public_id=uuid4())
    pool_team = SimpleNamespace(pool_id=4, team_id=3)

    members_out = MagicMock()
    members_out.all.return_value = [
        SimpleNamespace(
            id=7, draft_slot=1, is_commissioner=False, public_id=member.public_id
        )
    ]

    db = MagicMock()
    call_i = {"n": 0}

    def scalars(stmt):
        idx = call_i["n"]
        call_i["n"] += 1
        out = MagicMock()
        if idx == 0:
            out.first.return_value = state
            return out
        if idx == 1:
            return members_out
        if idx == 2:
            out.all.return_value = [pool]
            return out
        if idx == 3:
            out.first.return_value = team
            return out
        if idx == 4:
            out.first.return_value = None  # not already drafted
            return out
        if idx == 5:
            out.first.return_value = pool  # TeamPool by public_id
            return out
        if idx == 6:
            out.first.return_value = pool_team
            return out
        out.first.return_value = None
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars
    monkeypatch.setattr(draft_mod, "_member_has_open_draft_slots", lambda *a, **k: True)
    monkeypatch.setattr(draft_mod, "member_pool_filled", lambda *a, **k: True)

    with pytest.raises(ConflictError) as exc:
        draft_mod.make_pick(
            db,
            league=league,
            picker_member=member,
            team_public_id=team.public_id,
            pool_public_id=pool.public_id,
        )
    assert "competition is full" in str(exc.value.message).lower()
