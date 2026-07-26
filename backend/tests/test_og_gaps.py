"""Tests for OG-plan gap fixes (payouts, preassign gate, phase counts, etc.)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.errors import ConflictError
from app.services.payouts import apply_payouts


def test_payouts_normal_1st_2nd():
    entries = [
        {"rank": 1, "member_id": "a"},
        {"rank": 2, "member_id": "b"},
        {"rank": 3, "member_id": "c"},
    ]
    payouts = [
        {"phase": "season", "position": 1, "amount": 100},
        {"phase": "season", "position": 2, "amount": 50},
    ]
    out = apply_payouts(entries, payouts, None)
    assert out[0]["payout"] == 100.0
    assert out[1]["payout"] == 50.0
    assert out[2]["payout"] == 0.0


def test_payouts_two_way_tie_for_first():
    entries = [
        {"rank": 1, "member_id": "a"},
        {"rank": 1, "member_id": "b"},
        {"rank": 3, "member_id": "c"},
    ]
    payouts = [
        {"phase": "season", "position": 1, "amount": 100},
        {"phase": "season", "position": 2, "amount": 50},
    ]
    out = apply_payouts(entries, payouts, "season")
    assert out[0]["payout"] == 75.0
    assert out[1]["payout"] == 75.0
    assert out[2]["payout"] == 0.0


def test_payouts_three_way_tie_and_phase_filter():
    entries = [{"rank": 1, "member_id": x} for x in ("a", "b", "c")]
    payouts = [
        {"phase": "mw1_19", "position": 1, "amount": 50},
        {"phase": "season", "position": 1, "amount": 100},
        {"phase": "season", "position": 2, "amount": 50},
        {"phase": "season", "position": 3, "amount": 25},
    ]
    mid = apply_payouts(entries, payouts, "mw1_19")
    assert mid[0]["payout"] == pytest.approx(50 / 3)
    assert mid[1]["payout"] == pytest.approx(50 / 3)

    season = apply_payouts(entries, payouts, None)
    assert season[0]["payout"] == pytest.approx(175 / 3)


def test_phase_match_counts_helper():
    from app.services.analytics import phase_match_counts

    matches = [
        SimpleNamespace(
            scheduled_matchweek=1,
            stage=None,
            status="FINISHED",
            pool_id=1,
        ),
        SimpleNamespace(
            scheduled_matchweek=2,
            stage=None,
            status="SCHEDULED",
            pool_id=1,
        ),
        SimpleNamespace(
            scheduled_matchweek=20,
            stage=None,
            status="FINISHED",
            pool_id=1,
        ),
        SimpleNamespace(
            scheduled_matchweek=3,
            stage=None,
            status="FINISHED",
            pool_id=2,
        ),
    ]
    mf = {"type": "matchweek_range", "from": 1, "to": 19}
    counts = phase_match_counts(
        matches,
        match_filter=mf,
        scoring_pool_ids={1},
    )
    assert counts["matching_matches"] == 2
    assert counts["finished_matches"] == 1
    assert counts["remaining_matches"] == 1
    assert counts["is_final"] is False


def _ready_pool():
    return SimpleNamespace(
        id=100,
        key="premier_league",
        label="Premier League",
        slot_count=5,
        scores_match_results=True,
        competition_code="PL",
        season_year=2026,
    )


def test_open_draft_requires_supported_preassigns():
    from app.services.draft import open_draft

    league = SimpleNamespace(
        id=1,
        status="pre_draft",
        preassign_mode="supported",
        config={"max_members": 2},
    )
    members = [
        SimpleNamespace(id=10, draft_slot=1),
        SimpleNamespace(id=11, draft_slot=2),
    ]
    pools = [_ready_pool()]

    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "league_member" in sql:
            out.all.return_value = members
            return out
        if "team_pool" in sql:
            out.all.return_value = pools
            return out
        if "pool_team" in sql or "poolteam" in sql:
            out.all.return_value = [SimpleNamespace(id=1)]
            return out
        if "roster" in sql:
            out.all.return_value = [
                SimpleNamespace(member_id=10, team_id=1, source="preassigned"),
            ]
            return out
        out.first.return_value = None
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars

    with pytest.raises(ConflictError) as exc:
        open_draft(db, league)
    detail = exc.value.message
    assert isinstance(detail, dict)
    assert detail.get("blockers")


def test_open_draft_requires_exact_manager_count():
    from app.services.draft import open_draft

    league = SimpleNamespace(
        id=1,
        status="pre_draft",
        preassign_mode="none",
        config={"max_members": 4},
    )
    members = [
        SimpleNamespace(id=10, draft_slot=1),
        SimpleNamespace(id=11, draft_slot=2),
    ]
    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "league_member" in sql:
            out.all.return_value = members
            return out
        if "team_pool" in sql:
            out.all.return_value = [_ready_pool()]
            return out
        if "pool_team" in sql or "poolteam" in sql:
            out.all.return_value = [SimpleNamespace(id=1)]
            return out
        out.first.return_value = None
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars

    with pytest.raises(ConflictError) as exc:
        open_draft(db, league)
    assert "2 of 4 managers" in str(exc.value.message)


def test_open_draft_requires_manager_count_configured():
    from app.services.draft import open_draft

    league = SimpleNamespace(
        id=1,
        status="pre_draft",
        preassign_mode="none",
        config={},
    )
    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "league_member" in sql:
            out.all.return_value = [
                SimpleNamespace(id=10, draft_slot=1),
                SimpleNamespace(id=11, draft_slot=2),
            ]
            return out
        if "team_pool" in sql:
            out.all.return_value = [_ready_pool()]
            return out
        if "pool_team" in sql or "poolteam" in sql:
            out.all.return_value = [SimpleNamespace(id=1)]
            return out
        out.first.return_value = None
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars

    with pytest.raises(ConflictError) as exc:
        open_draft(db, league)
    assert "required number of managers" in str(exc.value.message).lower()


def test_lock_ranking_lists_after_scoring():
    from app.services.sync import lock_ranking_lists_after_scoring

    league = SimpleNamespace(id=1, upset_rules={"ranking_list_key": "fifa"})
    unlocked = SimpleNamespace(key="fifa", locked=False)
    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "scoring_event" in sql:
            out.first.return_value = 1
            return out
        if "ranking_list" in sql:
            out.all.return_value = [unlocked]
            return out
        out.first.return_value = None
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars
    assert lock_ranking_lists_after_scoring(db, league) == 1
    assert unlocked.locked is True


def test_undo_last_pick_allows_complete_status():
    from app.services.draft import undo_last_pick

    league = SimpleNamespace(id=1, status="active")
    db = MagicMock()
    state = SimpleNamespace(status="complete", current_pick_number=3)
    pick = SimpleNamespace(id=99, pick_number=2, team_id=5)

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "draft_state" in sql:
            out.first.return_value = state
            return out
        if "draft_pick" in sql:
            out.first.return_value = pick
            return out
        if "roster" in sql:
            out.first.return_value = SimpleNamespace(id=1)
            return out
        if "idempotency" in sql:
            out.all.return_value = []
            return out
        out.first.return_value = None
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars
    undone = undo_last_pick(db, league)
    assert undone is pick
    assert state.status == "open"
    assert league.status == "drafting"
    assert state.current_pick_number == 2


def test_fixed_ranking_map_builds_ranks():
    from app.services.scoring import UpsetRules
    from app.services.sync import _fixed_ranking_map

    league = SimpleNamespace(id=1)
    rules = UpsetRules.from_config(
        {
            "enabled": True,
            "rank_source": "fixed_ranking_at_event_start",
            "ranking_list_key": "fifa",
            "eligibility": {"min_played": 0},
            "thresholds": [],
        }
    )
    ranking_list = SimpleNamespace(id=10, key="fifa")
    rows = [
        SimpleNamespace(team_id=1, rank=1),
        SimpleNamespace(team_id=2, rank=5),
    ]
    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "ranking_list" in sql and "team_ranking" not in sql:
            out.first.return_value = ranking_list
            return out
        if "team_ranking" in sql:
            out.all.return_value = rows
            return out
        out.first.return_value = None
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars
    ranked = _fixed_ranking_map(db, league, rules)
    assert ranked is not None
    assert ranked[1].rank == 1
    assert ranked[2].rank == 5


def test_undo_last_pick_rejects_when_pending():
    from app.services.draft import undo_last_pick

    league = SimpleNamespace(id=1, status="drafting")
    db = MagicMock()
    state = SimpleNamespace(status="pending", current_pick_number=1)
    out = MagicMock()
    out.first.return_value = state
    db.scalars.return_value = out
    with pytest.raises(ConflictError):
        undo_last_pick(db, league)


def test_reset_draft_clears_picks_keeps_preassigns():
    from app.services.draft import reset_draft

    league = SimpleNamespace(id=1, status="active")
    db = MagicMock()
    state = SimpleNamespace(status="complete", current_pick_number=5)
    pick = SimpleNamespace(id=10)
    draft_roster = SimpleNamespace(id=20, source="draft")
    commissioner_roster = SimpleNamespace(id=21, source="commissioner")
    idem_key = SimpleNamespace(id=30)
    deleted: list[object] = []

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "draft_idempotency" in sql:
            out.all.return_value = [idem_key]
            return out
        if "draft_pick" in sql:
            out.all.return_value = [pick]
            return out
        if "roster" in sql:
            out.all.return_value = [draft_roster, commissioner_roster]
            return out
        if "draft_state" in sql:
            out.first.return_value = state
            return out
        out.first.return_value = None
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars
    db.delete.side_effect = deleted.append

    result = reset_draft(db, league)
    assert result is state
    assert state.status == "pending"
    assert state.current_pick_number == 1
    assert league.status == "pre_draft"
    assert pick in deleted
    assert draft_roster in deleted
    assert commissioner_roster in deleted
    assert idem_key in deleted


def test_is_development_only_for_development_env():
    from app.config import Settings

    assert Settings(app_env="development").is_development
    assert Settings(app_env="Development").is_development
    assert not Settings(app_env="production").is_development
    assert not Settings(app_env="staging").is_development


def test_reset_league_draft_404_outside_development(monkeypatch):
    from fastapi import HTTPException

    from app.config import Settings
    from app.routers.draft import reset_league_draft

    monkeypatch.setattr(
        "app.routers.draft.get_settings",
        lambda: Settings(app_env="staging"),
    )
    with pytest.raises(HTTPException) as exc:
        reset_league_draft(
            membership=(SimpleNamespace(id=1), SimpleNamespace()),
            db=MagicMock(),
        )
    assert exc.value.status_code == 404
