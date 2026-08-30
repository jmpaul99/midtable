"""football-data.org score goal parsing (home/away, legacy keys, goals[], detail)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from app.providers.football_data import FootballDataProvider


def _response(json_body: dict, *, url: str = "https://api.football-data.org/v4/x") -> httpx.Response:
    return httpx.Response(
        200,
        json=json_body,
        headers={"X-Requests-Available-Minute": "10"},
        request=httpx.Request("GET", url),
    )


def test_goals_from_score_block_prefers_home_away():
    assert FootballDataProvider.goals_from_score_block({"home": 2, "away": 1}) == (2, 1)


def test_goals_from_score_block_legacy_home_team_keys():
    assert FootballDataProvider.goals_from_score_block(
        {"homeTeam": 7, "awayTeam": 6}
    ) == (7, 6)


def test_goals_from_match_score_falls_back_to_regular_time_when_finished():
    score = {
        "duration": "REGULAR",
        "fullTime": {"home": None, "away": None},
        "regularTime": {"home": 1, "away": 1},
    }
    assert FootballDataProvider.goals_from_match_score(score, status="FINISHED") == (
        1,
        1,
    )


def test_goals_from_match_score_falls_back_to_extra_time_when_finished():
    score = {
        "duration": "EXTRA_TIME",
        "fullTime": {"home": None, "away": None},
        "regularTime": {"home": None, "away": None},
        "extraTime": {"home": 2, "away": 1},
    }
    assert FootballDataProvider.goals_from_match_score(score, status="FINISHED") == (
        2,
        1,
    )


def test_goals_from_match_score_legacy_full_time_when_finished():
    score = {
        "duration": "REGULAR",
        "fullTime": {"homeTeam": 0, "awayTeam": 2},
    }
    assert FootballDataProvider.goals_from_match_score(score, status="FINISHED") == (
        0,
        2,
    )


def test_goals_from_goals_events_uses_last_running_score():
    goals = [
        {"minute": 12, "score": {"home": 1, "away": 0}},
        {"minute": 67, "score": {"home": 1, "away": 1}},
        {"minute": 88, "score": {"home": 1, "away": 2}},
    ]
    assert FootballDataProvider.goals_from_goals_events(goals) == (1, 2)


def test_goals_from_goals_events_legacy_score_keys():
    goals = [{"minute": 90, "score": {"homeTeam": 0, "awayTeam": 2}}]
    assert FootballDataProvider.goals_from_goals_events(goals) == (0, 2)


def test_goals_from_match_payload_prefers_full_time_over_goals_events():
    item = {
        "status": "FINISHED",
        "score": {"fullTime": {"home": 3, "away": 0}},
        "goals": [{"minute": 10, "score": {"home": 1, "away": 0}}],
    }
    assert FootballDataProvider.goals_from_match_payload(item) == (3, 0)


def test_goals_from_match_payload_falls_back_to_goals_events():
    item = {
        "status": "FINISHED",
        "score": {
            "duration": "REGULAR",
            "fullTime": {"home": None, "away": None},
        },
        "goals": [
            {"minute": 28, "score": {"home": 0, "away": 1}},
            {"minute": 90, "score": {"home": 1, "away": 1}},
        ],
    }
    assert FootballDataProvider.goals_from_match_payload(item) == (1, 1)


def test_list_matches_parses_legacy_goal_keys():
    client = MagicMock()
    client.get.return_value = _response(
        {
            "matches": [
                {
                    "id": 99,
                    "utcDate": "2026-08-29T14:00:00Z",
                    "status": "FINISHED",
                    "matchday": 3,
                    "stage": "REGULAR_SEASON",
                    "homeTeam": {"id": 1},
                    "awayTeam": {"id": 2},
                    "score": {
                        "duration": "REGULAR",
                        "fullTime": {"homeTeam": 2, "awayTeam": 2},
                    },
                }
            ]
        },
        url="https://api.football-data.org/v4/competitions/PL/matches",
    )
    provider = FootballDataProvider("token", client=client)
    matches, _rate = provider.list_matches("PL", 2026)
    assert len(matches) == 1
    assert matches[0].status == "FINISHED"
    assert matches[0].home_goals == 2
    assert matches[0].away_goals == 2
    assert client.get.call_count == 1


def test_list_matches_uses_goals_events_when_full_time_null():
    """Saturday-style list row: FINISHED + null fullTime, but goals[] present."""
    client = MagicMock()
    client.get.return_value = _response(
        {
            "matches": [
                {
                    "id": 501,
                    "utcDate": "2026-08-29T14:00:00Z",
                    "status": "FINISHED",
                    "matchday": 3,
                    "stage": "REGULAR_SEASON",
                    "homeTeam": {"id": 10},
                    "awayTeam": {"id": 20},
                    "score": {
                        "duration": "REGULAR",
                        "winner": "DRAW",
                        "fullTime": {"home": None, "away": None},
                        "halfTime": {"home": None, "away": None},
                    },
                    "goals": [
                        {"minute": 41, "score": {"home": 1, "away": 0}},
                        {"minute": 73, "score": {"home": 1, "away": 1}},
                    ],
                }
            ]
        },
        url="https://api.football-data.org/v4/competitions/PL/matches",
    )
    provider = FootballDataProvider("token", client=client)
    matches, _rate = provider.list_matches("PL", 2026)
    assert matches[0].home_goals == 1
    assert matches[0].away_goals == 1
    # No detail GET when goals[] already fills the score.
    assert client.get.call_count == 1


def test_list_matches_fetches_detail_when_list_row_missing_goals():
    """Thin competition list: FINISHED + null fullTime + no goals[] → GET /matches/{id}."""
    client = MagicMock()

    def _get(path, params=None):
        if path.endswith("/matches") or "/competitions/" in path:
            return _response(
                {
                    "matches": [
                        {
                            "id": 777,
                            "utcDate": "2026-08-29T16:30:00Z",
                            "status": "FINISHED",
                            "matchday": 3,
                            "stage": "REGULAR_SEASON",
                            "homeTeam": {"id": 64},
                            "awayTeam": {"id": 17},
                            "score": {
                                "duration": "REGULAR",
                                "fullTime": {"home": None, "away": None},
                            },
                        }
                    ]
                },
                url="https://api.football-data.org/v4/competitions/PL/matches",
            )
        assert path == "/matches/777"
        return _response(
            {
                "id": 777,
                "utcDate": "2026-08-29T16:30:00Z",
                "status": "FINISHED",
                "homeTeam": {"id": 64},
                "awayTeam": {"id": 17},
                "score": {
                    "duration": "REGULAR",
                    "fullTime": {"home": 2, "away": 2},
                },
                "goals": [
                    {"minute": 10, "score": {"home": 1, "away": 0}},
                    {"minute": 55, "score": {"home": 1, "away": 1}},
                    {"minute": 80, "score": {"home": 2, "away": 2}},
                ],
            },
            url="https://api.football-data.org/v4/matches/777",
        )

    client.get.side_effect = _get
    provider = FootballDataProvider("token", client=client)
    matches, _rate = provider.list_matches("PL", 2026)
    assert len(matches) == 1
    assert matches[0].external_id == "777"
    assert matches[0].home_goals == 2
    assert matches[0].away_goals == 2
    assert client.get.call_count == 2


def test_list_matches_detail_can_fill_from_goals_events_alone():
    client = MagicMock()

    def _get(path, params=None):
        if "/competitions/" in path:
            return _response(
                {
                    "matches": [
                        {
                            "id": 888,
                            "utcDate": "2026-08-28T19:00:00Z",
                            "status": "FINISHED",
                            "homeTeam": {"id": 1},
                            "awayTeam": {"id": 2},
                            "score": {"fullTime": {"home": None, "away": None}},
                        }
                    ]
                }
            )
        return _response(
            {
                "id": 888,
                "status": "FINISHED",
                "score": {"fullTime": {"home": None, "away": None}},
                "goals": [
                    {"minute": 5, "score": {"home": 0, "away": 1}},
                    {"minute": 22, "score": {"home": 1, "away": 1}},
                    {"minute": 40, "score": {"home": 1, "away": 2}},
                    {"minute": 61, "score": {"home": 1, "away": 3}},
                    {"minute": 74, "score": {"home": 1, "away": 4}},
                ],
            }
        )

    client.get.side_effect = _get
    provider = FootballDataProvider("token", client=client)
    matches, _rate = provider.list_matches("PL", 2026)
    assert matches[0].home_goals == 1
    assert matches[0].away_goals == 4


def test_should_fetch_match_detail_overdue_non_terminal():
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 8, 30, 17, tzinfo=UTC)
    kickoff = now - timedelta(hours=5)
    assert FootballDataProvider.should_fetch_match_detail(
        status="TIMED",
        home_goals=None,
        away_goals=None,
        kickoff_at=kickoff,
        now=now,
    )
    # Still within 2h window — do not detail-fetch yet.
    assert not FootballDataProvider.should_fetch_match_detail(
        status="TIMED",
        home_goals=None,
        away_goals=None,
        kickoff_at=now - timedelta(hours=1),
        now=now,
    )
    # Future kickoff — never.
    assert not FootballDataProvider.should_fetch_match_detail(
        status="TIMED",
        home_goals=None,
        away_goals=None,
        kickoff_at=now + timedelta(hours=3),
        now=now,
    )


def test_list_matches_fetches_detail_for_overdue_timed_row():
    """Stuck TIMED list row after kickoff → GET detail; apply FINISHED + goals."""
    client = MagicMock()

    def _get(path, params=None):
        if "/competitions/" in path:
            return _response(
                {
                    "matches": [
                        {
                            "id": 901,
                            "utcDate": "2026-08-29T14:00:00Z",
                            "status": "TIMED",
                            "matchday": 3,
                            "homeTeam": {"id": 1044},
                            "awayTeam": {"id": 62},
                            "score": {
                                "fullTime": {"home": None, "away": None},
                            },
                        }
                    ]
                }
            )
        assert path == "/matches/901"
        return _response(
            {
                "id": 901,
                "utcDate": "2026-08-29T14:00:00Z",
                "status": "FINISHED",
                "homeTeam": {"id": 1044},
                "awayTeam": {"id": 62},
                "score": {"fullTime": {"home": 1, "away": 1}},
                "goals": [
                    {"minute": 33, "score": {"home": 1, "away": 0}},
                    {"minute": 71, "score": {"home": 1, "away": 1}},
                ],
            }
        )

    client.get.side_effect = _get
    provider = FootballDataProvider("token", client=client)
    matches, _rate = provider.list_matches("PL", 2026)
    assert client.get.call_count == 2
    assert matches[0].status == "FINISHED"
    assert matches[0].home_goals == 1
    assert matches[0].away_goals == 1


def test_list_matches_skips_detail_for_future_timed_row():
    client = MagicMock()
    client.get.return_value = _response(
        {
            "matches": [
                {
                    "id": 902,
                    "utcDate": "2099-08-29T14:00:00Z",
                    "status": "TIMED",
                    "homeTeam": {"id": 1},
                    "awayTeam": {"id": 2},
                    "score": {"fullTime": {"home": None, "away": None}},
                }
            ]
        }
    )
    provider = FootballDataProvider("token", client=client)
    matches, _rate = provider.list_matches("PL", 2026)
    assert client.get.call_count == 1
    assert matches[0].status == "TIMED"
    assert matches[0].home_goals is None
