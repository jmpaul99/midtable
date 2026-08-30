"""football-data.org score goal parsing (home/away and legacy homeTeam keys)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from app.providers.football_data import FootballDataProvider


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


def test_goals_from_match_score_legacy_full_time_when_finished():
    score = {
        "duration": "REGULAR",
        "fullTime": {"homeTeam": 0, "awayTeam": 2},
    }
    assert FootballDataProvider.goals_from_match_score(score, status="FINISHED") == (
        0,
        2,
    )


def test_list_matches_parses_legacy_goal_keys():
    client = MagicMock()
    client.get.return_value = httpx.Response(
        200,
        json={
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
        headers={"X-Requests-Available-Minute": "10"},
        request=httpx.Request(
            "GET", "https://api.football-data.org/v4/competitions/PL/matches"
        ),
    )
    provider = FootballDataProvider("token", client=client)
    matches, _rate = provider.list_matches("PL", 2026)
    assert len(matches) == 1
    assert matches[0].status == "FINISHED"
    assert matches[0].home_goals == 2
    assert matches[0].away_goals == 2
