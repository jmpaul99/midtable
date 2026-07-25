"""Unit tests for match-derived WDL / form helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.services.match_stats import (
    form_from_results,
    goals_from_results,
    points_by_stage_by_team,
    points_by_stage_from_events,
    team_results_from_matches,
    venue_split,
    wdl_from_results,
)
from app.services.scoring import Result


def _match(
    *,
    mid: int,
    home: int,
    away: int,
    hg: int,
    ag: int,
    kickoff: datetime,
    status: str = "FINISHED",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=mid,
        public_id=uuid4(),
        home_team_id=home,
        away_team_id=away,
        home_goals=hg,
        away_goals=ag,
        kickoff_at=kickoff,
        scheduled_matchweek=1,
        status=status,
    )


def test_wdl_includes_losses_from_finished_matches():
    t0 = datetime(2026, 8, 1, 12, tzinfo=UTC)
    t1 = datetime(2026, 8, 8, 12, tzinfo=UTC)
    t2 = datetime(2026, 8, 15, 12, tzinfo=UTC)
    matches = [
        _match(mid=1, home=10, away=20, hg=2, ag=0, kickoff=t0),  # team 10 win
        _match(mid=2, home=20, away=10, hg=1, ag=1, kickoff=t1),  # draw
        _match(mid=3, home=10, away=30, hg=0, ag=3, kickoff=t2),  # loss
    ]
    results = team_results_from_matches(matches, 10)
    wdl = wdl_from_results(results)
    assert wdl == {"wins": 1, "draws": 1, "losses": 1, "games_played": 3}
    assert [r.letter for r in results] == ["W", "D", "L"]
    assert results[0].result is Result.WIN
    assert results[2].result is Result.LOSS


def test_form_and_streak():
    t0 = datetime(2026, 8, 1, 12, tzinfo=UTC)
    matches = [
        _match(mid=i, home=1, away=2, hg=1, ag=0, kickoff=datetime(2026, 8, i, 12, tzinfo=UTC))
        for i in range(1, 6)
    ]
    # last two losses for team 2
    matches[-1] = _match(mid=5, home=1, away=2, hg=2, ag=0, kickoff=datetime(2026, 8, 5, 12, tzinfo=UTC))
    matches[-2] = _match(mid=4, home=2, away=1, hg=0, ag=1, kickoff=datetime(2026, 8, 4, 12, tzinfo=UTC))
    results = team_results_from_matches(matches, 2)
    form = form_from_results(results, limit=5)
    assert form["form"][-1] == "L"
    assert form["current_streak"]["result"] == "L"
    assert form["current_streak"]["count"] >= 2


def test_goals_and_venue_split():
    t0 = datetime(2026, 8, 1, 12, tzinfo=UTC)
    t1 = datetime(2026, 8, 8, 12, tzinfo=UTC)
    matches = [
        _match(mid=1, home=10, away=20, hg=3, ag=1, kickoff=t0),
        _match(mid=2, home=20, away=10, hg=0, ag=2, kickoff=t1),
    ]
    results = team_results_from_matches(matches, 10)
    goals = goals_from_results(results)
    assert goals == {"goals_for": 5, "goals_against": 1, "goal_difference": 4}
    splits = venue_split(results, {1: 3.0, 2: 3.0})
    assert splits["home"]["wins"] == 1
    assert splits["away"]["wins"] == 1
    assert splits["home"]["points"] == 3.0


def test_points_by_stage_aggregates_and_skips_blank():
    events = [
        SimpleNamespace(team_id=1, stage="GROUP_STAGE", points=3),
        SimpleNamespace(team_id=1, stage="GROUP_STAGE", points=1),
        SimpleNamespace(team_id=1, stage="LAST_16", points=3),
        SimpleNamespace(team_id=1, stage=None, points=5),
        SimpleNamespace(team_id=1, stage="  ", points=2),
        SimpleNamespace(team_id=2, stage="REGULAR_SEASON", points=3),
    ]
    by_team = points_by_stage_by_team(events)
    assert by_team[1] == {"GROUP_STAGE": 4.0, "LAST_16": 3.0}
    assert by_team[2] == {"REGULAR_SEASON": 3.0}
    assert points_by_stage_from_events(events[:3]) == {
        "GROUP_STAGE": 4.0,
        "LAST_16": 3.0,
    }
    assert len(points_by_stage_from_events([events[5]])) == 1
