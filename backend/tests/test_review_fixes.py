"""Tests for draft completion ordering, recompute seeds, and scoring smoke."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.draft import find_idempotent_pick, make_pick
from app.services.errors import ConflictError
from app.services.scoring import (
    MatchInput,
    ResultPoints,
    UpsetRules,
    is_finished,
    plan_recompute_cascade,
    score_match_events,
)
from app.services.sync import earliest_finished_seeds_per_pool


def _match(
    *,
    pool_id: int,
    kickoff: datetime,
    mid: int,
    finished: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=mid,
        pool_id=pool_id,
        home_team_id=1,
        away_team_id=2,
        kickoff_at=kickoff,
        home_goals=1 if finished else None,
        away_goals=0 if finished else None,
        status="FINISHED",
        scheduled_matchweek=1,
        stage=None,
    )


def test_earliest_finished_seeds_per_pool():
    t0 = datetime(2026, 8, 1, 12, tzinfo=UTC)
    t1 = datetime(2026, 8, 8, 12, tzinfo=UTC)
    t2 = datetime(2026, 8, 2, 12, tzinfo=UTC)
    matches = [
        _match(pool_id=1, kickoff=t1, mid=11),
        _match(pool_id=1, kickoff=t0, mid=10),
        _match(pool_id=2, kickoff=t2, mid=20),
        _match(pool_id=3, kickoff=t0, mid=30, finished=False),  # non-finished ignored
        _match(pool_id=9, kickoff=t0, mid=90),  # non-scoring pool ignored
    ]
    finished, seeds = earliest_finished_seeds_per_pool(
        matches,
        pool_by_match_id={10: 1, 11: 1, 20: 2, 30: 3, 90: 9},
        scoring_pool_ids={1, 2, 3},
    )
    assert {m.id for m in finished} == {10, 11, 20}
    assert {s.id for s in seeds} == {10, 20}


def test_score_match_events_smoke_for_finished_fixture():
    from app.services.scoring import RankedTeam

    kickoff = datetime(2026, 8, 15, 14, tzinfo=UTC)
    match = MatchInput(
        match_id=1,
        pool_id=1,
        home_team_id=10,
        away_team_id=20,
        kickoff_at=kickoff,
        home_goals=2,
        away_goals=1,
        status="FINISHED",
        scheduled_matchweek=1,
    )
    assert is_finished(match)
    before = {
        10: RankedTeam(team_id=10, rank=5, played=0, points=0),
        20: RankedTeam(team_id=20, rank=12, played=0, points=0),
    }
    events = score_match_events(
        match,
        before,
        result_points=ResultPoints(win=Decimal(3), draw=Decimal(1), loss=Decimal(0)),
        upset_rules=UpsetRules.from_config({}),
    )
    assert events
    assert any(e.event_type == "win" for e in events)
    plan = plan_recompute_cascade(match, [match])
    assert plan.starts_at == kickoff
    assert 1 in plan.affected_match_ids


def test_find_idempotent_pick_returns_existing():
    pick = SimpleNamespace(id=99)
    row = SimpleNamespace(pick_id=99)
    db = MagicMock()
    out = MagicMock()
    out.first.return_value = row
    db.scalars.return_value = out
    db.get.return_value = pick
    assert find_idempotent_pick(db, league_id=1, member_id=2, idempotency_key="k") is pick


def test_make_pick_completion_check_runs_after_flush(monkeypatch):
    """With autoflush=False, completion must run only after flush sees the new roster."""
    import app.services.draft as draft_mod

    order: list[str] = []

    @contextmanager
    def nested():
        yield

    db = MagicMock()
    db.begin_nested.side_effect = lambda: nested()

    def flush():
        order.append("flush")

    db.flush.side_effect = flush

    state = SimpleNamespace(status="open", current_pick_number=1)
    league = SimpleNamespace(id=1, draft_style="linear", status="drafting")
    member = SimpleNamespace(id=7, is_commissioner=False, public_id=uuid4())
    team = SimpleNamespace(id=3, public_id=uuid4())
    pool = SimpleNamespace(id=4, slot_count=1)
    pool_team = SimpleNamespace(pool_id=4, team_id=3)

    # scalars chain: state lock, idempotency skip, members, roster existing, pool_team
    scalar_results = [
        state,  # DraftState for_update
        None,  # no existing roster for team
        pool_team,  # PoolTeam join
    ]
    members_out = MagicMock()
    members_out.all.return_value = [
        SimpleNamespace(id=7, draft_slot=1, is_commissioner=False, public_id=member.public_id)
    ]

    call_i = {"n": 0}

    def scalars(stmt):
        # First call: DraftState
        # Then LeagueMember list
        # Then RosterEntry existing
        # Then PoolTeam
        # Later RosterEntry from _draft_is_complete / member_pool_filled
        idx = call_i["n"]
        call_i["n"] += 1
        if idx == 0:
            out = MagicMock()
            out.first.return_value = state
            return out
        if idx == 1:
            return members_out
        if idx == 2:
            out = MagicMock()
            out.first.return_value = None  # team not drafted
            return out
        if idx == 3:
            out = MagicMock()
            out.first.return_value = pool_team
            return out
        # capacity / complete checks
        out = MagicMock()
        out.all.return_value = []  # empty until after flush — capacity ok
        out.first.return_value = None
        return out

    db.scalars.side_effect = scalars
    db.get.return_value = pool

    def fake_complete(session, lg, ordered):
        order.append("complete_check")
        assert "flush" in order
        return True

    monkeypatch.setattr(draft_mod, "_draft_is_complete", fake_complete)
    monkeypatch.setattr(
        draft_mod,
        "member_pool_filled",
        lambda *a, **k: False,
    )

    team_out = MagicMock()
    team_out.first.return_value = team

    # Team lookup uses scalars(select(Team)...) — adjust: after members, team lookup
    # Rebuild scalars more carefully via side_effect list isn't enough for Team query.
    # Patch Team lookup by making the 3rd call return team when .first() — reorder.

    call_i["n"] = 0

    def scalars2(stmt):
        idx = call_i["n"]
        call_i["n"] += 1
        out = MagicMock()
        if idx == 0:
            out.first.return_value = state
            return out
        if idx == 1:
            return members_out
        if idx == 2:
            # TeamPool list for open-slot skip loop
            out.all.return_value = [pool]
            return out
        if idx == 3:
            out.first.return_value = team  # Team by public_id
            return out
        if idx == 4:
            out.first.return_value = None  # existing roster
            return out
        if idx == 5:
            out.first.return_value = pool_team
            return out
        out.all.return_value = []
        out.first.return_value = None
        return out

    db.scalars.side_effect = scalars2
    # Skip-loop open-slot check uses _member_has_open_draft_slots → member_pool_filled
    monkeypatch.setattr(draft_mod, "_member_has_open_draft_slots", lambda *a, **k: True)

    result = make_pick(
        db,
        league=league,
        picker_member=member,
        team_public_id=team.public_id,
        idempotency_key=None,
    )
    assert result is not None
    assert order == ["flush", "complete_check"]
    assert state.status == "complete"
    assert league.status == "active"


def test_make_pick_idempotent_short_circuit():
    existing = SimpleNamespace(id=55)
    db = MagicMock()
    state = SimpleNamespace(status="open", current_pick_number=3)
    out_state = MagicMock()
    out_state.first.return_value = state
    db.scalars.return_value = out_state

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.draft.find_idempotent_pick",
            lambda *a, **k: existing,
        )
        league = SimpleNamespace(id=1, draft_style="linear", status="drafting")
        member = SimpleNamespace(id=1, is_commissioner=False)
        pick = make_pick(
            db,
            league=league,
            picker_member=member,
            team_public_id=uuid4(),
            idempotency_key="same-key",
        )
    assert pick is existing
    assert state.current_pick_number == 3  # not advanced
