"""Gap-fill seeds and cross-league scoring after shared competition sync."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.sync import (
    gap_fill_seeds_for_league,
    merge_scoring_seeds,
    score_league_after_sync,
    sync_league_fixtures,
    unscored_finished_matches,
)


def _finished_match(*, match_id: int, kickoff_hour: int, pool_id: int = 1):
    return SimpleNamespace(
        id=match_id,
        kickoff_at=datetime(2026, 8, 1, kickoff_hour, tzinfo=UTC),
        status="FINISHED",
        home_goals=1,
        away_goals=0,
        home_team_id=10,
        away_team_id=20,
        duration="REGULAR",
        scheduled_matchweek=1,
        stage=None,
        provider="football-data.org",
        competition_code="PL",
        season_year=2025,
        _pool_id=pool_id,
    )


def test_merge_scoring_seeds_dedupes_by_id():
    a = SimpleNamespace(id=1)
    b = SimpleNamespace(id=2)
    a2 = SimpleNamespace(id=1)
    assert [m.id for m in merge_scoring_seeds([a, b], [a2, b])] == [1, 2]


def test_unscored_finished_matches_filters_scored(monkeypatch):
    from app.services import sync as sync_mod

    league = SimpleNamespace(id=7)
    m1 = _finished_match(match_id=1, kickoff_hour=12)
    m2 = _finished_match(match_id=2, kickoff_hour=15)
    pool = SimpleNamespace(id=1)

    monkeypatch.setattr(sync_mod, "matches_for_league", lambda *_a, **_k: [m1, m2])
    monkeypatch.setattr(sync_mod, "pool_lookup_for_league", lambda *_a, **_k: {})
    monkeypatch.setattr(
        sync_mod,
        "pool_for_match",
        lambda *_a, **_k: pool,
    )

    db = MagicMock()
    # Only match 1 already has events
    db.scalars.return_value.all.return_value = [1]

    gaps = unscored_finished_matches(db, league)
    assert [m.id for m in gaps] == [2]


def test_gap_fill_seeds_earliest_per_pool(monkeypatch):
    from app.services import sync as sync_mod

    league = SimpleNamespace(id=7)
    early = _finished_match(match_id=11, kickoff_hour=10, pool_id=1)
    late = _finished_match(match_id=12, kickoff_hour=18, pool_id=1)
    other = _finished_match(match_id=21, kickoff_hour=12, pool_id=2)

    def fake_pool(_db, _league, match, lookup=None):
        return SimpleNamespace(id=match._pool_id)

    monkeypatch.setattr(
        sync_mod,
        "unscored_finished_matches",
        lambda *_a, **_k: [late, early, other],
    )
    monkeypatch.setattr(sync_mod, "pool_lookup_for_league", lambda *_a, **_k: {})
    monkeypatch.setattr(sync_mod, "pool_for_match", fake_pool)

    seeds = gap_fill_seeds_for_league(MagicMock(), league)
    assert sorted(m.id for m in seeds) == [11, 21]


def test_score_league_after_sync_merges_changed_and_gaps(monkeypatch):
    from app.services import sync as sync_mod

    league = SimpleNamespace(id=3, public_id=uuid4())
    changed = [_finished_match(match_id=5, kickoff_hour=16)]
    gap_seed = _finished_match(match_id=2, kickoff_hour=10)
    seen: dict[str, list[int]] = {}

    monkeypatch.setattr(sync_mod, "gap_fill_seeds_for_league", lambda *_a, **_k: [gap_seed])

    def fake_score(_db, _league, seeds):
        seen["seeds"] = [m.id for m in seeds]
        return {"scored": 2, "cascaded": 2, "skipped_missing_snapshot": 0}

    monkeypatch.setattr(sync_mod, "score_changed_matches", fake_score)

    summary = score_league_after_sync(MagicMock(), league, changed)
    assert seen["seeds"] == [5, 2]
    assert summary["gap_fill_seeds"] == 1
    assert summary["seed_count"] == 2
    assert summary["scored"] == 2


def test_sync_league_fixtures_scores_sibling_leagues(monkeypatch):
    from app.services import sync as sync_mod

    league_a = SimpleNamespace(id=1, public_id=uuid4(), upset_rules={})
    league_b = SimpleNamespace(id=2, public_id=uuid4(), upset_rules={})
    pool = SimpleNamespace(
        id=1,
        key="pl",
        scores_match_results=True,
        provider="football-data.org",
        competition_code="PL",
        season_year=2025,
    )
    changed = [_finished_match(match_id=99, kickoff_hour=14)]
    scored_league_ids: list[int] = []

    db = MagicMock()
    db.scalars.return_value.all.return_value = [pool]

    monkeypatch.setattr(
        sync_mod,
        "sync_competition_fixtures",
        lambda *_a, **_k: {
            "ok": True,
            "created": 0,
            "updated": 1,
            "skipped_missing_teams": 0,
            "changed_matches": changed,
        },
    )
    monkeypatch.setattr(
        sync_mod,
        "leagues_sharing_competition_keys",
        lambda *_a, **_k: [league_a, league_b],
    )

    def fake_score(_db, target, seeds):
        scored_league_ids.append(target.id)
        assert [m.id for m in seeds] == [99]
        return {
            "scored": 1,
            "cascaded": 1,
            "skipped_missing_snapshot": 0,
            "gap_fill_seeds": 0,
            "seed_count": 1,
        }

    monkeypatch.setattr(sync_mod, "score_league_after_sync", fake_score)
    monkeypatch.setattr(
        "app.services.draft_schedule.clear_draft_schedule_if_after_first_kickoff",
        lambda *_a, **_k: False,
    )

    result = sync_league_fixtures(db, league_a, provider=MagicMock())
    assert result["ok"] is True
    assert scored_league_ids == [1, 2]
    assert result["sibling_leagues_scored"] == 1
    assert result["scored"] == 1
    assert result["changed"] == 1
