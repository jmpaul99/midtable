"""Gap-fill seeds and cross-league scoring after shared competition sync."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.scoring.engine import (
    MatchInput,
    RankedTeam,
    ResultPoints,
    UpsetRules,
    score_match_events,
)
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


def test_gap_fill_seeds_all_unscored(monkeypatch):
    from app.services import sync as sync_mod

    league = SimpleNamespace(id=7)
    early = _finished_match(match_id=11, kickoff_hour=10, pool_id=1)
    late = _finished_match(match_id=12, kickoff_hour=18, pool_id=1)

    def fake_pool(_db, _league, match, lookup=None):
        return SimpleNamespace(id=match._pool_id)

    monkeypatch.setattr(
        sync_mod,
        "unscored_finished_matches",
        lambda *_a, **_k: [late, early],
    )
    monkeypatch.setattr(sync_mod, "pool_lookup_for_league", lambda *_a, **_k: {})
    monkeypatch.setattr(sync_mod, "pool_for_match", fake_pool)

    seeds = gap_fill_seeds_for_league(MagicMock(), league, all_unscored=True)
    assert [m.id for m in seeds] == [11, 12]


def test_score_league_after_sync_merges_changed_and_gaps(monkeypatch):
    from app.services import sync as sync_mod

    league = SimpleNamespace(id=3, public_id=uuid4())
    changed = [_finished_match(match_id=5, kickoff_hour=16)]
    gap_seed = _finished_match(match_id=2, kickoff_hour=10)
    seen: dict[str, list[int]] = {}
    gap_calls = {"n": 0}

    def fake_gap(_db, _league, all_unscored=False):
        gap_calls["n"] += 1
        # After first scoring pass, earliest seed is no longer stuck.
        if gap_calls["n"] == 1:
            return [gap_seed]
        return []

    monkeypatch.setattr(sync_mod, "gap_fill_seeds_for_league", fake_gap)

    def fake_score(_db, _league, seeds):
        seen["seeds"] = [m.id for m in seeds]
        return {"scored": 2, "cascaded": 2, "skipped_missing_snapshot": 0}

    monkeypatch.setattr(sync_mod, "score_changed_matches", fake_score)

    summary = score_league_after_sync(MagicMock(), league, changed)
    assert seen["seeds"] == [5, 2]
    assert summary["gap_fill_seeds"] == 1
    assert summary["seed_count"] == 2
    assert summary["scored"] == 2


def test_score_league_after_sync_unblocks_later_when_earliest_stuck(monkeypatch):
    """Earliest gap seed that stays unscored must not leave later fixtures unseeded."""
    from app.services import sync as sync_mod

    league = SimpleNamespace(id=3, public_id=uuid4())
    early = _finished_match(match_id=10, kickoff_hour=10)
    late = _finished_match(match_id=20, kickoff_hour=16)
    calls: list[list[int]] = []

    def fake_gap(_db, _league, all_unscored=False):
        if all_unscored:
            return [early, late]
        # Earliest remains stuck after the first scoring pass.
        return [early]

    monkeypatch.setattr(sync_mod, "gap_fill_seeds_for_league", fake_gap)

    def fake_score(_db, _league, seeds):
        calls.append([m.id for m in seeds])
        return {
            "scored": len(seeds),
            "cascaded": len(seeds),
            "skipped_missing_snapshot": 0,
        }

    monkeypatch.setattr(sync_mod, "score_changed_matches", fake_score)

    summary = score_league_after_sync(MagicMock(), league, [])
    assert calls == [[10], [20]]
    assert summary["scored"] == 2
    assert summary["gap_fill_seeds"] == 2
    assert summary["seed_count"] == 2


def test_zero_point_result_yields_no_fantasy_events():
    """Empty score_match_events is the stuck-seed condition; sync writes a marker."""
    ranked = {
        10: RankedTeam(team_id=10, rank=1, played=10),
        20: RankedTeam(team_id=20, rank=2, played=10),
    }
    zero = ResultPoints(win=Decimal(0), draw=Decimal(0), loss=Decimal(0))
    rules = UpsetRules(
        enabled=False,
        rank_source="league_table_at_kickoff",
        min_played=0,
        thresholds=(),
    )
    match = MatchInput(
        match_id=1,
        pool_id=1,
        home_team_id=10,
        away_team_id=20,
        kickoff_at=datetime(2026, 8, 29, 12, tzinfo=UTC),
        home_goals=1,
        away_goals=0,
        status="FINISHED",
        duration="REGULAR",
    )
    assert score_match_events(match, ranked, result_points=zero, upset_rules=rules) == ()


def test_rescore_writes_processed_marker_for_zero_point_results():
    from app.services.sync import _rescore_plan_matches

    league = SimpleNamespace(id=1, public_id=uuid4())
    pool = SimpleNamespace(
        id=7,
        competition_code="PL",
        season_year=2026,
        provider="football-data.org",
    )
    match = _finished_match(match_id=42, kickoff_hour=15)
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    added: list[object] = []
    db.add.side_effect = lambda obj: added.append(obj)

    scored, skipped, _ids = _rescore_plan_matches(
        db,
        league=league,
        pool=pool,
        plan_match_ids=[42],
        by_id={42: match},
        result_points=ResultPoints(win=Decimal(0), draw=Decimal(0), loss=Decimal(0)),
        upset_rules=UpsetRules(enabled=False, min_played=0, thresholds=()),
        fixed_ranks={
            10: RankedTeam(team_id=10, rank=1, played=8),
            20: RankedTeam(team_id=20, rank=2, played=8),
        },
    )
    assert scored == 1
    assert skipped == 0
    assert len(added) == 1
    assert added[0].event_type == "processed"
    assert added[0].points == Decimal(0)


def test_sync_competition_keeps_finished_goals_when_list_payload_null(monkeypatch):
    """Thin list re-sync must not wipe known FINISHED scores back to null."""
    from datetime import UTC, datetime
    from app.providers.base import ProviderMatch
    from app.services import sync as sync_mod

    status = SimpleNamespace(
        in_progress=False,
        in_progress_since=None,
        last_error=None,
        last_sync_at=None,
        last_summary=None,
        requests_available_minute=None,
    )
    existing = SimpleNamespace(
        id=9,
        provider="football-data.org",
        competition_code="PL",
        season_year=2026,
        external_id="501",
        home_team_id=1,
        away_team_id=2,
        kickoff_at=datetime(2026, 8, 29, 14, tzinfo=UTC),
        status="FINISHED",
        home_goals=1,
        away_goals=1,
        duration="REGULAR",
        scheduled_matchweek=3,
        stage="REGULAR_SEASON",
        last_synced_at=None,
    )
    db = MagicMock()
    db.scalars.return_value.first.return_value = existing
    provider = MagicMock()
    provider.list_matches.return_value = (
        [
            ProviderMatch(
                external_id="501",
                home_external_id="10",
                away_external_id="20",
                kickoff_at=datetime(2026, 8, 29, 14, tzinfo=UTC),
                status="FINISHED",
                home_goals=None,
                away_goals=None,
                matchday=3,
                stage="REGULAR_SEASON",
                duration="REGULAR",
            )
        ],
        None,
    )
    monkeypatch.setattr(sync_mod, "_ensure_sync_status", lambda *_a, **_k: status)
    monkeypatch.setattr(
        sync_mod,
        "_team_by_external",
        lambda *_a, **_k: SimpleNamespace(id=1),
    )
    import app.services.standings as standings_mod

    monkeypatch.setattr(
        standings_mod,
        "ensure_competition_season_table_baselines",
        lambda *_a, **_k: None,
    )

    result = sync_mod.sync_competition_fixtures(
        db,
        provider,
        provider_key="football-data.org",
        competition_code="PL",
        season_year=2026,
    )
    assert result["ok"] is True
    assert existing.home_goals == 1
    assert existing.away_goals == 1
    assert result["changed"] == 0
    assert result["updated"] == 0


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
