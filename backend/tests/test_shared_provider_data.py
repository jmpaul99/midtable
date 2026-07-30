"""Shared fixtures / standings / ranking freeze behavior."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.models import Match
from app.services import ranking_catalog as ranking_catalog_mod
from app.services import standings as standings_mod
from app.services.match_adapters import match_to_input
from app.services.match_queries import competition_keys_from_pools
from app.services.ranking_catalog import (
    ensure_or_create_ranking_freeze,
    ranks_for_league,
)
from app.services.scoring import UpsetRules
from app.services.sync import sync_all_active_competitions_then_score


def test_competition_keys_dedupe_pools():
    pools = [
        SimpleNamespace(
            provider="football-data.org",
            competition_code="PL",
            season_year=2025,
        ),
        SimpleNamespace(
            provider="football-data.org",
            competition_code="PL",
            season_year=2025,
        ),
        SimpleNamespace(
            provider="football-data.org",
            competition_code="CL",
            season_year=2025,
        ),
        SimpleNamespace(
            provider="football-data.org",
            competition_code=None,
            season_year=2025,
        ),
    ]
    keys = competition_keys_from_pools(pools)
    assert keys == [
        ("football-data.org", "PL", 2025),
        ("football-data.org", "CL", 2025),
    ]


def test_match_model_has_no_league_or_pool():
    cols = {c.key for c in Match.__table__.columns}
    assert "league_id" not in cols
    assert "pool_id" not in cols
    assert "competition_code" in cols
    assert "season_year" in cols


def test_match_to_input_requires_pool_context():
    match = SimpleNamespace(
        id=1,
        home_team_id=10,
        away_team_id=20,
        kickoff_at=datetime(2026, 8, 1, tzinfo=UTC),
        home_goals=1,
        away_goals=0,
        status="FINISHED",
        duration="REGULAR",
        scheduled_matchweek=1,
        stage=None,
    )
    mi = match_to_input(match, pool_id=99)
    assert mi.pool_id == 99
    assert mi.match_id == 1


def test_ranks_for_league_uses_freeze_when_locked():
    league = SimpleNamespace(id=1)
    rules = UpsetRules.from_config(
        {
            "enabled": True,
            "rank_source": "fixed_ranking_at_event_start",
            "ranking_list_key": "fifa_men",
            "eligibility": {"min_played": 0},
            "thresholds": [],
        }
    )
    ranking_list = SimpleNamespace(
        id=10,
        key="fifa_men",
        locked=True,
        freeze_id=5,
        source="parse_fifa",
    )
    freeze_rows = [
        SimpleNamespace(team_id=1, rank=3),
        SimpleNamespace(team_id=2, rank=7),
    ]
    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "ranking_list" in sql:
            out.first.return_value = ranking_list
            return out
        if "ranking_catalog" in sql:
            out.first.return_value = SimpleNamespace(id=1, key="fifa_men", as_of=None)
            return out
        if "ranking_freeze_entr" in sql or "rankingfreezeentry" in sql:
            out.all.return_value = freeze_rows
            return out
        out.first.return_value = None
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars
    ranked = ranks_for_league(db, league, rules)
    assert ranked is not None
    assert ranked[1].rank == 3
    assert ranked[2].rank == 7


def test_ranks_for_league_uses_shared_freeze_without_league_lock():
    """Unlocked lists still read the catalog freeze — never live fuzzy match."""
    league = SimpleNamespace(id=1)
    rules = UpsetRules.from_config(
        {
            "enabled": True,
            "rank_source": "fixed_ranking_at_event_start",
            "ranking_list_key": "fifa_men",
            "eligibility": {"min_played": 0},
            "thresholds": [],
        }
    )
    ranking_list = SimpleNamespace(
        id=10,
        key="fifa_men",
        locked=False,
        freeze_id=None,
        source="parse_fifa",
    )
    catalog = SimpleNamespace(id=1, key="fifa_men", as_of=date(2026, 1, 1))
    shared_freeze = SimpleNamespace(id=9, catalog_id=1, as_of=date(2026, 1, 1))
    freeze_rows = [SimpleNamespace(team_id=1, rank=2)]
    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "ranking_list" in sql:
            out.first.return_value = ranking_list
            return out
        if "ranking_catalog" in sql and "freeze" not in sql:
            out.first.return_value = catalog
            return out
        if "ranking_freeze" in sql and "entr" not in sql:
            out.first.return_value = shared_freeze
            return out
        if "ranking_freeze_entr" in sql or "rankingfreezeentry" in sql:
            out.all.return_value = freeze_rows
            return out
        out.first.return_value = None
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars
    ranked = ranks_for_league(db, league, rules)
    assert ranked is not None
    assert ranked[1].rank == 2


def test_ranks_for_league_live_catalog_is_scoring_opt_in(monkeypatch):
    league = SimpleNamespace(id=1)
    rules = UpsetRules.from_config(
        {
            "enabled": True,
            "rank_source": "fixed_ranking_at_event_start",
            "ranking_list_key": "fifa_men",
            "eligibility": {"min_played": 0},
            "thresholds": [],
        }
    )
    ranking_list = SimpleNamespace(
        id=10,
        key="fifa_men",
        locked=False,
        freeze_id=None,
        source="parse_fifa",
    )
    catalog = SimpleNamespace(id=1, key="fifa_men", as_of=None)
    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "ranking_list" in sql:
            out.first.return_value = ranking_list
        elif "ranking_catalog" in sql:
            out.first.return_value = catalog
        else:
            out.all.return_value = []
        return out

    db.scalars.side_effect = scalars
    resolve = MagicMock(return_value={7: 4})
    monkeypatch.setattr(ranking_catalog_mod, "resolve_catalog_team_ranks", resolve)

    assert ranks_for_league(db, league, rules) is None
    resolve.assert_not_called()

    ranked = ranks_for_league(db, league, rules, allow_live_catalog=True)
    assert ranked is not None
    assert ranked[7].rank == 4
    resolve.assert_called_once_with(db, catalog, sample_league=league)


def test_previous_final_requires_zeroed_opener(monkeypatch):
    midseason = SimpleNamespace(
        kickoff_at=datetime(2026, 9, 1, tzinfo=UTC),
        rows=[SimpleNamespace(played=3)],
    )
    monkeypatch.setattr(
        standings_mod,
        "_snapshots_for_competition",
        MagicMock(return_value=[midseason]),
    )

    assert (
        standings_mod.previous_final_snapshot_for_competition(
            MagicMock(),
            provider="football-data.org",
            competition_code="PL",
            season_year=2026,
        )
        is None
    )


def test_previous_final_precedes_zeroed_opener(monkeypatch):
    previous_final = SimpleNamespace(
        kickoff_at=datetime(2026, 6, 1, tzinfo=UTC),
        rows=[SimpleNamespace(played=38)],
    )
    opener = SimpleNamespace(
        kickoff_at=datetime(2026, 8, 1, tzinfo=UTC),
        rows=[SimpleNamespace(played=0)],
    )
    midseason = SimpleNamespace(
        kickoff_at=datetime(2026, 9, 1, tzinfo=UTC),
        rows=[SimpleNamespace(played=3)],
    )
    monkeypatch.setattr(
        standings_mod,
        "_snapshots_for_competition",
        MagicMock(return_value=[previous_final, opener, midseason]),
    )

    result = standings_mod.previous_final_snapshot_for_competition(
        MagicMock(),
        provider="football-data.org",
        competition_code="PL",
        season_year=2026,
    )

    assert result is previous_final


def test_ensure_or_create_ranking_freeze_reuses_existing(monkeypatch):
    catalog = SimpleNamespace(id=9, key="fifa_men", as_of=date(2026, 1, 1))
    existing = SimpleNamespace(id=3, catalog_id=9, as_of=date(2026, 1, 1))
    db = MagicMock()
    out = MagicMock()
    out.first.return_value = existing
    db.scalars.return_value = out

    freeze = ensure_or_create_ranking_freeze(db, catalog)
    assert freeze is existing
    db.add.assert_not_called()


def test_sync_all_active_competitions_calls_provider_once_per_competition(monkeypatch):
    from app.services import sync as sync_mod

    league_a = SimpleNamespace(id=1, public_id=uuid4(), upset_rules={})
    league_b = SimpleNamespace(id=2, public_id=uuid4(), upset_rules={})
    pool = SimpleNamespace(
        id=10,
        provider="football-data.org",
        competition_code="PL",
        season_year=2025,
        scores_match_results=True,
    )

    calls: list[tuple[str, int]] = []

    def fake_sync(db, provider, *, provider_key, competition_code, season_year):
        calls.append((competition_code, season_year))
        return {
            "ok": True,
            "created": 0,
            "updated": 0,
            "skipped_missing_teams": 0,
            "changed_matches": [],
        }

    monkeypatch.setattr(sync_mod, "sync_competition_fixtures", fake_sync)
    monkeypatch.setattr(sync_mod, "ensure_fixed_ranking_for_league", lambda *_a, **_k: None)
    monkeypatch.setattr(
        sync_mod,
        "scoring_pools_for_league",
        lambda *_a, **_k: [pool],
    )
    monkeypatch.setattr(
        sync_mod,
        "score_changed_matches",
        lambda *_a, **_k: {"scored": 0, "cascaded": 0, "skipped_missing_snapshot": 0},
    )

    db = MagicMock()
    payload = sync_all_active_competitions_then_score(db, MagicMock(), [league_a, league_b])
    assert payload["ok"] is True
    assert calls == [("PL", 2025)]
    assert len(payload["leagues"]) == 2


def test_scoring_event_unique_includes_league():
    from app.models import ScoringEvent

    args = ScoringEvent.__table_args__
    # UniqueConstraint is first table arg
    uc = args[0] if isinstance(args, tuple) else args
    cols = list(uc.columns.keys()) if hasattr(uc, "columns") else list(uc._pending_colargs)
    assert "league_id" in cols
    assert "match_id" in cols
