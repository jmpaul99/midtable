"""Autopick timer enforcement: locking and conflict handling."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.draft import try_auto_pick_if_expired
from app.services.errors import ConflictError


def test_try_auto_pick_locks_draft_state_before_selecting(monkeypatch):
    """Concurrent polls must serialize on draft_state FOR UPDATE."""
    import app.services.draft as draft_mod

    past = datetime.now(UTC) - timedelta(seconds=5)
    state = SimpleNamespace(
        status="open",
        pick_deadline_at=past,
        current_pick_number=1,
        league_id=1,
    )
    league = SimpleNamespace(id=1, pick_timer_seconds=60, public_id=uuid4())
    member = SimpleNamespace(id=7, public_id=uuid4())
    team = SimpleNamespace(id=3, public_id=uuid4(), name="Arsenal")
    pool = SimpleNamespace(id=4, public_id=uuid4())

    db = MagicMock()
    state_out = MagicMock()
    state_out.first.return_value = state
    members_out = MagicMock()
    members_out.all.return_value = [member]
    pools_out = MagicMock()
    pools_out.all.return_value = [pool]

    calls: list[object] = []

    def scalars(stmt):
        calls.append(stmt)
        text = str(stmt)
        out = MagicMock()
        if "draft_state" in text.lower() or "DraftState" in text:
            out.first.return_value = state
            return out
        # LeagueMember / TeamPool list queries
        if not hasattr(scalars, "n"):
            scalars.n = 0
        scalars.n += 1
        if scalars.n == 1:
            return members_out
        return pools_out

    db.scalars.side_effect = scalars

    monkeypatch.setattr(draft_mod, "ordered_members", lambda members: list(members))
    monkeypatch.setattr(
        draft_mod,
        "peek_on_clock_member",
        lambda *a, **k: (member, 1),
    )
    monkeypatch.setattr(
        draft_mod,
        "select_autopick_team",
        lambda *a, **k: draft_mod.AutopickSelection(
            mode="ranking", team=team, pool=pool
        ),
    )
    picked = {"n": 0}

    def fake_pick(*a, **k):
        picked["n"] += 1
        return SimpleNamespace(id=1)

    monkeypatch.setattr(draft_mod, "make_pick", fake_pick)

    assert try_auto_pick_if_expired(db, league) == "picked"
    assert picked["n"] == 1
    # First query must lock draft_state (with_for_update on the statement).
    assert getattr(calls[0], "_for_update_arg", None) is not None


def test_try_auto_pick_conflict_does_not_rewrite_fresh_deadline(monkeypatch):
    """Losing a race must not push the next pick's newly set deadline forward."""
    import app.services.draft as draft_mod

    past = datetime.now(UTC) - timedelta(seconds=5)
    future = datetime.now(UTC) + timedelta(seconds=60)
    state = SimpleNamespace(
        status="open",
        pick_deadline_at=past,
        current_pick_number=1,
        league_id=1,
    )
    league = SimpleNamespace(id=1, pick_timer_seconds=60, public_id=uuid4())
    member = SimpleNamespace(id=7, public_id=uuid4())
    team = SimpleNamespace(id=3, public_id=uuid4(), name="Arsenal")
    pool = SimpleNamespace(id=4, public_id=uuid4())

    db = MagicMock()
    members_out = MagicMock()
    members_out.all.return_value = [member]
    pools_out = MagicMock()
    pools_out.all.return_value = [pool]

    def scalars(stmt):
        out = MagicMock()
        text = str(stmt)
        if "draft_state" in text.lower() or getattr(stmt, "column_descriptions", None):
            out.first.return_value = state
            # Heuristic: first call is state lock
            return out
        if not hasattr(scalars, "n"):
            scalars.n = 0
        scalars.n += 1
        return members_out if scalars.n == 1 else pools_out

    db.scalars.side_effect = scalars

    def refresh(obj):
        # Another request already advanced the clock.
        obj.pick_deadline_at = future
        obj.current_pick_number = 2

    db.refresh.side_effect = refresh

    monkeypatch.setattr(draft_mod, "ordered_members", lambda members: list(members))
    monkeypatch.setattr(
        draft_mod,
        "peek_on_clock_member",
        lambda *a, **k: (member, 1),
    )
    monkeypatch.setattr(
        draft_mod,
        "select_autopick_team",
        lambda *a, **k: draft_mod.AutopickSelection(
            mode="ranking", team=team, pool=pool
        ),
    )
    monkeypatch.setattr(
        draft_mod,
        "make_pick",
        lambda *a, **k: (_ for _ in ()).throw(ConflictError("Team already drafted")),
    )
    applied = {"n": 0}

    def fake_deadline(st, lg, **kw):
        applied["n"] += 1
        st.pick_deadline_at = datetime.now(UTC) + timedelta(seconds=60)

    monkeypatch.setattr(draft_mod, "apply_pick_deadline", fake_deadline)

    assert try_auto_pick_if_expired(db, league) == "noop"
    assert applied["n"] == 0
    assert state.pick_deadline_at == future
