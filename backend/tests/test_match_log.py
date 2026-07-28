"""Match log pagination, filters, and owner enrichment."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.league_reads import match_log
from app.services.match_constants import FINISHED_STATUSES
from app.services.match_queries import (
    competition_key_predicate,
    competition_keys_from_pools,
    fill_mapped_match_page,
    paginate_matches,
    pool_lookup_for_league,
)
from app.services.roster_owners import owner_by_team_id_for_league, team_ids_for_member

_MATCH_LOG_PATCHES = (
    "app.routers.league_reads.paginate_matches",
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


def _paginate_from(matches):
    """Simulate SQL paging + kickoff/points order for unit tests."""

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
        rows = list(matches)
        if order == "kickoff_asc":
            rows = sorted(rows, key=lambda m: (m.kickoff_at, m.id))
        elif order == "points_desc":
            # Caller pre-orders for points tests; keep id desc as tie-break.
            rows = list(rows)
        else:
            rows = sorted(rows, key=lambda m: (m.kickoff_at, m.id), reverse=True)
        page = rows[offset : offset + limit]
        has_more = len(rows) > offset + limit
        return page, has_more

    return _paginate


def _db_for_page(teams, events=None):
    events = events or []
    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "scoring_event" in sql or "scoringevent" in sql:
            out.all.return_value = events
        else:
            out.all.return_value = teams
        return out

    db.scalars.side_effect = scalars
    return db


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


@_patch_match_log
def test_match_log_results_pagination_and_owners(
    paginate_mock, keys_mock, pools_mock, lookup_mock, owners_mock
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
    paginate_mock.side_effect = _paginate_from(matches)
    league = SimpleNamespace(id=1)
    member = SimpleNamespace(id=99, public_id=uuid4())
    db = _db_for_page([home, away])

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
    assert page.next_offset == 2
    assert page.items[0].home_owner.team_name == "Gunners"
    assert page.items[0].away_owner.display_name == "Sam"
    assert page.items[0].pool_label == "Premier League"
    paginate_mock.assert_called()
    assert paginate_mock.call_args.kwargs["order"] == "kickoff_desc"
    assert paginate_mock.call_args.kwargs["limit"] == 2
    assert paginate_mock.call_args.kwargs["offset"] == 0


@_patch_match_log
def test_match_log_excludes_other_competitions_via_keys(
    paginate_mock, keys_mock, pools_mock, lookup_mock, owners_mock
):
    """SQL keys are pool-scoped; paginate only sees in-competition matches."""
    pool = _pool()
    pools_mock.return_value = [pool]
    keys = [(pool.provider, pool.competition_code, pool.season_year)]
    keys_mock.return_value = keys
    lookup_mock.return_value = {
        (pool.provider, pool.competition_code, pool.season_year): pool
    }
    owners_mock.return_value = {}
    home = _team(tid=10, name="Arsenal")
    away = _team(tid=20, name="Chelsea")
    t0 = datetime(2026, 8, 1, 12, tzinfo=UTC)
    t1 = datetime(2026, 8, 8, 12, tzinfo=UTC)
    kept_a = _match(
        mid=2, home=10, away=20, status="FINISHED", kickoff=t1, home_goals=0, away_goals=0
    )
    kept_b = _match(
        mid=3, home=10, away=20, status="FINISHED", kickoff=t0, home_goals=1, away_goals=0
    )
    # Orphan CL match is never passed to paginate (excluded by competition keys).
    paginate_mock.side_effect = _paginate_from([kept_a, kept_b])
    league = SimpleNamespace(id=1)
    member = SimpleNamespace(id=99, public_id=uuid4())
    db = _db_for_page([home, away])

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
    assert paginate_mock.call_args.kwargs["keys"] == keys

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
    paginate_mock, keys_mock, pools_mock, lookup_mock, owners_mock
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
    # SQL points order: high before low.
    paginate_mock.side_effect = _paginate_from([high, low])
    events = [
        SimpleNamespace(match_id=1, team_id=10, points=3.0),
        SimpleNamespace(match_id=2, team_id=10, points=8.0),
        SimpleNamespace(match_id=2, team_id=20, points=1.0),
    ]
    league = SimpleNamespace(id=1)
    member = SimpleNamespace(id=99, public_id=uuid4())
    db = _db_for_page([home, away], events=events)

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
    assert paginate_mock.call_args.kwargs["order"] == "points_desc"
    assert paginate_mock.call_args.kwargs["league_id"] == 1


@_patch_match_log
def test_match_log_points_sort_stable_ties(
    paginate_mock, keys_mock, pools_mock, lookup_mock, owners_mock
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
    # Match.id DESC tie-break (same as SQL points_desc).
    ordered = [c, b, a]
    paginate_mock.side_effect = _paginate_from(ordered)
    events = [
        SimpleNamespace(match_id=1, team_id=10, points=5.0),
        SimpleNamespace(match_id=2, team_id=10, points=5.0),
        SimpleNamespace(match_id=3, team_id=10, points=5.0),
    ]
    league = SimpleNamespace(id=1)
    member = SimpleNamespace(id=99, public_id=uuid4())
    db = _db_for_page([home, away], events=events)

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


def test_paginate_matches_empty_keys():
    db = MagicMock()
    matches, has_more = paginate_matches(db, keys=[], limit=10, offset=0)
    assert matches == []
    assert has_more is False
    db.scalars.assert_not_called()


def test_paginate_matches_requires_league_id_for_points():
    db = MagicMock()
    with pytest.raises(ValueError, match="league_id"):
        paginate_matches(
            db,
            keys=[("football-data.org", "PL", 2026)],
            limit=10,
            offset=0,
            order="points_desc",
        )


def test_paginate_matches_limit_plus_one():
    db = MagicMock()
    rows = [SimpleNamespace(id=i) for i in range(3)]
    result = MagicMock()
    result.all.return_value = rows
    result.unique.return_value = result
    db.scalars.return_value = result

    page, has_more = paginate_matches(
        db,
        keys=[("football-data.org", "PL", 2026)],
        limit=2,
        offset=0,
        order="kickoff_desc",
    )
    assert has_more is True
    assert page == rows[:2]
    assert FINISHED_STATUSES  # imported for domain coupling sanity


def test_fill_mapped_match_page_refills_after_drops():
    """Dropped mapped rows must not shrink the page or stall the SQL cursor."""
    all_matches = [SimpleNamespace(id=i) for i in range(6)]

    def fetch(limit: int, offset: int):
        page = all_matches[offset : offset + limit]
        has_more = len(all_matches) > offset + limit
        return page, has_more

    def map_matches(matches):
        # Drop even ids (orphans / unmapped rows).
        return [m for m in matches if m.id % 2 == 1]

    page0, has_more0, next0 = fill_mapped_match_page(
        limit=2,
        offset=0,
        fetch_matches=fetch,
        map_matches=map_matches,
    )
    assert [m.id for m in page0] == [1, 3]
    assert has_more0 is True
    assert next0 == 4

    page1, has_more1, next1 = fill_mapped_match_page(
        limit=2,
        offset=next0,
        fetch_matches=fetch,
        map_matches=map_matches,
    )
    assert [m.id for m in page1] == [5]
    assert has_more1 is False
    assert next1 == 6


@_patch_match_log
def test_match_log_fills_page_when_pool_missing(
    paginate_mock, keys_mock, pools_mock, lookup_mock, owners_mock
):
    """Matches without a pool are dropped; page still fills and next_offset advances."""
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
    t2 = datetime(2026, 8, 15, 12, tzinfo=UTC)
    orphan = _match(
        mid=1, home=10, away=20, status="FINISHED", kickoff=t2, home_goals=1, away_goals=0
    )
    orphan.competition_code = "CL"
    kept_a = _match(
        mid=2, home=10, away=20, status="FINISHED", kickoff=t1, home_goals=2, away_goals=0
    )
    kept_b = _match(
        mid=3, home=10, away=20, status="FINISHED", kickoff=t0, home_goals=0, away_goals=0
    )
    # Newest-first: orphan, kept_a, kept_b
    paginate_mock.side_effect = _paginate_from([orphan, kept_a, kept_b])
    league = SimpleNamespace(id=1)
    member = SimpleNamespace(id=99, public_id=uuid4())
    db = _db_for_page([home, away])

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
    assert [row.id for row in page.items] == [kept_a.public_id, kept_b.public_id]
    assert page.has_more is False
    assert page.next_offset == 3
    assert paginate_mock.call_count >= 2
