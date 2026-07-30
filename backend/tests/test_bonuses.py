"""Bonus award presentation helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.services.bonuses import accumulate_bonus_awards, match_label


def test_match_label_uses_competition_type():
    match = SimpleNamespace(
        home_team_id=1,
        away_team_id=2,
        scheduled_matchweek=3,
    )
    teams = {
        1: SimpleNamespace(name="Home"),
        2: SimpleNamespace(name="Away"),
    }
    assert match_label(match, teams, competition_type="LEAGUE") == "Home vs Away · MW3"
    assert match_label(match, teams, competition_type="CUP") == "Home vs Away · R3"


def test_accumulate_bonus_awards_labels_by_match_competition():
    bonuses = [
        SimpleNamespace(
            public_id=uuid4(),
            member_id=None,
            team_id=1,
            match_id=10,
            bonus_type_id=1,
            points=5,
            notes=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        SimpleNamespace(
            public_id=uuid4(),
            member_id=None,
            team_id=1,
            match_id=20,
            bonus_type_id=1,
            points=2,
            notes=None,
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    ]
    bonus_types = {1: SimpleNamespace(key="motm", label="Man of the match")}
    teams = {
        1: SimpleNamespace(public_id=uuid4(), name="Arsenal", crest_url=None),
        2: SimpleNamespace(public_id=uuid4(), name="Chelsea", crest_url=None),
        3: SimpleNamespace(public_id=uuid4(), name="Liverpool", crest_url=None),
    }
    matches = {
        10: SimpleNamespace(
            public_id=uuid4(),
            home_team_id=1,
            away_team_id=2,
            scheduled_matchweek=4,
            competition_code="PL",
        ),
        20: SimpleNamespace(
            public_id=uuid4(),
            home_team_id=1,
            away_team_id=3,
            scheduled_matchweek=2,
            competition_code="FAC",
        ),
    }

    acc = accumulate_bonus_awards(
        bonuses,
        bonus_types=bonus_types,
        teams=teams,
        matches=matches,
        competition_type="LEAGUE",
        competition_type_by_code={"PL": "LEAGUE", "FAC": "CUP"},
    )

    assert acc.awarded[0].match_label == "Arsenal vs Chelsea · MW4"
    assert acc.awarded[1].match_label == "Arsenal vs Liverpool · R2"
