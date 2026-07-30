"""Member highlight period selection across multi-competition leagues."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.match_stats import member_highlights


def test_member_highlights_best_period_stays_on_primary_competition_type():
    member_id = uuid4()
    league = SimpleNamespace(id=1, public_id=uuid4(), upset_rules={})
    member = SimpleNamespace(
        id=10,
        public_id=member_id,
        league_id=1,
        profile_id=99,
        team_name="Manager",
    )
    roster = [SimpleNamespace(league_id=1, member_id=10, team_id=100)]
    pools = [
        SimpleNamespace(
            id=1,
            league_id=1,
            sort_order=1,
            scores_match_results=True,
            competition_code="PL",
            competition_type="LEAGUE",
        ),
        SimpleNamespace(
            id=2,
            league_id=1,
            sort_order=2,
            scores_match_results=True,
            competition_code="FAC",
            competition_type="CUP",
        ),
    ]
    events = [
        SimpleNamespace(
            league_id=1,
            team_id=100,
            match_id=1,
            stage="REGULAR_SEASON",
            scheduled_matchweek=1,
            points=4,
            event_type="win",
            metadata_={},
        ),
        SimpleNamespace(
            league_id=1,
            team_id=100,
            match_id=2,
            stage="LAST_16",
            scheduled_matchweek=1,
            points=20,
            event_type="win",
            metadata_={},
        ),
    ]
    matches = [
        SimpleNamespace(
            id=1,
            public_id=uuid4(),
            competition_code="PL",
            home_team_id=100,
            away_team_id=200,
        ),
        SimpleNamespace(
            id=2,
            public_id=uuid4(),
            competition_code="FAC",
            home_team_id=100,
            away_team_id=201,
        ),
    ]
    teams = [
        SimpleNamespace(id=100, public_id=uuid4(), name="Club"),
        SimpleNamespace(id=200, public_id=uuid4(), name="Opp A"),
        SimpleNamespace(id=201, public_id=uuid4(), name="Opp B"),
    ]
    profile = SimpleNamespace(id=99, display_name="Manager")

    responses = [
        member,  # LeagueMember lookup
        roster,  # RosterEntry
        pools,  # TeamPool
        events,  # ScoringEvent
        matches,  # Match
        teams,  # Team
    ]
    call_i = {"n": 0}

    def scalars(_stmt):
        idx = call_i["n"]
        call_i["n"] += 1
        value = responses[idx]
        out = MagicMock()
        if isinstance(value, list):
            out.all.return_value = value
            out.__iter__ = lambda self: iter(value)
        else:
            out.first.return_value = value
        return out

    db = MagicMock()
    db.scalars.side_effect = scalars
    db.get.return_value = profile

    result = member_highlights(db, league, member_public_id=member_id)

    assert result["period_kind"] == "matchweek"
    assert result["best_matchweek"] is not None
    assert result["best_matchweek"]["points"] == 4.0
    assert result["best_matchweek"]["period_key"] == "REGULAR_SEASON"
    assert result["worst_matchweek"]["points"] == 4.0
