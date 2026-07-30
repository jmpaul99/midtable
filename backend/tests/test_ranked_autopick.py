"""Ranked draft autopick, table baselines, and competition tiers."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.providers.base import CompetitionSeasonInfo, ProviderStandingRow, RateLimitInfo
from app.providers.football_data import FootballDataError, FootballDataProvider
from app.services.competitions import domestic_tier_for_competition
from app.services.draft import select_autopick_team
from app.services.standings import (
    ensure_competition_season_table_baselines,
    oldest_snapshot_for_competition,
)


def test_domestic_tier_catalog():
    assert domestic_tier_for_competition("PL") == 1
    assert domestic_tier_for_competition("pd") == 1
    assert domestic_tier_for_competition("ELC") == 2
    assert domestic_tier_for_competition("CL") is None
    assert domestic_tier_for_competition("WC") is None
    assert domestic_tier_for_competition(None) is None


def test_draft_timer_freezes_rankings_before_autopick(monkeypatch):
    from app.services import draft as draft_mod

    calls: list[str] = []
    league = SimpleNamespace(status="drafting")

    monkeypatch.setattr(
        draft_mod, "try_auto_open_if_scheduled", lambda db, item: False
    )

    def freeze(db, item):  # noqa: ARG001
        calls.append("freeze")
        return True

    def auto_pick(db, item):  # noqa: ARG001
        calls.append("autopick")
        return "noop"

    monkeypatch.setattr(draft_mod, "ensure_draft_ranking_freeze", freeze)
    monkeypatch.setattr(draft_mod, "try_auto_pick_if_expired", auto_pick)

    outcome = draft_mod.enforce_league_draft_timers(MagicMock(), league)

    assert calls == ["freeze", "autopick"]
    assert outcome["frozen"] is True
    assert outcome["changed"] is True


def test_list_standings_prefers_total_null_group():
    provider = FootballDataProvider(api_token="test", client=MagicMock())
    payload = {
        "standings": [
            {
                "type": "HOME",
                "group": None,
                "table": [{"position": 1, "team": {"id": 1, "name": "Home"}, "playedGames": 1}],
            },
            {
                "type": "TOTAL",
                "group": "GROUP_A",
                "table": [
                    {
                        "position": 2,
                        "team": {"id": 99, "name": "Grouped"},
                        "playedGames": 10,
                        "points": 20,
                        "goalsFor": 15,
                        "goalsAgainst": 5,
                        "goalDifference": 10,
                    }
                ],
            },
            {
                "type": "TOTAL",
                "group": None,
                "table": [
                    {
                        "position": 1,
                        "team": {"id": 57, "name": "Arsenal"},
                        "playedGames": 38,
                        "points": 84,
                        "goalsFor": 88,
                        "goalsAgainst": 30,
                        "goalDifference": 58,
                    },
                    {
                        "position": 2,
                        "team": {"id": 65, "name": "Man City"},
                        "playedGames": 38,
                        "points": 80,
                        "goalsFor": 90,
                        "goalsAgainst": 40,
                        "goalDifference": 50,
                    },
                ],
            },
        ]
    }
    provider._get = MagicMock(return_value=(payload, RateLimitInfo()))  # type: ignore[method-assign]
    rows, _ = provider.list_standings("PL", 2024)
    assert [r.external_team_id for r in rows] == ["57", "65"]
    assert rows[0].points == 84
    assert rows[0].position == 1


def test_list_standings_merges_multi_group_total_blocks():
    provider = FootballDataProvider(api_token="test", client=MagicMock())
    payload = {
        "standings": [
            {
                "type": "TOTAL",
                "group": "GROUP_A",
                "table": [
                    {
                        "position": 1,
                        "team": {"id": 1, "name": "A1"},
                        "playedGames": 6,
                        "points": 12,
                        "goalsFor": 10,
                        "goalsAgainst": 4,
                        "goalDifference": 6,
                    },
                    {
                        "position": 2,
                        "team": {"id": 2, "name": "A2"},
                        "playedGames": 6,
                        "points": 9,
                        "goalsFor": 8,
                        "goalsAgainst": 5,
                        "goalDifference": 3,
                    },
                ],
            },
            {
                "type": "TOTAL",
                "group": "GROUP_B",
                "table": [
                    {
                        "position": 1,
                        "team": {"id": 3, "name": "B1"},
                        "playedGames": 6,
                        "points": 15,
                        "goalsFor": 12,
                        "goalsAgainst": 3,
                        "goalDifference": 9,
                    },
                    {
                        "position": 2,
                        "team": {"id": 4, "name": "B2"},
                        "playedGames": 6,
                        "points": 7,
                        "goalsFor": 5,
                        "goalsAgainst": 6,
                        "goalDifference": -1,
                    },
                ],
            },
        ]
    }
    provider._get = MagicMock(return_value=(payload, RateLimitInfo()))  # type: ignore[method-assign]
    rows, _ = provider.list_standings("CL", 2024)
    assert [r.external_team_id for r in rows] == ["1", "3", "2", "4"]
    assert {r.external_team_id for r in rows} == {"1", "2", "3", "4"}


def test_list_standings_merges_non_total_blocks_when_total_missing():
    provider = FootballDataProvider(api_token="test", client=MagicMock())
    payload = {
        "standings": [
            {
                "type": "HOME",
                "group": "GROUP_A",
                "table": [
                    {
                        "position": 1,
                        "team": {"id": 10, "name": "Home A"},
                        "playedGames": 3,
                        "points": 9,
                        "goalsFor": 5,
                        "goalsAgainst": 1,
                        "goalDifference": 4,
                    }
                ],
            },
            {
                "type": "HOME",
                "group": "GROUP_B",
                "table": [
                    {
                        "position": 1,
                        "team": {"id": 20, "name": "Home B"},
                        "playedGames": 3,
                        "points": 6,
                        "goalsFor": 4,
                        "goalsAgainst": 2,
                        "goalDifference": 2,
                    }
                ],
            },
        ]
    }
    provider._get = MagicMock(return_value=(payload, RateLimitInfo()))  # type: ignore[method-assign]
    rows, _ = provider.list_standings("FAC", 2024)
    assert [r.external_team_id for r in rows] == ["10", "20"]


def test_ensure_baselines_skips_previous_standings_when_cached():
    db = MagicMock()
    existing = SimpleNamespace(
        rows=[SimpleNamespace(team_id=1, played=38)],
        kickoff_at=datetime(2025, 5, 26, tzinfo=UTC),
    )
    # oldest_snapshot returns existing; zeroed path needs resolve + _snapshot_at None + teams
    call_count = {"n": 0}

    def scalars_side_effect(stmt):  # noqa: ARG001
        call_count["n"] += 1
        result = MagicMock()
        # First call inside oldest_snapshot_for_competition
        if call_count["n"] == 1:
            result.first.return_value = existing
            result.all.return_value = [existing]
        else:
            result.first.return_value = SimpleNamespace(
                id=10, rows=[], kickoff_at=datetime(2025, 8, 15, tzinfo=UTC)
            )
            result.all.return_value = []
        return result

    db.scalars.side_effect = scalars_side_effect

    provider = MagicMock()
    provider.list_standings = MagicMock(
        side_effect=AssertionError("should not call list_standings when cached")
    )
    provider.resolve_competition_season.return_value = (
        CompetitionSeasonInfo(
            code="PL",
            season_year=2025,
            start_date=datetime(2025, 8, 15, tzinfo=UTC),
            end_date=datetime(2026, 5, 24, tzinfo=UTC),
            available=True,
        ),
        RateLimitInfo(),
    )

    # Patch oldest to return existing with rows so previous fetch is skipped.
    from app.services import standings as standings_mod

    original_oldest = standings_mod.oldest_snapshot_for_competition
    original_snapshot_at = standings_mod._snapshot_at
    original_teams = standings_mod._teams_for_competition_season

    standings_mod.oldest_snapshot_for_competition = lambda *a, **k: existing  # type: ignore[assignment]
    standings_mod._snapshot_at = lambda *a, **k: SimpleNamespace(id=1)  # type: ignore[assignment]
    standings_mod._teams_for_competition_season = lambda *a, **k: []  # type: ignore[assignment]
    try:
        out = ensure_competition_season_table_baselines(
            db,
            provider,
            provider_key="football-data.org",
            competition_code="PL",
            season_year=2025,
        )
        assert out["created_previous_final"] is False
        provider.list_standings.assert_not_called()
    finally:
        standings_mod.oldest_snapshot_for_competition = original_oldest  # type: ignore[assignment]
        standings_mod._snapshot_at = original_snapshot_at  # type: ignore[assignment]
        standings_mod._teams_for_competition_season = original_teams  # type: ignore[assignment]


def test_ensure_baselines_reraises_rate_limited_standings():
    db = MagicMock()
    provider = MagicMock()
    provider.resolve_competition_season.return_value = (
        CompetitionSeasonInfo(
            code="PL",
            season_year=2025,
            start_date=None,
            end_date=datetime(2026, 5, 24, tzinfo=UTC),
            available=True,
        ),
        RateLimitInfo(),
    )
    provider.list_standings.side_effect = FootballDataError(
        "rate limit exceeded",
        RateLimitInfo(retry_after_seconds=30),
        rate_limited=True,
    )

    from app.services import standings as standings_mod

    original_oldest = standings_mod.oldest_snapshot_for_competition
    standings_mod.oldest_snapshot_for_competition = lambda *a, **k: None  # type: ignore[assignment]
    try:
        with pytest.raises(FootballDataError) as exc_info:
            ensure_competition_season_table_baselines(
                db,
                provider,
                provider_key="football-data.org",
                competition_code="PL",
                season_year=2026,
            )
        assert exc_info.value.rate_limited is True
    finally:
        standings_mod.oldest_snapshot_for_competition = original_oldest  # type: ignore[assignment]


def test_ensure_baselines_fetches_previous_when_missing(monkeypatch):
    db = MagicMock()
    created: dict[str, object] = {}

    def fake_oldest(*_a, **_k):
        return None

    def fake_snapshot_at(*_a, **_k):
        return None

    def fake_upsert(*_a, **kwargs):
        created.setdefault("calls", []).append(
            {"kickoff": kwargs["kickoff_at"], "rows": kwargs["rows"]}
        )
        return SimpleNamespace(id=1, rows=kwargs["rows"])

    def fake_teams(*_a, **_k):
        return [
            SimpleNamespace(id=10, name="Arsenal"),
            SimpleNamespace(id=11, name="Burnley"),
        ]

    provider = MagicMock()
    provider.resolve_competition_season.side_effect = [
        (
            CompetitionSeasonInfo(
                code="PL",
                season_year=2024,
                start_date=datetime(2024, 8, 16, tzinfo=UTC),
                end_date=datetime(2025, 5, 25, tzinfo=UTC),
                available=True,
            ),
            RateLimitInfo(),
        ),
        (
            CompetitionSeasonInfo(
                code="PL",
                season_year=2025,
                start_date=datetime(2025, 8, 15, tzinfo=UTC),
                end_date=datetime(2026, 5, 24, tzinfo=UTC),
                available=True,
            ),
            RateLimitInfo(),
        ),
    ]
    provider.list_standings.return_value = (
        [
            ProviderStandingRow(
                external_team_id="57",
                position=1,
                played=38,
                points=84,
                goals_for=88,
                goals_against=30,
                goal_difference=58,
                team_name="Arsenal",
            )
        ],
        RateLimitInfo(),
    )

    from app.services import standings as standings_mod

    monkeypatch.setattr(standings_mod, "oldest_snapshot_for_competition", fake_oldest)
    monkeypatch.setattr(standings_mod, "_snapshot_at", fake_snapshot_at)
    monkeypatch.setattr(standings_mod, "_upsert_snapshot_with_rows", fake_upsert)
    monkeypatch.setattr(standings_mod, "_teams_for_competition_season", fake_teams)
    monkeypatch.setattr(
        standings_mod,
        "_map_standing_rows_to_local",
        lambda *_a, **_k: [(10, 1, 38, 84, 88, 30, 58)],
    )

    out = ensure_competition_season_table_baselines(
        db,
        provider,
        provider_key="football-data.org",
        competition_code="PL",
        season_year=2025,
    )
    assert out["created_previous_final"] is True
    assert out["created_zeroed_opener"] is True
    provider.list_standings.assert_called_once_with("PL", 2024)
    calls = created["calls"]
    assert len(calls) == 2
    assert calls[0]["kickoff"] == datetime(2025, 5, 26, tzinfo=UTC)
    assert calls[0]["rows"] == [(10, 1, 38, 84, 88, 30, 58)]
    assert calls[1]["kickoff"] == datetime(2025, 8, 15, tzinfo=UTC)
    assert len(calls[1]["rows"]) == 2


def _team(name: str, *, tid: int, code: str = "PL"):
    return SimpleNamespace(
        id=tid,
        name=name,
        public_id=uuid4(),
        crest_url=None,
    ), SimpleNamespace(
        id=tid + 100,
        public_id=uuid4(),
        competition_code=code,
        provider="football-data.org",
        season_year=2025,
        slot_count=1,
    )


def _table_state(previous: dict, opener_ids: set[int] | None):
    from app.services.draft import CompetitionTableState

    return CompetitionTableState(
        previous_rows=previous,
        opener_ids=None if opener_ids is None else frozenset(opener_ids),
    )


def test_select_autopick_table_prefers_rank_one(monkeypatch):
    arsenal, pool = _team("Arsenal", tid=1)
    burnley, _ = _team("Burnley", tid=2)
    candidates = [(burnley, pool), (arsenal, pool)]
    rows = {
        ("PL", 2025): _table_state(
            {
                1: SimpleNamespace(rank=1, points=84, goal_difference=58, goals_for=88),
                2: SimpleNamespace(rank=17, points=35, goal_difference=-20, goals_for=40),
            },
            {1, 2},
        )
    }
    monkeypatch.setattr(
        "app.services.draft._available_candidates",
        lambda *_a, **_k: candidates,
    )
    monkeypatch.setattr(
        "app.services.draft._table_row_lookup",
        lambda *_a, **_k: rows,
    )
    monkeypatch.setattr(
        "app.services.draft.resolve_domestic_tiers",
        lambda *_a, **_k: {"PL": 1},
    )
    league = SimpleNamespace(
        upset_rules={"rank_source": "league_table_at_kickoff"},
    )
    selection = select_autopick_team(
        MagicMock(),
        league=league,
        member=SimpleNamespace(id=1),
        pools=[pool],
    )
    assert selection is not None
    assert selection.mode == "table"
    assert selection.team is arsenal


def test_select_autopick_unranked_alpha_last(monkeypatch):
    arsenal, pool = _team("Arsenal", tid=1)
    leeds, _ = _team("Leeds", tid=2)  # promoted / missing from snapshot
    zteam, _ = _team("Zulu FC", tid=3)
    candidates = [(leeds, pool), (zteam, pool), (arsenal, pool)]
    rows = {
        ("PL", 2025): _table_state(
            {
                1: SimpleNamespace(rank=1, points=84, goal_difference=58, goals_for=88),
            },
            {1, 2, 3},  # leeds + zulu are new to PL
        )
    }
    monkeypatch.setattr(
        "app.services.draft._available_candidates",
        lambda *_a, **_k: candidates,
    )
    monkeypatch.setattr(
        "app.services.draft._table_row_lookup",
        lambda *_a, **_k: rows,
    )
    monkeypatch.setattr(
        "app.services.draft.resolve_domestic_tiers",
        lambda *_a, **_k: {"PL": 1},
    )
    league = SimpleNamespace(upset_rules={"rank_source": "league_table_at_kickoff"})
    selection = select_autopick_team(
        MagicMock(),
        league=league,
        member=SimpleNamespace(id=1),
        pools=[pool],
    )
    assert selection is not None
    assert selection.team is arsenal

    # Only unranked left → alphabetical
    monkeypatch.setattr(
        "app.services.draft._available_candidates",
        lambda *_a, **_k: [(zteam, pool), (leeds, pool)],
    )
    selection2 = select_autopick_team(
        MagicMock(),
        league=league,
        member=SimpleNamespace(id=1),
        pools=[pool],
    )
    assert selection2 is not None
    assert selection2.team is leeds


def test_select_autopick_tier_one_before_tier_two(monkeypatch):
    pl_20th, pl_pool = _team("Wolves", tid=1, code="PL")
    elc_1st, elc_pool = _team("Leicester", tid=2, code="ELC")
    candidates = [(elc_1st, elc_pool), (pl_20th, pl_pool)]
    rows = {
        ("PL", 2025): _table_state(
            {
                1: SimpleNamespace(rank=20, points=25, goal_difference=-30, goals_for=30),
            },
            {1},
        ),
        ("ELC", 2025): _table_state(
            {
                2: SimpleNamespace(rank=1, points=90, goal_difference=40, goals_for=80),
            },
            {2},
        ),
    }
    monkeypatch.setattr(
        "app.services.draft._available_candidates",
        lambda *_a, **_k: candidates,
    )
    monkeypatch.setattr(
        "app.services.draft._table_row_lookup",
        lambda *_a, **_k: rows,
    )
    monkeypatch.setattr(
        "app.services.draft.resolve_domestic_tiers",
        lambda *_a, **_k: {"PL": 1, "ELC": 2},
    )
    league = SimpleNamespace(upset_rules={"rank_source": "league_table_at_kickoff"})
    selection = select_autopick_team(
        MagicMock(),
        league=league,
        member=SimpleNamespace(id=1),
        pools=[pl_pool, elc_pool],
    )
    assert selection is not None
    assert selection.team is pl_20th


def test_select_autopick_same_tier_interleaves_by_rank(monkeypatch):
    pl_2nd, pl_pool = _team("Arsenal", tid=1, code="PL")
    pd_1st, pd_pool = _team("Real Madrid", tid=2, code="PD")
    candidates = [(pl_2nd, pl_pool), (pd_1st, pd_pool)]
    rows = {
        ("PL", 2025): _table_state(
            {
                1: SimpleNamespace(rank=2, points=80, goal_difference=50, goals_for=70),
            },
            {1},
        ),
        ("PD", 2025): _table_state(
            {
                2: SimpleNamespace(rank=1, points=88, goal_difference=55, goals_for=75),
            },
            {2},
        ),
    }
    monkeypatch.setattr(
        "app.services.draft._available_candidates",
        lambda *_a, **_k: candidates,
    )
    monkeypatch.setattr(
        "app.services.draft._table_row_lookup",
        lambda *_a, **_k: rows,
    )
    monkeypatch.setattr(
        "app.services.draft.resolve_domestic_tiers",
        lambda *_a, **_k: {"PL": 1, "PD": 1},
    )
    league = SimpleNamespace(upset_rules={"rank_source": "league_table_at_kickoff"})
    selection = select_autopick_team(
        MagicMock(),
        league=league,
        member=SimpleNamespace(id=1),
        pools=[pl_pool, pd_pool],
    )
    assert selection is not None
    assert selection.team is pd_1st


def test_promoted_team_bottom_of_own_tier_before_lower_tier(monkeypatch):
    """Opener-only PL teams (left ELC) sort after PL stayers, before ELC."""
    wolves, pl_pool = _team("Wolves", tid=1, code="PL")
    coventry, _ = _team("Coventry", tid=2, code="PL")
    leicester, elc_pool = _team("Leicester", tid=3, code="ELC")
    candidates = [(coventry, pl_pool), (leicester, elc_pool), (wolves, pl_pool)]
    rows = {
        ("PL", 2025): _table_state(
            {
                1: SimpleNamespace(rank=20, points=25, goal_difference=-30, goals_for=30),
            },
            {1, 2},  # coventry arrived in PL opener
        ),
        ("ELC", 2025): _table_state(
            {
                2: SimpleNamespace(rank=1, points=95, goal_difference=52, goals_for=80),
                3: SimpleNamespace(rank=2, points=90, goal_difference=40, goals_for=75),
            },
            {3},  # coventry departed ELC; leicester stayed
        ),
    }
    monkeypatch.setattr(
        "app.services.draft._table_row_lookup",
        lambda *_a, **_k: rows,
    )
    monkeypatch.setattr(
        "app.services.draft.resolve_domestic_tiers",
        lambda *_a, **_k: {"PL": 1, "ELC": 2},
    )
    from app.services.draft import sort_candidates_for_autopick

    ordered, mode = sort_candidates_for_autopick(
        MagicMock(),
        league=SimpleNamespace(upset_rules={"rank_source": "league_table_at_kickoff"}),
        candidates=candidates,
    )
    assert mode == "table"
    assert [t.name for t, _ in ordered] == ["Wolves", "Coventry", "Leicester"]


def test_relegated_team_top_of_lower_tier(monkeypatch):
    """Teams that left PL opener and arrived in ELC sort above ELC stayers."""
    burnley, elc_pool = _team("Burnley", tid=1, code="ELC")
    wolves, _ = _team("Wolves", tid=2, code="ELC")
    leicester, _ = _team("Leicester", tid=3, code="ELC")
    candidates = [(leicester, elc_pool), (wolves, elc_pool), (burnley, elc_pool)]
    rows = {
        ("PL", 2025): _table_state(
            {
                1: SimpleNamespace(rank=19, points=22, goal_difference=-40, goals_for=30),
                2: SimpleNamespace(rank=20, points=20, goal_difference=-50, goals_for=25),
            },
            set(),  # both left PL
        ),
        ("ELC", 2025): _table_state(
            {
                3: SimpleNamespace(rank=1, points=90, goal_difference=40, goals_for=80),
            },
            {1, 2, 3},  # burnley/wolves arrived in Championship
        ),
    }
    monkeypatch.setattr(
        "app.services.draft._table_row_lookup",
        lambda *_a, **_k: rows,
    )
    monkeypatch.setattr(
        "app.services.draft.resolve_domestic_tiers",
        lambda *_a, **_k: {"PL": 1, "ELC": 2},
    )
    from app.services.draft import sort_candidates_for_autopick

    ordered, mode = sort_candidates_for_autopick(
        MagicMock(),
        league=SimpleNamespace(upset_rules={"rank_source": "league_table_at_kickoff"}),
        candidates=candidates,
    )
    assert mode == "table"
    assert [t.name for t, _ in ordered] == ["Burnley", "Wolves", "Leicester"]


def test_playoff_not_assumed_from_table_position(monkeypatch):
    """Mid-table finisher who left via opener diff is still treated as departed."""
    # Finished 6th in ELC but not in ELC opener (playoff promotion) → PL arrival.
    sixth, pl_pool = _team("Playoff Winner", tid=1, code="PL")
    champ, elc_pool = _team("Champ Runner", tid=2, code="ELC")
    pl_stayer, _ = _team("Arsenal", tid=3, code="PL")
    candidates = [(sixth, pl_pool), (champ, elc_pool), (pl_stayer, pl_pool)]
    rows = {
        ("PL", 2025): _table_state(
            {
                3: SimpleNamespace(rank=1, points=85, goal_difference=40, goals_for=70),
            },
            {1, 3},
        ),
        ("ELC", 2025): _table_state(
            {
                1: SimpleNamespace(rank=6, points=70, goal_difference=10, goals_for=60),
                2: SimpleNamespace(rank=2, points=88, goal_difference=30, goals_for=70),
            },
            {2},  # #6 departed ELC despite not finishing top-2
        ),
    }
    monkeypatch.setattr(
        "app.services.draft._table_row_lookup",
        lambda *_a, **_k: rows,
    )
    monkeypatch.setattr(
        "app.services.draft.resolve_domestic_tiers",
        lambda *_a, **_k: {"PL": 1, "ELC": 2},
    )
    from app.services.draft import sort_candidates_for_autopick

    ordered, mode = sort_candidates_for_autopick(
        MagicMock(),
        league=SimpleNamespace(upset_rules={"rank_source": "league_table_at_kickoff"}),
        candidates=candidates,
    )
    assert mode == "table"
    # PL stayer, then promoted playoff winner, then ELC stayer
    assert [t.name for t, _ in ordered] == ["Arsenal", "Playoff Winner", "Champ Runner"]


def test_select_autopick_fixed_ranking(monkeypatch):
    low, pool = _team("Low", tid=1)
    high, _ = _team("High", tid=2)
    candidates = [(low, pool), (high, pool)]
    monkeypatch.setattr(
        "app.services.draft._available_candidates",
        lambda *_a, **_k: candidates,
    )
    monkeypatch.setattr(
        "app.services.draft.ranks_for_league",
        lambda *_a, **_k: {
            1: SimpleNamespace(rank=20),
            2: SimpleNamespace(rank=3),
        },
    )
    league = SimpleNamespace(
        upset_rules={
            "rank_source": "fixed_ranking_at_event_start",
            "ranking_list_key": "fifa_men",
        }
    )
    selection = select_autopick_team(
        MagicMock(),
        league=league,
        member=SimpleNamespace(id=1),
        pools=[pool],
    )
    assert selection is not None
    assert selection.mode == "ranking"
    assert selection.team is high


def test_select_autopick_preview_random_omits_team(monkeypatch):
    a, pool = _team("A", tid=1)
    monkeypatch.setattr(
        "app.services.draft._available_candidates",
        lambda *_a, **_k: [(a, pool)],
    )
    monkeypatch.setattr(
        "app.services.draft._table_row_lookup",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        "app.services.draft.ranks_for_league",
        lambda *_a, **_k: None,
    )
    league = SimpleNamespace(upset_rules={"rank_source": "league_table_at_kickoff"})
    selection = select_autopick_team(
        MagicMock(),
        league=league,
        member=SimpleNamespace(id=1),
        pools=[pool],
        for_preview=True,
    )
    assert selection is not None
    assert selection.mode == "random"
    assert selection.team is None


def test_sort_candidates_matches_autopick_pick(monkeypatch):
    arsenal, pool = _team("Arsenal", tid=1)
    burnley, _ = _team("Burnley", tid=2)
    candidates = [(burnley, pool), (arsenal, pool)]
    rows = {
        ("PL", 2025): _table_state(
            {
                1: SimpleNamespace(rank=1, points=84, goal_difference=58, goals_for=88),
                2: SimpleNamespace(rank=17, points=35, goal_difference=-20, goals_for=40),
            },
            {1, 2},
        )
    }
    monkeypatch.setattr(
        "app.services.draft._table_row_lookup",
        lambda *_a, **_k: rows,
    )
    monkeypatch.setattr(
        "app.services.draft.resolve_domestic_tiers",
        lambda *_a, **_k: {"PL": 1},
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [pool]
    league = SimpleNamespace(
        id=1,
        upset_rules={"rank_source": "league_table_at_kickoff"},
    )
    from app.services.draft import sort_candidates_for_autopick

    ordered, mode = sort_candidates_for_autopick(
        db, league=league, candidates=candidates
    )
    assert mode == "table"
    assert [t.name for t, _ in ordered] == ["Arsenal", "Burnley"]


def test_missing_opener_does_not_count_as_stayer(monkeypatch):
    """Previous-final without opener must not treat teams as confirmed stayers."""
    relegated, pl_pool = _team("Leeds", tid=1, code="PL")
    stayer, _ = _team("Arsenal", tid=2, code="PL")
    # Same previous-final ranks; without opener Leeds would wrongly beat Arsenal
    # if unknown opener counted as stayer (Leeds finished higher historically).
    candidates = [(relegated, pl_pool), (stayer, pl_pool)]
    rows = {
        ("PL", 2025): _table_state(
            {
                1: SimpleNamespace(rank=1, points=90, goal_difference=50, goals_for=80),
                2: SimpleNamespace(rank=2, points=80, goal_difference=40, goals_for=70),
            },
            None,  # opener missing
        ),
    }
    monkeypatch.setattr(
        "app.services.draft._table_row_lookup",
        lambda *_a, **_k: rows,
    )
    monkeypatch.setattr(
        "app.services.draft.resolve_domestic_tiers",
        lambda *_a, **_k: {"PL": 1},
    )
    from app.services.draft import sort_candidates_for_autopick

    ordered, mode = sort_candidates_for_autopick(
        MagicMock(),
        league=SimpleNamespace(upset_rules={"rank_source": "league_table_at_kickoff"}),
        candidates=candidates,
    )
    assert mode == "table"
    # Both fall through to "new/unknown" bucket → alphabetical
    assert [t.name for t, _ in ordered] == ["Arsenal", "Leeds"]


def test_table_lookup_keys_by_season_year(monkeypatch):
    """Pools sharing a code across seasons must not overwrite table state."""
    old_champ, old_pool = _team("Old Champ", tid=1, code="PL")
    old_pool.season_year = 2024
    new_champ, new_pool = _team("New Champ", tid=2, code="PL")
    new_pool.season_year = 2025
    candidates = [(old_champ, old_pool), (new_champ, new_pool)]

    def fake_lookup(_db, pools):
        from app.services.draft import CompetitionTableState

        out = {}
        for pool in pools:
            code = (pool.competition_code or "").upper()
            year = int(pool.season_year)
            if year == 2024:
                out[(code, year)] = CompetitionTableState(
                    previous_rows={
                        1: SimpleNamespace(
                            rank=1, points=90, goal_difference=50, goals_for=80
                        ),
                    },
                    opener_ids=frozenset({1}),
                )
            else:
                out[(code, year)] = CompetitionTableState(
                    previous_rows={
                        2: SimpleNamespace(
                            rank=1, points=88, goal_difference=45, goals_for=75
                        ),
                    },
                    opener_ids=frozenset({2}),
                )
        return out

    monkeypatch.setattr("app.services.draft._table_row_lookup", fake_lookup)
    monkeypatch.setattr(
        "app.services.draft.resolve_domestic_tiers",
        lambda *_a, **_k: {"PL": 1},
    )
    from app.services.draft import sort_candidates_for_autopick

    ordered, mode = sort_candidates_for_autopick(
        MagicMock(),
        league=SimpleNamespace(upset_rules={"rank_source": "league_table_at_kickoff"}),
        candidates=candidates,
    )
    assert mode == "table"
    # Both are rank-1 stayers in their own season; higher points first.
    assert [t.name for t, _ in ordered] == ["Old Champ", "New Champ"]


def test_draft_order_cache_skips_random_fallback(monkeypatch):
    from app.services import draft as draft_svc

    draft_svc.invalidate_draft_order_cache()
    arsenal, pool = _team("Arsenal", tid=1)
    burnley, _ = _team("Burnley", tid=2)
    league = SimpleNamespace(
        id=42,
        upset_rules={"rank_source": "league_table_at_kickoff"},
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [pool]
    db.execute.return_value.all.return_value = [
        (arsenal, pool.id),
        (burnley, pool.id),
    ]

    monkeypatch.setattr(
        "app.services.draft.sort_candidates_for_autopick",
        lambda *_a, **_k: (
            [(arsenal, pool), (burnley, pool)],
            "random",
        ),
    )
    first = draft_svc.draft_order_by_team_pool(db, league=league)
    assert first[(arsenal.id, pool.id)] == 0
    assert league.id not in draft_svc._draft_order_cache

    monkeypatch.setattr(
        "app.services.draft.sort_candidates_for_autopick",
        lambda *_a, **_k: (
            [(burnley, pool), (arsenal, pool)],
            "table",
        ),
    )
    second = draft_svc.draft_order_by_team_pool(db, league=league)
    assert second[(burnley.id, pool.id)] == 0
    assert league.id in draft_svc._draft_order_cache
    draft_svc.invalidate_draft_order_cache(league.id)
