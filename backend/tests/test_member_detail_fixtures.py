"""Member detail recent/upcoming fixtures across owned clubs."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.routers.league_reads import member_detail


def _team(*, tid: int, name: str):
    return SimpleNamespace(
        id=tid,
        public_id=uuid4(),
        name=name,
        crest_url=None,
    )


def _match(
    *,
    mid: int,
    home: int,
    away: int,
    status: str,
    kickoff: datetime,
    home_goals: int | None = None,
    away_goals: int | None = None,
):
    return SimpleNamespace(
        id=mid,
        public_id=uuid4(),
        provider="football-data.org",
        competition_code="PL",
        season_year=2026,
        home_team_id=home,
        away_team_id=away,
        kickoff_at=kickoff,
        status=status,
        home_goals=home_goals,
        away_goals=away_goals,
        scheduled_matchweek=1,
    )


def _pool():
    return SimpleNamespace(
        id=1,
        public_id=uuid4(),
        provider="football-data.org",
        competition_code="PL",
        season_year=2026,
        label="Premier League",
        scores_match_results=True,
        sort_order=0,
    )


@patch("app.routers.league_reads.owner_by_team_id_for_league")
@patch("app.routers.league_reads.pool_for_match")
@patch("app.routers.league_reads.pool_lookup_for_league")
@patch("app.routers.league_reads.matches_for_league")
@patch("app.routers.league_reads.effective_roster_club_order", return_value="draft")
@patch("app.routers.league_reads.match_stats_service.draft_pick_numbers", return_value={})
@patch("app.routers.league_reads.load_bonus_context")
@patch("app.routers.league_reads.accumulate_bonus_awards")
@patch("app.routers.league_reads.roster_entries_for_member")
@patch("app.routers.league_reads.analytics_service.leaderboard", return_value=[])
def test_member_detail_recent_upcoming_and_derby(
    _leaderboard,
    roster_mock,
    bonus_acc_mock,
    bonus_ctx_mock,
    _picks,
    _order,
    matches_mock,
    lookup_mock,
    pool_for_match_mock,
    owners_mock,
):
    pool = _pool()
    arsenal = _team(tid=10, name="Arsenal")
    chelsea = _team(tid=20, name="Chelsea")
    spurs = _team(tid=30, name="Spurs")
    member_public_id = uuid4()
    member = SimpleNamespace(
        id=3,
        public_id=member_public_id,
        profile_id=7,
        team_name="Foxes",
        draft_slot=1,
    )
    profile = SimpleNamespace(id=7, display_name="Alex")
    league = SimpleNamespace(id=9, public_id=uuid4())

    roster_mock.return_value = [
        SimpleNamespace(team_id=10, pool_id=1, source="draft"),
        SimpleNamespace(team_id=20, pool_id=1, source="draft"),
    ]
    bonus_ctx_mock.return_value = ({}, {}, {})
    bonus_acc_mock.return_value = SimpleNamespace(
        bonus_points=0.0,
        bonus_by_type={},
        awarded=[],
    )
    owners_mock.return_value = {
        30: {
            "member_id": str(uuid4()),
            "display_name": "Sam",
            "team_name": "Lilywhites",
            "acquired_via": "draft",
        }
    }
    lookup_mock.return_value = {
        (pool.provider, pool.competition_code, pool.season_year): pool
    }
    pool_for_match_mock.return_value = pool

    t_recent = datetime(2026, 8, 8, 12, tzinfo=UTC)
    t_upcoming = datetime(2026, 8, 22, 12, tzinfo=UTC)
    # Intra-roster derby (both owned) + one upcoming vs outsider
    derby = _match(
        mid=1,
        home=10,
        away=20,
        status="FINISHED",
        kickoff=t_recent,
        home_goals=2,
        away_goals=1,
    )
    upcoming = _match(
        mid=2,
        home=10,
        away=30,
        status="TIMED",
        kickoff=t_upcoming,
    )
    matches_mock.return_value = [derby, upcoming]

    events = [
        SimpleNamespace(
            public_id=uuid4(),
            match_id=1,
            team_id=10,
            event_type="win",
            points=3.0,
            metadata_={},
        ),
        SimpleNamespace(
            public_id=uuid4(),
            match_id=1,
            team_id=20,
            event_type="loss",
            points=0.0,
            metadata_={},
        ),
    ]

    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "league_member" in sql:
            out.first.return_value = member
            out.all.return_value = [member]
        elif "scoring_event" in sql or "scoringevent" in sql:
            out.all.return_value = events
        elif "team_pool" in sql or "teampool" in sql:
            out.all.return_value = [pool]
        elif "manual_bonus" in sql or "manualbonus" in sql:
            out.all.return_value = []
        elif "team" in sql:
            out.all.return_value = [arsenal, chelsea, spurs]
        else:
            out.all.return_value = []
            out.first.return_value = None
        return out

    db.scalars.side_effect = scalars
    db.get.side_effect = lambda model, pk: profile if pk == 7 else None

    detail = member_detail(
        member_id=member_public_id,
        membership=(league, member),
        db=db,
    )

    assert len(detail.recent_matches) == 2
    recent_focus = {
        (row.is_home, row.opponent_name, row.points) for row in detail.recent_matches
    }
    assert (True, "Chelsea", 3.0) in recent_focus
    assert (False, "Arsenal", 0.0) in recent_focus

    assert len(detail.upcoming_matches) == 1
    up = detail.upcoming_matches[0]
    assert up.is_home is True
    assert up.opponent_name == "Spurs"
    assert up.points is None

    assert len(detail.scoring_events) == 2
    assert {e.event_type for e in detail.scoring_events} == {"win", "loss"}
