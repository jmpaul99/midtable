"""Match log pagination, filters, and owner enrichment."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.league_reads import match_log
from app.services.match_queries import (
    competition_key_predicate,
    competition_keys_from_pools,
    pool_lookup_for_league,
)
from app.services.roster_owners import owner_by_team_id_for_league, team_ids_for_member

_MATCH_LOG_PATCHES = (
    "app.routers.league_reads.competition_keys_from_pools",
    "app.routers.league_reads.scoring_pools_for_league",
    "app.routers.league_reads.pool_lookup_for_league",
    "app.routers.league_reads.owner_by_team_id_for_league",
)


def _patch_match_log(fn):
    # Apply in list order so the first target is the innermost patch (first arg).
    for target in _MATCH_LOG_PATCHES:
        fn = patch(target)(fn)
    return fn


def _call_match_log(**kwargs):
    defaults = dict(
        section="results",
        limit=20,
        offset=0,
        pool_id=None,
        team_id=None,
        member_id=None,
        mine=False,
        sort="kickoff",
        q=None,
    )
    defaults.update(kwargs)
    return match_log(**defaults)


def _pool(**kwargs):
    base = dict(
        id=1,
        public_id=uuid4(),
        provider="football-data.org",
        competition_code="PL",
        season_year=2026,
        label="Premier League",
        scores_match_results=True,
        sort_order=0,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _team(*, tid: int, name: str):
    return SimpleNamespace(id=tid, public_id=uuid4(), name=name)


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


def test_competition_key_predicate_empty():
    assert competition_key_predicate([]) is None
    pred = competition_key_predicate([("football-data.org", "PL", 2026)])
    assert pred is not None


def test_owner_by_team_id_for_league():
    league = SimpleNamespace(id=9)
    member = SimpleNamespace(
        id=3,
        public_id=uuid4(),
        profile_id=7,
        team_name="  Foxes FC  ",
    )
    profile = SimpleNamespace(id=7, display_name="Alex")
    entry = SimpleNamespace(team_id=10, member_id=3, source="draft")

    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "roster" in sql:
            out.all.return_value = [entry]
        elif "league_member" in sql:
            out.all.return_value = [member]
        elif "profile" in sql:
            out.all.return_value = [profile]
        else:
            out.all.return_value = []
        return out

    db.scalars.side_effect = scalars
    owners = owner_by_team_id_for_league(db, league)
    assert owners[10]["member_id"] == str(member.public_id)
    assert owners[10]["team_name"] == "Foxes FC"
    assert owners[10]["display_name"] == "Foxes FC"  # member_label prefers team_name
    assert owners[10]["acquired_via"] == "draft"


def test_team_ids_for_member():
    db = MagicMock()
    out = MagicMock()
    out.all.return_value = [
        SimpleNamespace(team_id=1),
        SimpleNamespace(team_id=2),
    ]
    db.scalars.return_value = out
    assert team_ids_for_member(db, league_id=1, member_id=5) == {1, 2}


def _db_for_matches(matches, teams, events=None):
    events = events or []
    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "scoring_event" in sql or "scoringevent" in sql:
            out.all.return_value = events
        elif "from teams" in sql or ".teams" in sql or "team." in sql:
            # Team query
            out.all.return_value = teams
        else:
            # Match query (default)
            out.all.return_value = matches
        return out

    db.scalars.side_effect = scalars
    return db


@_patch_match_log
def test_match_log_results_pagination_and_owners(
    keys_mock, pools_mock, lookup_mock, owners_mock
):
    pool = _pool()
    pools_mock.return_value = [pool]
    keys_mock.return_value = [(pool.provider, pool.competition_code, pool.season_year)]
    lookup_mock.return_value = {
        (pool.provider, pool.competition_code, pool.season_year): pool
    }
    home = _team(tid=10, name="Arsenal")
    away = _team(tid=20, name="Chelsea")
    owners_mock.return_value = {
        10: {
            "member_id": str(uuid4()),
            "display_name": "Alex",
            "team_name": "Gunners",
            "acquired_via": "draft",
        },
        20: {
            "member_id": str(uuid4()),
            "display_name": "Sam",
            "team_name": None,
            "acquired_via": "draft",
        },
    }
    t0 = datetime(2026, 8, 1, 12, tzinfo=UTC)
    t1 = datetime(2026, 8, 8, 12, tzinfo=UTC)
    t2 = datetime(2026, 8, 15, 12, tzinfo=UTC)
    matches = [
        _match(mid=1, home=10, away=20, status="FINISHED", kickoff=t2, home_goals=2, away_goals=1),
        _match(mid=2, home=10, away=20, status="FINISHED", kickoff=t1, home_goals=0, away_goals=0),
        _match(mid=3, home=10, away=20, status="FINISHED", kickoff=t0, home_goals=1, away_goals=0),
    ]
    league = SimpleNamespace(id=1)
    member = SimpleNamespace(id=99, public_id=uuid4())
    db = _db_for_matches(matches[:3], [home, away])

    page = match_log(
        membership=(league, member),
        db=db,
        section="results",
        limit=2,
        offset=0,
        pool_id=None,
        team_id=None,
        member_id=None,
        mine=False,
        sort="kickoff",
        q=None,
    )
    assert page.has_more is True
    assert len(page.items) == 2
    assert page.items[0].home_owner.team_name == "Gunners"
    assert page.items[0].away_owner.display_name == "Sam"
    assert page.items[0].pool_label == "Premier League"


@_patch_match_log
def test_match_log_kickoff_pages_after_dropped_rows(
    keys_mock, pools_mock, lookup_mock, owners_mock
):
    """Rows dropped post-query must not skew offset/has_more (Bugbot finding)."""
    pool = _pool()
    pools_mock.return_value = [pool]
    keys_mock.return_value = [(pool.provider, pool.competition_code, pool.season_year)]
    # First match has no pool mapping and is dropped before paging.
    lookup_mock.return_value = {
        (pool.provider, pool.competition_code, pool.season_year): pool
    }
    owners_mock.return_value = {}
    home = _team(tid=10, name="Arsenal")
    away = _team(tid=20, name="Chelsea")
    t0 = datetime(2026, 8, 1, 12, tzinfo=UTC)
    t1 = datetime(2026, 8, 8, 12, tzinfo=UTC)
    t2 = datetime(2026, 8, 15, 12, tzinfo=UTC)
    orphan = _match(
        mid=1, home=10, away=20, status="FINISHED", kickoff=t2, home_goals=2, away_goals=1
    )
    orphan.competition_code = "CL"  # not in pool lookup → dropped
    kept_a = _match(
        mid=2, home=10, away=20, status="FINISHED", kickoff=t1, home_goals=0, away_goals=0
    )
    kept_b = _match(
        mid=3, home=10, away=20, status="FINISHED", kickoff=t0, home_goals=1, away_goals=0
    )
    league = SimpleNamespace(id=1)
    member = SimpleNamespace(id=99, public_id=uuid4())
    db = _db_for_matches([orphan, kept_a, kept_b], [home, away])

    page0 = match_log(
        membership=(league, member),
        db=db,
        section="results",
        limit=1,
        offset=0,
        pool_id=None,
        team_id=None,
        member_id=None,
        mine=False,
        sort="kickoff",
        q=None,
    )
    assert len(page0.items) == 1
    assert page0.items[0].id == kept_a.public_id
    assert page0.has_more is True

    page1 = match_log(
        membership=(league, member),
        db=db,
        section="results",
        limit=1,
        offset=1,
        pool_id=None,
        team_id=None,
        member_id=None,
        mine=False,
        sort="kickoff",
        q=None,
    )
    assert len(page1.items) == 1
    assert page1.items[0].id == kept_b.public_id
    assert page1.has_more is False


@_patch_match_log
def test_match_log_points_sort(
    keys_mock, pools_mock, lookup_mock, owners_mock
):
    pool = _pool()
    pools_mock.return_value = [pool]
    keys_mock.return_value = [(pool.provider, pool.competition_code, pool.season_year)]
    lookup_mock.return_value = {
        (pool.provider, pool.competition_code, pool.season_year): pool
    }
    owners_mock.return_value = {}
    home = _team(tid=10, name="Arsenal")
    away = _team(tid=20, name="Chelsea")
    t0 = datetime(2026, 8, 1, 12, tzinfo=UTC)
    t1 = datetime(2026, 8, 8, 12, tzinfo=UTC)
    low = _match(mid=1, home=10, away=20, status="FINISHED", kickoff=t1, home_goals=1, away_goals=0)
    high = _match(mid=2, home=10, away=20, status="FINISHED", kickoff=t0, home_goals=3, away_goals=0)
    events = [
        SimpleNamespace(match_id=1, team_id=10, points=3.0),
        SimpleNamespace(match_id=2, team_id=10, points=8.0),
        SimpleNamespace(match_id=2, team_id=20, points=1.0),
    ]
    league = SimpleNamespace(id=1)
    member = SimpleNamespace(id=99, public_id=uuid4())
    db = _db_for_matches([low, high], [home, away], events=events)

    page = match_log(
        membership=(league, member),
        db=db,
        section="results",
        limit=10,
        offset=0,
        pool_id=None,
        team_id=None,
        member_id=None,
        mine=False,
        sort="points",
        q=None,
    )
    assert len(page.items) == 2
    assert page.items[0].id == high.public_id
    assert page.items[0].home_points == 8.0
    assert page.has_more is False


@_patch_match_log
def test_match_log_points_sort_stable_ties(
    keys_mock, pools_mock, lookup_mock, owners_mock
):
    """Tied points+kickoff must paginate without repeats/skips (Bugbot finding)."""
    pool = _pool()
    pools_mock.return_value = [pool]
    keys_mock.return_value = [(pool.provider, pool.competition_code, pool.season_year)]
    lookup_mock.return_value = {
        (pool.provider, pool.competition_code, pool.season_year): pool
    }
    owners_mock.return_value = {}
    home = _team(tid=10, name="Arsenal")
    away = _team(tid=20, name="Chelsea")
    kickoff = datetime(2026, 8, 1, 12, tzinfo=UTC)
    a = _match(mid=1, home=10, away=20, status="FINISHED", kickoff=kickoff, home_goals=1, away_goals=0)
    b = _match(mid=2, home=10, away=20, status="FINISHED", kickoff=kickoff, home_goals=1, away_goals=0)
    c = _match(mid=3, home=10, away=20, status="FINISHED", kickoff=kickoff, home_goals=1, away_goals=0)
    events = [
        SimpleNamespace(match_id=1, team_id=10, points=5.0),
        SimpleNamespace(match_id=2, team_id=10, points=5.0),
        SimpleNamespace(match_id=3, team_id=10, points=5.0),
    ]
    league = SimpleNamespace(id=1)
    member = SimpleNamespace(id=99, public_id=uuid4())
    db = _db_for_matches([a, b, c], [home, away], events=events)

    page0 = match_log(
        membership=(league, member),
        db=db,
        section="results",
        limit=2,
        offset=0,
        pool_id=None,
        team_id=None,
        member_id=None,
        mine=False,
        sort="points",
        q=None,
    )
    page1 = match_log(
        membership=(league, member),
        db=db,
        section="results",
        limit=2,
        offset=2,
        pool_id=None,
        team_id=None,
        member_id=None,
        mine=False,
        sort="points",
        q=None,
    )
    ids0 = {row.id for row in page0.items}
    ids1 = {row.id for row in page1.items}
    assert len(page0.items) == 2
    assert page0.has_more is True
    assert len(page1.items) == 1
    assert page1.has_more is False
    assert ids0.isdisjoint(ids1)
    assert ids0 | ids1 == {a.public_id, b.public_id, c.public_id}


@patch("app.routers.league_reads.scoring_pools_for_league")
def test_match_log_unknown_pool_404(pools_mock):
    pools_mock.return_value = [_pool()]
    league = SimpleNamespace(id=1)
    member = SimpleNamespace(id=99, public_id=uuid4())
    with pytest.raises(HTTPException) as exc:
        _call_match_log(
            membership=(league, member),
            db=MagicMock(),
            pool_id=uuid4(),
        )
    assert exc.value.status_code == 404


def test_pool_lookup_for_league():
    league = SimpleNamespace(id=1)
    pool = _pool()
    db = MagicMock()
    out = MagicMock()
    out.all.return_value = [pool]
    db.scalars.return_value = out
    lookup = pool_lookup_for_league(db, league)
    assert lookup[(pool.provider, pool.competition_code, pool.season_year)] is pool


def test_competition_keys_from_pools_still_dedupes():
    pools = [
        _pool(),
        _pool(competition_code="PL", season_year=2026),
        _pool(competition_code="CL", season_year=2026, public_id=uuid4()),
    ]
    keys = competition_keys_from_pools(pools)
    assert keys == [
        ("football-data.org", "PL", 2026),
        ("football-data.org", "CL", 2026),
    ]
