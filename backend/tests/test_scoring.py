"""Comprehensive pure scoring tests (no DB)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.scoring import (
    DEFAULT_TABLE_TIEBREAKS,
    PL_DEFAULT_UPSET_RULES,
    MatchInput,
    MemberPoints,
    RankedTeam,
    Result,
    ResultPoints,
    TableRow,
    UpsetRules,
    UpsetThreshold,
    attribute_team_points_to_members,
    build_standings_before_kickoff,
    kickoff_snapshots,
    match_passes_phase_filter,
    phase_points_from_events,
    plan_recompute_cascade,
    points_for_result,
    rank_leaderboard,
    rank_table,
    score_match_events,
    snapshot_map,
    upset_bonus,
)

NOW = datetime(2026, 8, 15, 14, tzinfo=UTC)
RULES = PL_DEFAULT_UPSET_RULES
POINTS = ResultPoints()


def _team(team_id: int, rank: int, played: int = 8) -> RankedTeam:
    return RankedTeam(team_id=team_id, rank=rank, played=played)


def _match(
    match_id: int,
    home: int,
    away: int,
    kickoff: datetime,
    hg: int,
    ag: int,
    *,
    pool_id: int = 1,
    mw: int | None = 1,
    stage: str | None = None,
    status: str = "FINISHED",
) -> MatchInput:
    return MatchInput(
        match_id=match_id,
        pool_id=pool_id,
        home_team_id=home,
        away_team_id=away,
        kickoff_at=kickoff,
        home_goals=hg,
        away_goals=ag,
        status=status,
        scheduled_matchweek=mw,
        stage=stage,
    )


def test_default_result_points() -> None:
    assert points_for_result(Result.WIN, POINTS) == 3
    assert points_for_result(Result.DRAW, POINTS) == 1
    assert points_for_result(Result.LOSS, POINTS) == 0


def test_pl_default_upset_rules_thresholds() -> None:
    assert RULES.min_played == 8
    keys = {t.key for t in RULES.thresholds}
    assert keys == {"minor_upset", "major_upset", "major_upset_draw"}


@pytest.mark.parametrize(
    ("gap", "expected"),
    [
        (4, Decimal(0)),
        (5, Decimal(1)),
        (9, Decimal(1)),
        (10, Decimal(3)),
        (15, Decimal(3)),
    ],
)
def test_win_upset_gap_boundaries_4_5_9_10(gap: int, expected: Decimal) -> None:
    underdog = _team(1, rank=2 + gap, played=8)
    favorite = _team(2, rank=2, played=8)
    points, key, observed_gap = upset_bonus(underdog, favorite, Result.WIN, RULES)
    assert observed_gap == gap
    assert points == expected
    if expected == 1:
        assert key == "minor_upset"
    elif expected == 3:
        assert key == "major_upset"
    else:
        assert key is None


@pytest.mark.parametrize(("winner_played", "loser_played"), [(7, 8), (8, 7), (0, 0), (7, 7)])
def test_upset_requires_min_played_8_for_both(winner_played: int, loser_played: int) -> None:
    winner = _team(1, rank=12, played=winner_played)
    loser = _team(2, rank=2, played=loser_played)
    points, key, _ = upset_bonus(winner, loser, Result.WIN, RULES)
    assert points == 0
    assert key is None


def test_exactly_eight_played_allows_upset() -> None:
    winner = _team(1, rank=12, played=8)
    loser = _team(2, rank=2, played=8)
    points, key, _ = upset_bonus(winner, loser, Result.WIN, RULES)
    assert points == 3
    assert key == "major_upset"


@pytest.mark.parametrize(
    ("gap", "result", "expected"),
    [
        (9, Result.DRAW, Decimal(0)),
        (10, Result.DRAW, Decimal(1)),
        (10, Result.LOSS, Decimal(0)),
        (4, Result.WIN, Decimal(0)),
    ],
)
def test_result_specific_upset_rules(gap: int, result: Result, expected: Decimal) -> None:
    underdog = _team(1, rank=1 + gap, played=8)
    favorite = _team(2, rank=1, played=8)
    points, _, _ = upset_bonus(underdog, favorite, result, RULES)
    assert points == expected


def test_major_draw_bonus_goes_only_to_underdog() -> None:
    match = _match(1, home=1, away=2, kickoff=NOW, hg=1, ag=1, mw=10)
    snapshot = {
        1: _team(1, rank=2, played=8),
        2: _team(2, rank=12, played=8),
    }
    events = score_match_events(match, snapshot, result_points=POINTS, upset_rules=RULES)
    by_type = {(e.team_id, e.event_type): e.points for e in events}
    assert by_type[(1, "draw")] == 1
    assert by_type[(2, "draw")] == 1
    assert by_type[(2, "major_upset_draw")] == 1
    assert (1, "major_upset_draw") not in by_type


def test_minor_and_major_win_events() -> None:
    minor = _match(1, 1, 2, NOW, 2, 0)
    major = _match(2, 3, 4, NOW, 1, 0)
    minor_snap = {1: _team(1, 10, 8), 2: _team(2, 4, 8)}  # gap 6
    major_snap = {3: _team(3, 15, 8), 4: _team(4, 3, 8)}  # gap 12
    minor_events = score_match_events(minor, minor_snap, result_points=POINTS, upset_rules=RULES)
    major_events = score_match_events(major, major_snap, result_points=POINTS, upset_rules=RULES)
    assert any(e.event_type == "minor_upset" and e.points == 1 for e in minor_events)
    assert any(e.event_type == "major_upset" and e.points == 3 for e in major_events)


def test_table_tiebreak_points_gd_gf_name() -> None:
    assert DEFAULT_TABLE_TIEBREAKS == ("points", "gd", "gf", "name")
    alpha = TableRow(1, "Alpha", goals_for=10, goals_against=5, points=20)
    beta = TableRow(2, "Beta", goals_for=10, goals_against=5, points=20)
    ranked = rank_table((beta, alpha))
    assert [r.team_id for r in ranked] == [1, 2]

    better_gd = TableRow(3, "Charlie", goals_for=12, goals_against=5, points=20)
    worse_gd = TableRow(4, "Delta", goals_for=10, goals_against=5, points=20)
    ranked2 = rank_table((worse_gd, better_gd))
    assert ranked2[0].team_id == 3

    more_gf = TableRow(5, "Echo", goals_for=15, goals_against=10, points=20)
    fewer_gf = TableRow(6, "Foxtrot", goals_for=12, goals_against=7, points=20)
    ranked3 = rank_table((fewer_gf, more_gf))
    assert ranked3[0].team_id == 5


def test_simultaneous_kickoffs_share_one_pre_kickoff_snapshot() -> None:
    rows = [
        TableRow(1, "A", played=8, points=20),
        TableRow(2, "B", played=8, points=18),
        TableRow(3, "C", played=8, points=10),
        TableRow(4, "D", played=8, points=8),
    ]
    matches = [
        _match(1, 1, 4, NOW, 0, 1),
        _match(2, 2, 3, NOW, 0, 1),
    ]
    snapshots = kickoff_snapshots(matches, rows)
    assert len(snapshots) == 1
    snap = snapshot_map(snapshots[NOW])
    # Strict <: neither simultaneous result is in the table yet
    assert snap[1].played == 8
    assert snap[4].played == 8
    assert snap[1].rank == 1
    assert snap[2].rank == 2


def test_simultaneous_kickoffs_do_not_affect_each_other_via_build() -> None:
    rows = [TableRow(i, name=chr(64 + i)) for i in range(1, 5)]
    matches = [
        _match(1, 1, 2, NOW, 5, 0),
        _match(2, 3, 4, NOW, 5, 0),
    ]
    before = build_standings_before_kickoff(
        team_rows=rows, finished_matches=matches, kickoff_at=NOW
    )
    by_id = {r.team_id: r for r in before}
    assert all(r.played == 0 for r in by_id.values())


def test_postponement_uses_actual_kickoff_order_not_matchweek() -> None:
    rows = [TableRow(1, "A"), TableRow(2, "B"), TableRow(3, "C")]
    postponed = _match(1, 1, 2, NOW + timedelta(days=7), 1, 0, mw=2)
    earlier = _match(99, 1, 3, NOW, 0, 1, mw=3)  # later MW, earlier kickoff

    snap_early = snapshot_map(
        build_standings_before_kickoff(
            team_rows=rows, finished_matches=[postponed, earlier], kickoff_at=NOW
        )
    )
    snap_late = snapshot_map(
        build_standings_before_kickoff(
            team_rows=rows,
            finished_matches=[postponed, earlier],
            kickoff_at=NOW + timedelta(days=7),
        )
    )
    assert snap_early[1].played == 0
    assert snap_late[1].played == 1
    assert snap_late[3].played == 1


def test_recompute_cascade_from_changed_kickoff_forward() -> None:
    matches = [
        _match(1, 1, 2, NOW - timedelta(hours=1), 1, 0),
        _match(2, 3, 4, NOW, 2, 0),
        _match(3, 5, 6, NOW, 1, 1),
        _match(4, 1, 3, NOW + timedelta(days=1), 0, 0),
        _match(5, 10, 11, NOW + timedelta(days=1), 1, 0, pool_id=2),
    ]
    plan = plan_recompute_cascade(matches[1], matches)
    assert plan.affected_match_ids == (2, 3, 4)
    assert plan.stale_kickoffs == (NOW + timedelta(days=1),)
    assert plan.pool_id == 1
    assert 5 not in plan.affected_match_ids


def test_phase_matchweek_range_filter_mw1_19() -> None:
    filt = {"type": "matchweek_range", "from": 1, "to": 19}
    assert match_passes_phase_filter(scheduled_matchweek=1, stage=None, match_filter=filt)
    assert match_passes_phase_filter(scheduled_matchweek=19, stage=None, match_filter=filt)
    assert not match_passes_phase_filter(scheduled_matchweek=20, stage=None, match_filter=filt)
    assert not match_passes_phase_filter(scheduled_matchweek=None, stage=None, match_filter=filt)


def test_phase_stage_in_filter() -> None:
    filt = {"type": "stage_in", "stages": ["GROUP_STAGE"]}
    assert match_passes_phase_filter(
        scheduled_matchweek=None, stage="GROUP_STAGE", match_filter=filt
    )
    assert not match_passes_phase_filter(
        scheduled_matchweek=None, stage="FINAL", match_filter=filt
    )


def test_phase_points_excludes_out_of_range_matchweeks() -> None:
    events = [
        {"scheduled_matchweek": 1, "stage": None, "points": 3},
        {"scheduled_matchweek": 19, "stage": None, "points": 1},
        {"scheduled_matchweek": 20, "stage": None, "points": 3},
    ]
    total = phase_points_from_events(
        events, {"type": "matchweek_range", "from": 1, "to": 19}
    )
    assert total == Decimal(4)


def test_leaderboard_tiebreaks_and_true_tie() -> None:
    members = (
        MemberPoints(
            1,
            Decimal(20),
            event_points_by_type={"minor_upset": Decimal(2)},
            event_counts_by_type={"win": 4},
        ),
        MemberPoints(
            2,
            Decimal(20),
            event_points_by_type={"minor_upset": Decimal(3)},
            event_counts_by_type={"win": 1},
        ),
        MemberPoints(
            3,
            Decimal(20),
            event_points_by_type={"minor_upset": Decimal(3)},
            event_counts_by_type={"win": 1},
        ),
    )
    tiebreaks = [
        {"metric": "total_points", "direction": "desc"},
        {
            "metric": "event_points",
            "event_types": ["minor_upset", "major_upset", "major_upset_draw"],
            "direction": "desc",
        },
        {"metric": "event_count", "event_types": ["win"], "direction": "desc"},
    ]
    ranked = rank_leaderboard(members, tiebreaks)
    assert [(r.rank, r.member_id) for r in ranked] == [(1, 2), (1, 3), (3, 1)]


def test_leaderboard_legacy_string_rungs() -> None:
    members = (
        MemberPoints(1, Decimal(10), event_counts_by_type={"win": 5}),
        MemberPoints(2, Decimal(10), event_counts_by_type={"win": 2}),
    )
    ranked = rank_leaderboard(members, ("total_points", "win_count"))
    assert ranked[0].member_id == 1


def test_member_attribution_via_roster_join() -> None:
    team_points = {10: Decimal(5), 11: Decimal(3), 12: Decimal(7)}
    roster = {10: 1, 11: 1, 12: 2}  # team -> member
    totals = attribute_team_points_to_members(team_points, roster)
    assert totals == {1: Decimal(8), 2: Decimal(7)}


def test_scoring_events_unique_key_shape() -> None:
    match = _match(42, 1, 2, NOW, 1, 0)
    snapshot = {1: _team(1, 12, 8), 2: _team(2, 2, 8)}
    events = score_match_events(match, snapshot, result_points=POINTS, upset_rules=RULES)
    keys = {(e.match_id, e.team_id, e.event_type) for e in events}
    assert len(keys) == len(events)
    assert (42, 1, "win") in keys
    assert (42, 1, "major_upset") in keys


def test_favorite_win_gets_no_upset() -> None:
    match = _match(1, 1, 2, NOW, 2, 0)
    snapshot = {1: _team(1, 2, 8), 2: _team(2, 12, 8)}
    events = score_match_events(match, snapshot, result_points=POINTS, upset_rules=RULES)
    assert all(e.event_type in {"win"} for e in events)
    assert sum(e.points for e in events) == 3


def test_upset_rules_from_config_parses_eligibility() -> None:
    rules = UpsetRules.from_config(
        {
            "enabled": True,
            "eligibility": {"min_played": 8},
            "thresholds": [
                {"key": "minor_upset", "min_gap": 5, "max_gap": 9, "result": "win", "points": 1}
            ],
        }
    )
    assert rules.min_played == 8
    assert rules.thresholds[0].min_gap == 5


def test_disabled_upset_rules_yield_zero() -> None:
    rules = UpsetRules(enabled=False, thresholds=RULES.thresholds, min_played=8)
    points, key, _ = upset_bonus(_team(1, 20, 8), _team(2, 1, 8), Result.WIN, rules)
    assert points == 0
    assert key is None
