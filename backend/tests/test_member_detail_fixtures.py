"""Member/team fixture list: recent/upcoming, filters, and pagination."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.routers.league_reads import member_detail, member_fixtures, team_fixtures
from app.services.match_constants import FINISHED_STATUSES


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


def _paginate_from(all_matches):
    """Simulate SQL section filter + kickoff paging."""

    def _paginate(
        _db,
        *,
        keys,
        limit,
        offset,
        filters=None,
        order="kickoff_desc",
        league_id=None,
    ):
        if order == "kickoff_asc":
            rows = [m for m in all_matches if m.status not in FINISHED_STATUSES]
            rows = sorted(rows, key=lambda m: (m.kickoff_at, m.id))
        else:
            rows = [m for m in all_matches if m.status in FINISHED_STATUSES]
            rows = sorted(rows, key=lambda m: (m.kickoff_at, m.id), reverse=True)
        page = rows[offset : offset + limit]
        has_more = len(rows) > offset + limit
        return page, has_more

    return _paginate


def _db_for_fixtures(*, member, profile, pool, teams, events):
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
        elif "roster_entry" in sql or "rosterentry" in sql:
            out.all.return_value = []
        elif "pool_team" in sql or "poolteam" in sql:
            out.first.return_value = SimpleNamespace(pool_id=pool.id)
            out.all.return_value = []
        elif "team" in sql:
            out.all.return_value = teams
        else:
            out.all.return_value = []
            out.first.return_value = None
        return out

    db.scalars.side_effect = scalars
    db.get.side_effect = lambda model, pk: (
        profile if pk == 7 else (pool if pk == pool.id else None)
    )
    return db


_FIXTURE_PATCHES = (
    "app.routers.league_reads.paginate_matches",
    "app.routers.league_reads.scoring_pools_for_league",
    "app.routers.league_reads.owner_by_team_id_for_league",
    "app.routers.league_reads.pool_for_match",
    "app.routers.league_reads.pool_lookup_for_league",
    "app.routers.league_reads.team_ids_for_member",
)


def _patch_fixtures(fn):
    for target in _FIXTURE_PATCHES:
        fn = patch(target)(fn)
    return fn


@_patch_fixtures
def test_member_fixtures_recent_upcoming_and_derby(
    paginate_mock,
    pools_mock,
    owners_mock,
    pool_for_match_mock,
    lookup_mock,
    team_ids_mock,
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

    team_ids_mock.return_value = {10, 20}
    owners_mock.return_value = {
        30: {
            "member_id": str(uuid4()),
            "display_name": "Sam",
            "team_name": "Lilywhites",
            "acquired_via": "draft",
        }
    }
    pools_mock.return_value = [pool]
    lookup_mock.return_value = {
        (pool.provider, pool.competition_code, pool.season_year): pool
    }
    pool_for_match_mock.return_value = pool

    t_recent = datetime(2026, 8, 8, 12, tzinfo=UTC)
    t_upcoming = datetime(2026, 8, 22, 12, tzinfo=UTC)
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
    paginate_mock.side_effect = _paginate_from([derby, upcoming])

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

    db = _db_for_fixtures(
        member=member,
        profile=profile,
        pool=pool,
        teams=[arsenal, chelsea, spurs],
        events=events,
    )

    recent = member_fixtures(
        member_id=member_public_id,
        membership=(league, member),
        db=db,
        section="recent",
        limit=5,
        offset=0,
    )
    assert len(recent.items) == 1
    assert recent.has_more is False
    derby_row = recent.items[0]
    assert derby_row.is_home is True
    assert derby_row.opponent_name == "Chelsea"
    assert derby_row.points == 3.0
    assert derby_row.opponent_owner is None

    upcoming_page = member_fixtures(
        member_id=member_public_id,
        membership=(league, member),
        db=db,
        section="upcoming",
        limit=5,
        offset=0,
    )
    assert len(upcoming_page.items) == 1
    up = upcoming_page.items[0]
    assert up.is_home is True
    assert up.opponent_name == "Spurs"
    assert up.points is None


@_patch_fixtures
def test_member_fixtures_lists_each_fixture_once(
    paginate_mock,
    pools_mock,
    owners_mock,
    pool_for_match_mock,
    lookup_mock,
    team_ids_mock,
):
    """Derbies and outsider fixtures each contribute a single list row."""
    pool = _pool()
    clubs = [_team(tid=i, name=f"Club {i}") for i in range(10, 14)]
    outsider = _team(tid=99, name="Outsider")
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

    team_ids_mock.return_value = {10, 11, 12, 13}
    owners_mock.return_value = {
        99: {
            "member_id": str(uuid4()),
            "display_name": "Sam",
            "team_name": "Outsiders",
            "acquired_via": "draft",
        }
    }
    pools_mock.return_value = [pool]
    lookup_mock.return_value = {
        (pool.provider, pool.competition_code, pool.season_year): pool
    }
    pool_for_match_mock.return_value = pool

    derby = _match(
        mid=1,
        home=10,
        away=11,
        status="FINISHED",
        kickoff=datetime(2026, 8, 12, 12, tzinfo=UTC),
        home_goals=1,
        away_goals=0,
    )
    outsider_result = _match(
        mid=2,
        home=12,
        away=99,
        status="FINISHED",
        kickoff=datetime(2026, 8, 10, 12, tzinfo=UTC),
        home_goals=2,
        away_goals=2,
    )
    paginate_mock.side_effect = _paginate_from([derby, outsider_result])

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
            team_id=11,
            event_type="loss",
            points=0.0,
            metadata_={},
        ),
        SimpleNamespace(
            public_id=uuid4(),
            match_id=2,
            team_id=12,
            event_type="draw",
            points=1.0,
            metadata_={},
        ),
    ]

    db = _db_for_fixtures(
        member=member,
        profile=profile,
        pool=pool,
        teams=[*clubs, outsider],
        events=events,
    )

    page = member_fixtures(
        member_id=member_public_id,
        membership=(league, member),
        db=db,
        section="recent",
        limit=5,
        offset=0,
    )

    assert [row.id for row in page.items] == [
        derby.public_id,
        outsider_result.public_id,
    ]
    assert page.items[0].points == 3.0
    assert page.items[0].opponent_owner is None
    assert page.items[1].points == 1.0
    assert page.items[1].opponent_owner is not None


@patch("app.routers.league_reads.team_ids_for_member")
@patch("app.routers.league_reads.pool_lookup_for_league")
@patch("app.routers.league_reads.pool_for_match")
@patch("app.routers.league_reads.owner_by_team_id_for_league")
@patch("app.routers.league_reads.scoring_pools_for_league")
@patch("app.routers.league_reads.paginate_matches")
@patch("app.routers.league_reads.team_in_league")
@patch("app.routers.league_reads._resolve_member")
def test_member_fixtures_filters_and_paginates(
    resolve_member_mock,
    team_in_league_mock,
    paginate_mock,
    pools_mock,
    owners_mock,
    pool_for_match_mock,
    lookup_mock,
    team_ids_mock,
):
    pool = _pool()
    arsenal = _team(tid=10, name="Arsenal")
    chelsea = _team(tid=20, name="Chelsea")
    spurs = _team(tid=30, name="Spurs")
    member_public_id = uuid4()
    opponent_public_id = uuid4()
    member = SimpleNamespace(
        id=3,
        public_id=member_public_id,
        profile_id=7,
        team_name="Foxes",
        draft_slot=1,
    )
    opponent = SimpleNamespace(
        id=4,
        public_id=opponent_public_id,
        profile_id=8,
        team_name="Lilywhites",
        draft_slot=2,
    )
    profile = SimpleNamespace(id=7, display_name="Alex")
    league = SimpleNamespace(id=9, public_id=uuid4())

    def resolve(_db, _league, mid):
        if mid == member_public_id:
            return member
        if mid == opponent_public_id:
            return opponent
        raise AssertionError(f"unexpected member {mid}")

    resolve_member_mock.side_effect = resolve

    def team_ids_for(_db, *, league_id, member_id):
        if member_id == member.id:
            return {10, 20}
        if member_id == opponent.id:
            return {30}
        return set()

    team_ids_mock.side_effect = team_ids_for
    team_in_league_mock.return_value = arsenal
    owners_mock.return_value = {
        30: {
            "member_id": str(opponent_public_id),
            "display_name": "Sam",
            "team_name": "Lilywhites",
            "acquired_via": "draft",
        }
    }
    pools_mock.return_value = [pool]
    lookup_mock.return_value = {
        (pool.provider, pool.competition_code, pool.season_year): pool
    }
    pool_for_match_mock.return_value = pool

    finished = [
        _match(
            mid=i,
            home=10,
            away=30,
            status="FINISHED",
            kickoff=datetime(2026, 8, i, 12, tzinfo=UTC),
            home_goals=1,
            away_goals=0,
        )
        for i in range(1, 8)
    ]
    paginate_mock.side_effect = _paginate_from(finished)
    events = [
        SimpleNamespace(
            public_id=uuid4(),
            match_id=m.id,
            team_id=10,
            event_type="win",
            points=3.0,
            metadata_={},
        )
        for m in finished
    ]

    db = _db_for_fixtures(
        member=member,
        profile=profile,
        pool=pool,
        teams=[arsenal, chelsea, spurs],
        events=events,
    )

    page1 = member_fixtures(
        member_id=member_public_id,
        membership=(league, member),
        db=db,
        section="recent",
        limit=5,
        offset=0,
        club_id=arsenal.public_id,
        opponent_member_id=opponent_public_id,
    )
    assert len(page1.items) == 5
    assert page1.has_more is True
    assert page1.next_offset == 5

    page2 = member_fixtures(
        member_id=member_public_id,
        membership=(league, member),
        db=db,
        section="recent",
        limit=5,
        offset=page1.next_offset,
        club_id=arsenal.public_id,
        opponent_member_id=opponent_public_id,
    )
    assert len(page2.items) == 2
    assert page2.has_more is False
    assert page2.next_offset == 7


@patch("app.routers.league_reads.team_ids_for_member")
@patch("app.routers.league_reads.pool_lookup_for_league")
@patch("app.routers.league_reads.pool_for_match")
@patch("app.routers.league_reads.owner_by_team_id_for_league")
@patch("app.routers.league_reads.scoring_pools_for_league")
@patch("app.routers.league_reads.paginate_matches")
@patch("app.routers.league_reads.team_in_league")
@patch("app.routers.league_reads._resolve_member")
def test_member_fixtures_self_opponent_derby_by_either_club(
    resolve_member_mock,
    team_in_league_mock,
    paginate_mock,
    pools_mock,
    owners_mock,
    pool_for_match_mock,
    lookup_mock,
    team_ids_mock,
):
    """Intra-roster derbies are filterable by either owned club and self as Opponent."""
    pool = _pool()
    arsenal = _team(tid=10, name="Arsenal")
    chelsea = _team(tid=20, name="Chelsea")
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

    resolve_member_mock.return_value = member
    team_ids_mock.return_value = {10, 20}
    owners_mock.return_value = {
        10: {
            "member_id": str(member_public_id),
            "display_name": "Alex",
            "team_name": "Foxes",
            "acquired_via": "draft",
        },
        20: {
            "member_id": str(member_public_id),
            "display_name": "Alex",
            "team_name": "Foxes",
            "acquired_via": "draft",
        },
    }
    pools_mock.return_value = [pool]
    lookup_mock.return_value = {
        (pool.provider, pool.competition_code, pool.season_year): pool
    }
    pool_for_match_mock.return_value = pool
    derby = _match(
        mid=1,
        home=10,
        away=20,
        status="FINISHED",
        kickoff=datetime(2026, 8, 8, 12, tzinfo=UTC),
        home_goals=2,
        away_goals=1,
    )
    paginate_mock.side_effect = _paginate_from([derby])
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
    db = _db_for_fixtures(
        member=member,
        profile=profile,
        pool=pool,
        teams=[arsenal, chelsea],
        events=events,
    )

    team_in_league_mock.return_value = chelsea
    as_chelsea = member_fixtures(
        member_id=member_public_id,
        membership=(league, member),
        db=db,
        section="recent",
        limit=5,
        offset=0,
        club_id=chelsea.public_id,
        opponent_member_id=member_public_id,
    )
    assert len(as_chelsea.items) == 1
    assert as_chelsea.items[0].is_home is False
    assert as_chelsea.items[0].opponent_name == "Arsenal"
    assert as_chelsea.items[0].opponent_owner is not None
    assert as_chelsea.items[0].opponent_owner.member_id == member_public_id

    team_in_league_mock.return_value = arsenal
    as_arsenal = member_fixtures(
        member_id=member_public_id,
        membership=(league, member),
        db=db,
        section="recent",
        limit=5,
        offset=0,
        club_id=arsenal.public_id,
        opponent_member_id=member_public_id,
    )
    assert len(as_arsenal.items) == 1
    assert as_arsenal.items[0].is_home is True
    assert as_arsenal.items[0].opponent_name == "Chelsea"


@patch("app.routers.league_reads.team_ids_for_member")
@patch("app.routers.league_reads.pool_lookup_for_league")
@patch("app.routers.league_reads.pool_for_match")
@patch("app.routers.league_reads.owner_by_team_id_for_league")
@patch("app.routers.league_reads.scoring_pools_for_league")
@patch("app.routers.league_reads.paginate_matches")
@patch("app.routers.league_reads.team_in_league")
@patch("app.routers.league_reads.match_stats_service.current_table_for_pool", return_value={})
def test_team_fixtures_paginates(
    _table_mock,
    team_in_league_mock,
    paginate_mock,
    pools_mock,
    owners_mock,
    pool_for_match_mock,
    lookup_mock,
    team_ids_mock,
):
    pool = _pool()
    arsenal = _team(tid=10, name="Arsenal")
    spurs = _team(tid=30, name="Spurs")
    member = SimpleNamespace(id=3, public_id=uuid4(), profile_id=7, team_name="Foxes")
    profile = SimpleNamespace(id=7, display_name="Alex")
    league = SimpleNamespace(id=9, public_id=uuid4())

    team_in_league_mock.return_value = arsenal
    team_ids_mock.return_value = set()
    owners_mock.return_value = {
        30: {
            "member_id": str(uuid4()),
            "display_name": "Sam",
            "team_name": "Lilywhites",
            "acquired_via": "draft",
        }
    }
    pools_mock.return_value = [pool]
    lookup_mock.return_value = {
        (pool.provider, pool.competition_code, pool.season_year): pool
    }
    pool_for_match_mock.return_value = pool

    finished = [
        _match(
            mid=i,
            home=10,
            away=30,
            status="FINISHED",
            kickoff=datetime(2026, 8, i, 12, tzinfo=UTC),
            home_goals=1,
            away_goals=0,
        )
        for i in range(1, 8)
    ]
    paginate_mock.side_effect = _paginate_from(finished)
    events = [
        SimpleNamespace(
            public_id=uuid4(),
            match_id=m.id,
            team_id=10,
            event_type="win",
            points=3.0,
            metadata_={},
        )
        for m in finished
    ]
    db = _db_for_fixtures(
        member=member,
        profile=profile,
        pool=pool,
        teams=[arsenal, spurs],
        events=events,
    )

    page1 = team_fixtures(
        team_id=arsenal.public_id,
        membership=(league, member),
        db=db,
        section="recent",
        limit=5,
        offset=0,
    )
    assert len(page1.items) == 5
    assert page1.has_more is True
    assert page1.next_offset == 5
    assert page1.items[0].opponent_name == "Spurs"
    assert page1.items[0].points == 3.0

    page2 = team_fixtures(
        team_id=arsenal.public_id,
        membership=(league, member),
        db=db,
        section="recent",
        limit=5,
        offset=page1.next_offset,
    )
    assert len(page2.items) == 2
    assert page2.has_more is False
    assert page2.next_offset == 7


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
def test_member_detail_omits_embedded_fixtures(
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
    ]
    bonus_ctx_mock.return_value = ({}, {}, {})
    bonus_acc_mock.return_value = SimpleNamespace(
        bonus_points=0.0,
        bonus_by_type={},
        awarded=[],
    )
    owners_mock.return_value = {}
    lookup_mock.return_value = {
        (pool.provider, pool.competition_code, pool.season_year): pool
    }
    pool_for_match_mock.return_value = pool
    matches_mock.return_value = []

    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "league_member" in sql:
            out.first.return_value = member
            out.all.return_value = [member]
        elif "scoring_event" in sql or "scoringevent" in sql:
            out.all.return_value = []
        elif "team_pool" in sql or "teampool" in sql:
            out.all.return_value = [pool]
        elif "manual_bonus" in sql or "manualbonus" in sql:
            out.all.return_value = []
        elif "team" in sql:
            out.all.return_value = [arsenal]
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
    assert detail.recent_matches == []
    assert detail.upcoming_matches == []
    assert detail.scoring_events == []
